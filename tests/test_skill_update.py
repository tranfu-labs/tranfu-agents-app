"""Daily tfs update runner: backup, schedule, and rollback contracts."""
import json
import os
import plistlib
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shims"))

import tf_skill_update as updater


def _use_home(tmp_path, monkeypatch):
    root = tmp_path / ".tranfu"
    tfs_home = tmp_path / ".tfs"
    monkeypatch.setattr(updater, "TRANFU_HOME", root)
    monkeypatch.setattr(updater, "TFS_HOME", tfs_home)
    monkeypatch.setattr(updater, "CONFIG_PATH", root / "skill-update-config.json")
    monkeypatch.setattr(updater, "STATE_PATH", root / "skill-update-state.json")
    monkeypatch.setattr(updater, "LOCK_PATH", root / ".skill-update.lock")
    monkeypatch.setattr(updater, "BACKUP_ROOT", root / "skill-backups")
    monkeypatch.setattr(updater, "TFS_REGISTRY", tfs_home / "installed.json")
    monkeypatch.setattr(updater, "PLIST_PATH", tmp_path / "LaunchAgents" / f"{updater.LABEL}.plist")
    units = tmp_path / "systemd" / "user"
    monkeypatch.setattr(updater, "SYSTEMD_USER_DIR", units)
    monkeypatch.setattr(updater, "SYSTEMD_SERVICE", units / "tranfu-skill-update.service")
    monkeypatch.setattr(updater, "SYSTEMD_TIMER", units / "tranfu-skill-update.timer")
    updater._write_json_atomic(updater.CONFIG_PATH, {"schema": 1, "enabled": True,
                                                      "hour": 10, "minute": 20})
    return root, tfs_home


def test_run_backs_up_only_tfs_update_plan_before_exact_update(tmp_path, monkeypatch):
    _root, tfs_home = _use_home(tmp_path, monkeypatch)
    first = tmp_path / "skills" / "alpha"
    second = tmp_path / "project" / ".codex" / "skills" / "beta"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "SKILL.md").write_text("alpha-old", encoding="utf-8")
    (second / "SKILL.md").write_text("beta-old", encoding="utf-8")
    tfs_home.mkdir(parents=True)
    (tfs_home / "installed.json").write_text('{"version":1}', encoding="utf-8")
    plan = [
        {"name": "alpha", "path": str(first), "scope": "user",
         "runtime": "codex", "status": "outdated"},
        {"name": "beta", "path": str(second), "scope": "project",
         "runtime": "codex", "status": "noop"},
    ]
    calls = []

    def fake_exec(args, timeout=updater.COMMAND_TIMEOUT, env=None):
        calls.append(list(args))
        if args[1:] == ["update", "--skills-only", "--check-only", "--json"]:
            return {"returncode": 0, "stdout": json.dumps({"skills": plan}), "stderr": ""}
        if args[1:] == ["update", "--skills-only", "--json"]:
            assert any((p / "items" / "0001" / "SKILL.md").exists()
                       for p in updater.BACKUP_ROOT.iterdir())
            return {"returncode": 0, "stdout": json.dumps({
                "skills": [{"name": "alpha", "status": "updated"},
                           {"name": "beta", "status": "noop"}],
            }), "stderr": ""}
        raise AssertionError(args)

    monkeypatch.setattr(updater, "_resolve_tfs", lambda config=None: "/fake/tfs")
    monkeypatch.setattr(updater, "_exec", fake_exec)
    now = datetime(2026, 9, 3, 4, 0, tzinfo=timezone.utc)

    result = updater.run_update(now=now)

    assert calls == [
        ["/fake/tfs", "update", "--skills-only", "--check-only", "--json"],
        ["/fake/tfs", "update", "--skills-only", "--json"],
    ]
    assert result["status"] == "updated"
    manifest = next(updater.BACKUP_ROOT.iterdir()) / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["complete"] is True
    assert [item["status"] for item in data["items"]] == ["copied"]
    assert data["items"][0]["path"] == str(first)
    assert not any(item.get("path") == str(second) for item in data["items"])
    assert (manifest.parent / "tfs-installed.json").read_text(encoding="utf-8") == '{"version":1}'


def test_unsafe_or_failed_backup_stops_before_update(tmp_path, monkeypatch):
    _use_home(tmp_path, monkeypatch)
    calls = []

    def fake_exec(args, timeout=updater.COMMAND_TIMEOUT, env=None):
        calls.append(list(args))
        return {"returncode": 0, "stdout": json.dumps({
            "skills": [{"name": Path.home().name, "path": str(Path.home()),
                        "status": "outdated"}],
        }), "stderr": ""}

    monkeypatch.setattr(updater, "_resolve_tfs", lambda config=None: "/fake/tfs")
    monkeypatch.setattr(updater, "_exec", fake_exec)

    result = updater.run_update(now=datetime(2026, 9, 4, tzinfo=timezone.utc))

    assert result["status"] == "failed"
    assert result["error"] == "backup_failed"
    assert calls == [["/fake/tfs", "update", "--skills-only", "--check-only", "--json"]]


def test_same_local_day_does_not_run_twice(tmp_path, monkeypatch):
    _use_home(tmp_path, monkeypatch)
    updater._write_json_atomic(updater.STATE_PATH, {
        "schema": 1, "last_attempt_local_day": "2026-09-03", "status": "noop",
    })
    monkeypatch.setattr(updater, "_resolve_tfs",
                        lambda config=None: (_ for _ in ()).throw(AssertionError("must not resolve")))
    now = datetime(2026, 9, 3, 12, 0).astimezone()

    assert updater.run_update(now=now)["reason"] == "already_attempted_today"


def test_minimal_launchagent_path_resolves_node_next_to_tfs(tmp_path, monkeypatch):
    _use_home(tmp_path, monkeypatch)
    bin_dir = tmp_path / "nvm" / "versions" / "node" / "v24" / "bin"
    bin_dir.mkdir(parents=True)
    node = bin_dir / "node"
    tfs = bin_dir / "tfs"
    node.write_text(
        "#!/bin/sh\nexec %s \"$@\"\n" % shlex.quote(sys.executable),
        encoding="utf-8",
    )
    tfs.write_text(
        "#!/usr/bin/env node\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if args == ['--version']:\n"
        "    print('9.9.9')\n"
        "elif args == ['update', '--skills-only', '--check-only', '--json']:\n"
        "    print(json.dumps({'skills': []}))\n"
        "elif args == ['update', '--skills-only', '--json']:\n"
        "    print(json.dumps({'skills': []}))\n"
        "else:\n"
        "    raise SystemExit(2)\n",
        encoding="utf-8",
    )
    node.chmod(0o755)
    tfs.chmod(0o755)
    config = updater._load_config()
    config["tfs_path"] = str(tfs)
    updater._save_config(config)
    monkeypatch.setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    monkeypatch.delenv("TF_TFS_BIN", raising=False)

    result = updater.run_update(
        force=True, now=datetime(2026, 9, 5, 4, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "noop"
    assert result["backup_run"]
    assert updater._load_config()["tfs_path"] == str(tfs)


def test_outdated_plan_without_path_stops_before_update(tmp_path, monkeypatch):
    _use_home(tmp_path, monkeypatch)
    calls = []

    def fake_exec(args, timeout=updater.COMMAND_TIMEOUT, env=None):
        calls.append(list(args))
        return {"returncode": 0, "stdout": json.dumps({
            "skills": [{"name": "alpha", "status": "outdated"}],
        }), "stderr": ""}

    monkeypatch.setattr(updater, "_resolve_tfs", lambda config=None: "/fake/tfs")
    monkeypatch.setattr(updater, "_exec", fake_exec)

    result = updater.run_update(
        force=True, now=datetime(2026, 9, 6, 4, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "failed"
    assert result["error"] == "update_plan_failed"
    assert calls == [["/fake/tfs", "update", "--skills-only", "--check-only", "--json"]]


def test_explicit_rollback_restores_skill_and_registry(tmp_path, monkeypatch):
    _root, tfs_home = _use_home(tmp_path, monkeypatch)
    skill = tmp_path / "skills" / "alpha"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("old", encoding="utf-8")
    tfs_home.mkdir(parents=True)
    updater.TFS_REGISTRY.write_text("old-registry", encoding="utf-8")
    run_id, _run_dir = updater._snapshot_plan(
        [{"name": "alpha", "path": str(skill)}],
        datetime(2026, 9, 3, tzinfo=timezone.utc),
    )
    (skill / "SKILL.md").write_text("new", encoding="utf-8")
    updater.TFS_REGISTRY.write_text("new-registry", encoding="utf-8")

    result = updater.rollback(run_id)

    assert result["status"] == "rollback_completed"
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == "old"
    assert updater.TFS_REGISTRY.read_text(encoding="utf-8") == "old-registry"


def test_launch_agent_install_is_idempotent_and_managed_only(tmp_path, monkeypatch):
    _use_home(tmp_path, monkeypatch)
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    monkeypatch.setattr(updater, "_resolve_tfs", lambda config=None: "/fake/tfs")
    calls = []

    def fake_launchctl(args):
        calls.append(list(args))
        return args[0] != "print"

    monkeypatch.setattr(updater, "_launchctl", fake_launchctl)
    first = updater.install_schedule()
    second = updater.install_schedule()
    payload = plistlib.loads(updater.PLIST_PATH.read_bytes())

    assert first["status"] == second["status"] == "installed"
    assert first["changed"] is True and second["changed"] is False
    assert payload["Label"] == updater.LABEL
    assert payload["RunAtLoad"] is True
    assert payload["ProgramArguments"][-2:] == ["run", "--json"]
    assert all(Path(value).is_absolute() for value in payload["ProgramArguments"][:2])
    assert sum(call[0] == "bootstrap" for call in calls) == 2

    removed = updater.uninstall_schedule()
    assert removed["status"] == "uninstalled"
    assert not updater.PLIST_PATH.exists()


def test_ensure_schedule_preserves_disabled_preference(tmp_path, monkeypatch):
    _use_home(tmp_path, monkeypatch)
    updater._write_json_atomic(updater.CONFIG_PATH, {
        "schema": 1, "enabled": False, "hour": 10, "minute": 20,
    })
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    monkeypatch.setattr(updater, "_launchctl", lambda _args: True)

    result = updater.ensure_schedule()

    assert result["status"] == "uninstalled"
    assert updater._load_config()["enabled"] is False
    assert not updater.PLIST_PATH.exists()


def test_linux_systemd_units_use_user_timer(tmp_path, monkeypatch):
    _use_home(tmp_path, monkeypatch)
    monkeypatch.setattr(updater.sys, "platform", "linux")
    monkeypatch.setattr(updater, "_resolve_tfs", lambda config=None: "/fake/tfs")
    monkeypatch.setattr(updater.shutil, "which", lambda name: "/bin/systemctl" if name == "systemctl" else None)
    calls = []
    monkeypatch.setattr(updater, "_exec", lambda args, timeout=updater.COMMAND_TIMEOUT, env=None:
                        calls.append(list(args)) or {"returncode": 0, "stdout": "", "stderr": ""})

    result = updater.install_schedule()

    assert result["status"] == "installed"
    timer = updater.SYSTEMD_TIMER.read_text(encoding="utf-8")
    service = updater.SYSTEMD_SERVICE.read_text(encoding="utf-8")
    assert "Persistent=true" in timer and "RandomizedDelaySec=30m" in timer
    assert "run --json" in service
    assert any(call[1:4] == ["--user", "enable", "--now"] for call in calls)


def test_prune_keeps_three_complete_runs(tmp_path, monkeypatch):
    _use_home(tmp_path, monkeypatch)
    for day in range(1, 5):
        skill = tmp_path / f"skills-{day}" / f"skill-{day}"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(str(day), encoding="utf-8")
        updater._snapshot_plan(
            [{"name": f"skill-{day}", "path": str(skill)}],
            datetime(2026, 9, day, tzinfo=timezone.utc),
        )
    updater._prune_backups()

    assert len(updater._complete_runs()) == 3
