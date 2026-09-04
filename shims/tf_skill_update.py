#!/usr/bin/env python3
"""Schedule, back up, run, and roll back tfs skill updates.

This shim deliberately treats tfs as the sole authority for update semantics.
It snapshots ``outdated`` paths returned by the tfs update check-only plan,
then invokes ``tfs update --skills-only --json`` without adding scope policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = 1
LABEL = "com.tranfu.skill-update"
KEEP_BACKUPS = 3
COMMAND_TIMEOUT = 15 * 60
LOCK_STALE_SECONDS = 30 * 60
MAX_OUTPUT = 128 * 1024

TRANFU_HOME = Path(os.environ.get("TF_TRANFU_HOME") or Path.home() / ".tranfu")
TFS_HOME = Path(os.environ.get("TF_TFS_HOME") or Path.home() / ".tfs")
CONFIG_PATH = TRANFU_HOME / "skill-update-config.json"
STATE_PATH = TRANFU_HOME / "skill-update-state.json"
LOCK_PATH = TRANFU_HOME / ".skill-update.lock"
BACKUP_ROOT = TRANFU_HOME / "skill-backups"
TFS_REGISTRY = TFS_HOME / "installed.json"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
SYSTEMD_SERVICE = SYSTEMD_USER_DIR / "tranfu-skill-update.service"
SYSTEMD_TIMER = SYSTEMD_USER_DIR / "tranfu-skill-update.timer"


def _utc_now():
    return datetime.now(timezone.utc)


def _read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_json_atomic(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.chmod(tmp, mode)
    os.replace(str(tmp), str(path))


def _write_bytes_atomic(path, data, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, mode)
    os.replace(str(tmp), str(path))


def _enabled_from_env(default=True):
    raw = os.environ.get("TF_SKILL_AUTO_UPDATE")
    if raw is None:
        return bool(default)
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _schedule_time():
    seed = f"{os.getuid()}:{Path.home()}".encode("utf-8", errors="replace")
    value = int(hashlib.sha256(seed).hexdigest()[:12], 16)
    return 9 + value % 9, (value // 9) % 60


def _load_config():
    config = _read_json(CONFIG_PATH) or {}
    if not isinstance(config.get("enabled"), bool):
        config["enabled"] = _enabled_from_env(True)
    config.setdefault("schema", SCHEMA)
    hour, minute = _schedule_time()
    config.setdefault("hour", hour)
    config.setdefault("minute", minute)
    return config


def _save_config(config):
    config = dict(config)
    config["schema"] = SCHEMA
    _write_json_atomic(CONFIG_PATH, config)


def _safe_error(value):
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    return text[:240]


def _state(status, **extra):
    previous = _read_json(STATE_PATH) or {}
    payload = {
        "schema": SCHEMA,
        "enabled": bool(_load_config().get("enabled")),
        "status": status,
        "scheduler": _scheduler_name(),
    }
    for key in ("last_attempt_at", "last_attempt_local_day", "last_success_at",
                "backup_run", "last_rollback_at", "rollback_run"):
        if key in previous:
            payload[key] = previous[key]
    payload.update(extra)
    try:
        _write_json_atomic(STATE_PATH, payload)
    except Exception:
        pass
    return payload


def _acquire_lock(path=LOCK_PATH):
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(fd, str(os.getpid()).encode("ascii"))
        return fd
    except FileExistsError:
        try:
            if time.time() - path.stat().st_mtime > LOCK_STALE_SECONDS:
                path.unlink()
                return _acquire_lock(path)
        except Exception:
            pass
    except Exception:
        pass
    return None


def _release_lock(fd, path=LOCK_PATH):
    try:
        if fd is not None:
            os.close(fd)
    except Exception:
        pass
    try:
        Path(path).unlink()
    except Exception:
        pass


def _candidate_tfs_paths(config):
    seen = set()

    def add(value):
        if not value:
            return
        path = os.path.abspath(os.path.expanduser(str(value)))
        if path not in seen:
            seen.add(path)
            yield path

    for value in (os.environ.get("TF_TFS_BIN"), config.get("tfs_path"), shutil.which("tfs")):
        yield from add(value)
    for value in ("/opt/homebrew/bin/tfs", "/usr/local/bin/tfs",
                  str(Path.home() / ".local" / "bin" / "tfs")):
        yield from add(value)
    try:
        nvm = sorted((Path.home() / ".nvm" / "versions" / "node").glob("*/bin/tfs"),
                     reverse=True)
    except Exception:
        nvm = []
    for value in nvm:
        yield from add(value)


def _exec(args, timeout=COMMAND_TIMEOUT, env=None):
    try:
        proc = subprocess.run(
            list(args), capture_output=True, text=True, timeout=timeout,
            env=dict(os.environ) if env is None else dict(env),
        )
        return {
            "returncode": int(proc.returncode),
            "stdout": (proc.stdout or "")[:MAX_OUTPUT],
            "stderr": (proc.stderr or "")[:MAX_OUTPUT],
        }
    except subprocess.TimeoutExpired as exc:
        return {"returncode": 124, "stdout": _safe_error(exc.stdout),
                "stderr": "command_timeout"}
    except Exception as exc:
        return {"returncode": 127, "stdout": "",
                "stderr": type(exc).__name__}


def _tfs_env(tfs_bin):
    """Return a minimal per-command PATH that can resolve tfs' Node shebang."""
    env = dict(os.environ)
    bin_dir = str(Path(tfs_bin).parent)
    current = env.get("PATH", "")
    parts = [part for part in current.split(os.pathsep) if part and part != bin_dir]
    env["PATH"] = os.pathsep.join([bin_dir] + parts)
    return env


def _tfs_exec(tfs_bin, args, timeout=COMMAND_TIMEOUT):
    return _exec([tfs_bin] + list(args), timeout=timeout, env=_tfs_env(tfs_bin))


def _resolve_tfs(config=None):
    config = config or _load_config()
    for candidate in _candidate_tfs_paths(config):
        path = Path(candidate)
        try:
            if not path.is_file() or not os.access(str(path), os.X_OK):
                continue
            result = _tfs_exec(str(path), ["--version"], timeout=8)
            if result["returncode"] == 0:
                return os.path.abspath(str(path))
        except Exception:
            continue
    return ""


def _parse_json_result(result):
    if result.get("returncode") != 0:
        return None
    try:
        data = json.loads(result.get("stdout") or "")
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _update_plan(tfs_bin):
    result = _tfs_exec(
        tfs_bin, ["update", "--skills-only", "--check-only", "--json"], timeout=60,
    )
    data = _parse_json_result(result)
    items = data.get("skills") if data else None
    if not isinstance(items, list):
        raise RuntimeError("update_plan_failed")
    planned = []
    for item in items:
        if not isinstance(item, dict) or item.get("status") != "outdated":
            continue
        name = item.get("name")
        path = item.get("path")
        if not isinstance(name, str) or not name or not isinstance(path, str) or not path:
            raise RuntimeError("update_plan_failed")
        planned.append({"name": name, "path": path})
    return planned


def _run_id(now):
    base = now.strftime("%Y%m%dT%H%M%SZ")
    candidate = base
    index = 1
    while (BACKUP_ROOT / candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _validate_plan_path(item, require_exists=True):
    name = item.get("name") if isinstance(item, dict) else None
    raw = item.get("path") if isinstance(item, dict) else None
    if not isinstance(name, str) or not name or not isinstance(raw, str) or not raw:
        raise ValueError("invalid_plan_item")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError("path_not_absolute")
    if path.is_symlink():
        raise ValueError("target_is_symlink")
    resolved = path.resolve(strict=False)
    if resolved in (Path("/"), Path.home().resolve()):
        raise ValueError("broad_target")
    if resolved.name != name:
        raise ValueError("name_path_mismatch")
    if require_exists:
        if not resolved.exists():
            return None
        if not resolved.is_dir():
            raise ValueError("target_not_directory")
    return resolved


def _snapshot_plan(items, now=None):
    now = now or _utc_now()
    run_id = _run_id(now)
    run_dir = BACKUP_ROOT / run_id
    items_dir = run_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=False)
    os.chmod(run_dir, 0o700)
    os.chmod(items_dir, 0o700)
    manifest = {
        "schema": SCHEMA,
        "run_id": run_id,
        "created_at": now.isoformat(),
        "complete": False,
        "registry_present": TFS_REGISTRY.is_file(),
        "items": [],
    }
    copied = set()
    try:
        for item in items:
            name = item.get("name", "") if isinstance(item, dict) else ""
            raw = item.get("path", "") if isinstance(item, dict) else ""
            record = {"name": str(name), "path": str(raw)}
            path = _validate_plan_path(item)
            if path is None:
                record.update({"status": "skipped", "reason": "missing"})
                manifest["items"].append(record)
                continue
            key = str(path)
            if key in copied:
                record.update({"status": "skipped", "reason": "duplicate"})
                manifest["items"].append(record)
                continue
            copied.add(key)
            rel = f"items/{len(copied):04d}"
            shutil.copytree(str(path), str(run_dir / rel), symlinks=True)
            record.update({"status": "copied", "backup": rel})
            manifest["items"].append(record)
        if TFS_REGISTRY.is_file():
            shutil.copy2(str(TFS_REGISTRY), str(run_dir / "tfs-installed.json"))
        manifest["complete"] = True
        _write_json_atomic(run_dir / "manifest.json", manifest)
        return run_id, run_dir
    except Exception as exc:
        manifest["error"] = _safe_error(type(exc).__name__ + ":" + str(exc))
        try:
            _write_json_atomic(run_dir / "manifest.json", manifest)
        except Exception:
            pass
        raise RuntimeError("backup_failed") from exc


def _complete_runs():
    try:
        children = sorted(BACKUP_ROOT.iterdir(), key=lambda p: p.name, reverse=True)
    except Exception:
        return []
    runs = []
    for child in children:
        if child.is_symlink() or not child.is_dir():
            continue
        manifest = _read_json(child / "manifest.json")
        if manifest and manifest.get("schema") == SCHEMA and manifest.get("complete") is True:
            if manifest.get("run_id") == child.name:
                runs.append((child, manifest))
    return runs


def _prune_backups(keep=KEEP_BACKUPS):
    for path, _manifest in _complete_runs()[max(0, int(keep)):]:
        try:
            if path.parent.resolve() == BACKUP_ROOT.resolve() and not path.is_symlink():
                shutil.rmtree(path)
        except Exception:
            pass


def _summarize_update(data):
    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, list):
        return {"updated": 0, "failed": 0, "total": 0}
    updated = 0
    failed = 0
    for item in skills:
        status = item.get("status") if isinstance(item, dict) else ""
        updated += status == "updated"
        failed += status == "failed"
    return {"updated": updated, "failed": failed, "total": len(skills)}


def run_update(force=False, now=None):
    now = now or _utc_now()
    config = _load_config()
    if not config.get("enabled"):
        return _state("disabled")
    local_day = now.astimezone().date().isoformat()
    previous = _read_json(STATE_PATH) or {}
    if not force and previous.get("last_attempt_local_day") == local_day:
        return _state("noop", reason="already_attempted_today")
    fd = _acquire_lock()
    if fd is None:
        return _state("busy", reason="runner_locked")
    attempted = {"last_attempt_at": now.isoformat(), "last_attempt_local_day": local_day}
    try:
        tfs_bin = _resolve_tfs(config)
        if not tfs_bin:
            return _state("failed", error="tfs_not_found", **attempted)
        if config.get("tfs_path") != tfs_bin:
            config["tfs_path"] = tfs_bin
            _save_config(config)
        try:
            items = _update_plan(tfs_bin)
        except Exception:
            return _state("failed", error="update_plan_failed", **attempted)
        try:
            run_id, _run_dir = _snapshot_plan(items, now)
        except Exception:
            return _state("failed", error="backup_failed", **attempted)
        result = _tfs_exec(tfs_bin, ["update", "--skills-only", "--json"])
        data = _parse_json_result(result)
        if data is None:
            error = "update_failed" if result.get("returncode") else "update_bad_json"
            payload = _state("failed", error=error, backup_run=run_id, **attempted)
        else:
            summary = _summarize_update(data)
            status = "completed_with_errors" if summary["failed"] else (
                "updated" if summary["updated"] else "noop")
            payload = _state(status, backup_run=run_id, tfs_summary=summary,
                             last_success_at=now.isoformat(), **attempted)
        _prune_backups()
        return payload
    finally:
        _release_lock(fd)


def _safe_run(run_id):
    if not isinstance(run_id, str) or not run_id or "/" in run_id or "\\" in run_id:
        raise ValueError("invalid_run_id")
    path = BACKUP_ROOT / run_id
    if path.is_symlink() or not path.is_dir() or path.parent.resolve() != BACKUP_ROOT.resolve():
        raise ValueError("backup_not_found")
    manifest = _read_json(path / "manifest.json")
    if not manifest or manifest.get("schema") != SCHEMA or not manifest.get("complete"):
        raise ValueError("backup_incomplete")
    if manifest.get("run_id") != run_id:
        raise ValueError("backup_identity_mismatch")
    return path, manifest


def rollback(run_id=""):
    if not run_id:
        runs = _complete_runs()
        if not runs:
            return _state("rollback_failed", error="backup_not_found")
        run_id = runs[0][0].name
    try:
        run_dir, manifest = _safe_run(run_id)
    except Exception as exc:
        return _state("rollback_failed", error=_safe_error(exc))
    fd = _acquire_lock()
    if fd is None:
        return _state("busy", reason="runner_locked")
    staged = []
    applied = []
    try:
        for index, item in enumerate(manifest.get("items", []), start=1):
            if item.get("status") != "copied":
                continue
            target = _validate_plan_path(item, require_exists=False)
            backup = (run_dir / str(item.get("backup", ""))).resolve()
            if not str(backup).startswith(str(run_dir.resolve()) + os.sep) or not backup.is_dir():
                raise ValueError("backup_item_invalid")
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = target.parent / f".tranfu-skill-restore-{os.getpid()}-{index}"
            if stage.exists():
                shutil.rmtree(stage)
            shutil.copytree(str(backup), str(stage), symlinks=True)
            staged.append((target, stage, index))
        for target, stage, index in staged:
            current = target.parent / f".tranfu-skill-current-{os.getpid()}-{index}"
            existed = target.exists()
            if current.exists():
                shutil.rmtree(current)
            if existed:
                os.replace(str(target), str(current))
            try:
                os.replace(str(stage), str(target))
            except Exception:
                if existed and current.exists():
                    os.replace(str(current), str(target))
                raise
            applied.append((target, current, existed))
        registry_backup = run_dir / "tfs-installed.json"
        if manifest.get("registry_present") and registry_backup.is_file():
            TFS_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
            tmp = TFS_REGISTRY.with_name(TFS_REGISTRY.name + ".tranfu-restore.tmp")
            shutil.copy2(str(registry_backup), str(tmp))
            os.replace(str(tmp), str(TFS_REGISTRY))
        for _target, current, existed in applied:
            if existed and current.exists():
                try:
                    shutil.rmtree(current)
                except Exception:
                    pass
        now = _utc_now().isoformat()
        return _state("rollback_completed", last_rollback_at=now, rollback_run=run_id)
    except Exception as exc:
        for target, current, existed in reversed(applied):
            try:
                if target.exists():
                    shutil.rmtree(target)
                if existed and current.exists():
                    os.replace(str(current), str(target))
            except Exception:
                pass
        return _state("rollback_failed", error=_safe_error(type(exc).__name__ + ":" + str(exc)),
                      rollback_run=run_id)
    finally:
        for _target, stage, _index in staged:
            try:
                if stage.exists():
                    shutil.rmtree(stage)
            except Exception:
                pass
        _release_lock(fd)


def _scheduler_name():
    if sys.platform == "darwin":
        return "launchd"
    if sys.platform.startswith("linux"):
        return "systemd-user"
    return "unsupported"


def _launchctl(args):
    binary = shutil.which("launchctl") or "/bin/launchctl"
    return _exec([binary] + list(args), timeout=15)["returncode"] == 0


def _managed_plist():
    try:
        return plistlib.loads(PLIST_PATH.read_bytes()).get("Label") == LABEL
    except Exception:
        return False


def _install_launch_agent(config):
    script = str(Path(__file__).resolve())
    python = str(Path(sys.executable).resolve())
    payload = {
        "Label": LABEL,
        "ProgramArguments": [python, script, "run", "--json"],
        "RunAtLoad": True,
        "StartCalendarInterval": {
            "Hour": int(config["hour"]), "Minute": int(config["minute"]),
        },
        "ProcessType": "Background",
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
    }
    encoded = plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)
    changed = not PLIST_PATH.exists() or PLIST_PATH.read_bytes() != encoded
    if PLIST_PATH.exists() and not _managed_plist():
        return {"status": "error", "error": "unmanaged_plist"}
    if changed:
        _write_bytes_atomic(PLIST_PATH, encoded, 0o644)
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LABEL}"
    loaded = _launchctl(["print", service])
    if changed or not loaded:
        if changed and loaded:
            _launchctl(["bootout", domain, str(PLIST_PATH)])
        if not _launchctl(["bootstrap", domain, str(PLIST_PATH)]):
            return {"status": "error", "error": "launchctl_bootstrap_failed"}
    return {"status": "installed", "scheduler": "launchd", "changed": changed}


def _systemd_quote(value):
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return '"' + escaped + '"'


def _install_systemd_timer(config):
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return {"status": "error", "error": "systemd_user_unavailable"}
    script = str(Path(__file__).resolve())
    python = str(Path(sys.executable).resolve())
    marker = "# managed by TRANFU//AGENTS\n"
    service = marker + """[Unit]
Description=Update TRANFU managed skills

[Service]
Type=oneshot
ExecStart=%s %s run --json
""" % (_systemd_quote(python), _systemd_quote(script))
    timer = marker + """[Unit]
Description=Daily TRANFU managed skill update

[Timer]
OnCalendar=*-*-* %02d:%02d:00
Persistent=true
RandomizedDelaySec=30m

[Install]
WantedBy=timers.target
""" % (int(config["hour"]), int(config["minute"]))
    _write_bytes_atomic(SYSTEMD_SERVICE, service.encode("utf-8"), 0o644)
    _write_bytes_atomic(SYSTEMD_TIMER, timer.encode("utf-8"), 0o644)
    if _exec([systemctl, "--user", "daemon-reload"], timeout=20)["returncode"] != 0:
        return {"status": "error", "error": "systemd_reload_failed"}
    result = _exec([systemctl, "--user", "enable", "--now", SYSTEMD_TIMER.name], timeout=20)
    if result["returncode"] != 0:
        return {"status": "error", "error": "systemd_enable_failed"}
    return {"status": "installed", "scheduler": "systemd-user"}


def _apply_schedule(config):
    try:
        if sys.platform == "darwin":
            return _install_launch_agent(config)
        if sys.platform.startswith("linux"):
            return _install_systemd_timer(config)
        return {"status": "skipped", "error": "unsupported_platform"}
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__}


def install_schedule():
    config = _load_config()
    config["enabled"] = True
    tfs_bin = _resolve_tfs(config)
    if tfs_bin:
        config["tfs_path"] = tfs_bin
    _save_config(config)
    return _apply_schedule(config)


def ensure_schedule():
    """Repair the managed schedule without changing the persisted preference."""
    config = _load_config()
    _save_config(config)
    if not config.get("enabled"):
        return uninstall_schedule(preserve_config=True)
    tfs_bin = _resolve_tfs(config)
    if tfs_bin and config.get("tfs_path") != tfs_bin:
        config["tfs_path"] = tfs_bin
        _save_config(config)
    return _apply_schedule(config)


def uninstall_schedule(preserve_config=False):
    config = _load_config()
    if not preserve_config:
        config["enabled"] = False
        _save_config(config)
    try:
        if sys.platform == "darwin":
            if PLIST_PATH.exists() and not _managed_plist():
                return {"status": "error", "error": "unmanaged_plist"}
            _launchctl(["bootout", f"gui/{os.getuid()}", str(PLIST_PATH)])
            existed = PLIST_PATH.exists()
            try:
                PLIST_PATH.unlink()
            except FileNotFoundError:
                pass
            return {"status": "uninstalled", "changed": existed}
        if sys.platform.startswith("linux"):
            systemctl = shutil.which("systemctl")
            if systemctl:
                _exec([systemctl, "--user", "disable", "--now", SYSTEMD_TIMER.name], timeout=20)
            changed = False
            for path in (SYSTEMD_TIMER, SYSTEMD_SERVICE):
                if path.exists():
                    try:
                        if not path.read_text(encoding="utf-8").startswith("# managed by TRANFU//AGENTS"):
                            return {"status": "error", "error": "unmanaged_systemd_unit"}
                        path.unlink()
                        changed = True
                    except Exception as exc:
                        return {"status": "error", "error": type(exc).__name__}
            if systemctl:
                _exec([systemctl, "--user", "daemon-reload"], timeout=20)
            return {"status": "uninstalled", "changed": changed}
        return {"status": "skipped", "error": "unsupported_platform"}
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__}


def schedule_status():
    config = _load_config()
    installed = False
    if sys.platform == "darwin":
        installed = PLIST_PATH.exists() and _managed_plist()
    elif sys.platform.startswith("linux"):
        installed = SYSTEMD_TIMER.is_file() and SYSTEMD_SERVICE.is_file()
    state = _read_json(STATE_PATH) or {}
    return {
        "status": "installed" if installed else "not_installed",
        "enabled": bool(config.get("enabled")),
        "scheduler": _scheduler_name(),
        "tfs_found": bool(_resolve_tfs(config)),
        "last_attempt_at": state.get("last_attempt_at", ""),
        "last_success_at": state.get("last_success_at", ""),
        "last_result": state.get("status", "never"),
        "backup_run": state.get("backup_run", ""),
    }


def _emit(result, as_json):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser(description="TRANFU managed skill update scheduler")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "status", "install-schedule", "ensure-schedule", "uninstall-schedule"):
        command = sub.add_parser(name)
        command.add_argument("--json", action="store_true")
        if name == "run":
            command.add_argument("--force", action="store_true")
    restore = sub.add_parser("rollback")
    group = restore.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true")
    group.add_argument("--run", dest="run_id")
    restore.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            result = run_update(force=args.force)
        elif args.command == "status":
            result = schedule_status()
        elif args.command == "install-schedule":
            result = install_schedule()
        elif args.command == "ensure-schedule":
            result = ensure_schedule()
        elif args.command == "uninstall-schedule":
            result = uninstall_schedule()
        else:
            result = rollback("" if args.latest else args.run_id)
    except Exception as exc:
        result = {"status": "error", "error": type(exc).__name__}
    _emit(result, args.json)
    return 1 if result.get("status") in {"error", "failed", "rollback_failed"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
