"""Codex Hook guard safety and lifecycle contracts."""
import json
import os
import plistlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shims"))

import tf_codex_hook_guard as guard


SOURCE = "/tmp/home/.codex/hooks.json"
TRANFU = '. "$HOME/.tranfu/tf_env.codex.sh"; python3 "$HOME/.tranfu/tf_hook.py"'
THIRD = "/tmp/codeisland-bridge --source codex"


def _group(command, matcher=None, extra=None):
    value = {"hooks": [{"type": "command", "command": command, "timeout": 5}]}
    if matcher is not None:
        value["matcher"] = matcher
    if extra:
        value.update(extra)
    return value


def _hook(index, command, digest, trust="modified", enabled=False,
          event="preToolUse", handler=0):
    return {
        "key": f"{SOURCE}:pre_tool_use:{index}:{handler}",
        "eventName": event,
        "handlerType": "command",
        "command": command,
        "sourcePath": SOURCE,
        "source": "user",
        "currentHash": digest,
        "trustStatus": trust,
        "enabled": enabled,
    }


def _permuted_fixture():
    tranfu_group = _group(TRANFU, matcher="", extra={"thirdPartyField": "keep"})
    third_group = _group(THIRD, matcher="Bash")
    document = {"hooks": {"PreToolUse": [tranfu_group, third_group]}}
    entry = {"hooks": [
        _hook(0, TRANFU, "sha256:tranfu"),
        _hook(1, THIRD, "sha256:third"),
    ]}
    trusted = {
        f"{SOURCE}:pre_tool_use:0:0": "sha256:third",
        f"{SOURCE}:pre_tool_use:1:0": "sha256:tranfu",
    }
    return document, entry, trusted


def test_pure_group_permutation_is_repaired_without_mutating_input():
    document, entry, trusted = _permuted_fixture()
    repaired, events = guard.build_reordered_document(document, entry, trusted, SOURCE)

    assert events == ["preToolUse"]
    assert repaired["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == THIRD
    assert repaired["hooks"]["PreToolUse"][1]["thirdPartyField"] == "keep"
    assert document["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == TRANFU


def test_multi_handler_group_moves_as_one_unit():
    tranfu_group = {
        "matcher": "x",
        "hooks": [
            {"type": "command", "command": TRANFU},
            {"type": "command", "command": "helper"},
        ],
    }
    third_group = _group(THIRD)
    document = {"hooks": {"PreToolUse": [tranfu_group, third_group]}}
    entry = {"hooks": [
        _hook(0, TRANFU, "sha256:t", handler=0),
        _hook(0, "helper", "sha256:h", handler=1),
        _hook(1, THIRD, "sha256:x", handler=0),
    ]}
    trusted = {
        f"{SOURCE}:pre_tool_use:0:0": "sha256:x",
        f"{SOURCE}:pre_tool_use:1:0": "sha256:t",
        f"{SOURCE}:pre_tool_use:1:1": "sha256:h",
    }

    repaired, _events = guard.build_reordered_document(document, entry, trusted, SOURCE)
    moved = repaired["hooks"]["PreToolUse"][1]
    assert moved["matcher"] == "x"
    assert [item["command"] for item in moved["hooks"]] == [TRANFU, "helper"]


@pytest.mark.parametrize("mutation,code", [
    (lambda trusted: trusted.__setitem__(f"{SOURCE}:pre_tool_use:0:0", "sha256:new"),
     "not_a_trusted_permutation"),
    (lambda trusted: trusted.__setitem__(f"{SOURCE}:pre_tool_use:0:0", "sha256:tranfu"),
     "trusted_groups_not_unique"),
    (lambda trusted: trusted.pop(f"{SOURCE}:pre_tool_use:0:0"),
     "trusted_hash_missing"),
])
def test_new_duplicate_or_missing_trusted_hash_refuses_repair(mutation, code):
    document, entry, trusted = _permuted_fixture()
    mutation(trusted)
    with pytest.raises(guard.GuardError) as exc:
        guard.build_reordered_document(document, entry, trusted, SOURCE)
    assert exc.value.code == code


def _write_config(path, trusted):
    lines = []
    for key, value in trusted.items():
        escaped = json.dumps(key, ensure_ascii=False)
        lines += [f"[hooks.state.{escaped}]", f'trusted_hash = "{value}"', ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def test_post_repair_failure_restores_original(tmp_path, monkeypatch):
    document, before, trusted = _permuted_fixture()
    hooks = tmp_path / "hooks.json"
    config = tmp_path / "config.toml"
    state = tmp_path / "state.json"
    binary = tmp_path / "codex"
    hooks.write_text(json.dumps(document), encoding="utf-8")
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    actual_source = str(hooks)
    for item in before["hooks"]:
        item["sourcePath"] = actual_source
        item["key"] = item["key"].replace(SOURCE, actual_source)
    trusted = {key.replace(SOURCE, actual_source): value for key, value in trusted.items()}
    _write_config(config, trusted)
    original = hooks.read_bytes()
    calls = []

    def fake_rpc(_cwd, _binary):
        calls.append(1)
        return before  # remains modified after the write -> rollback

    monkeypatch.setattr(guard, "_notify_user", lambda _message: False)
    result = guard.run_check(hooks, config, state, str(binary), tmp_path,
                             notify=True, rpc=fake_rpc)

    assert len(calls) == 2
    assert result["status"] == "needs_user"
    assert result["reason"] == "post_repair_verification_failed"
    assert hooks.read_bytes() == original
    assert list(tmp_path.glob("hooks.json.tranfu-guard.bak.*"))


def test_run_check_repairs_and_verifies_with_codex_runtime_facts(tmp_path, monkeypatch):
    document, before, trusted = _permuted_fixture()
    hooks = tmp_path / "hooks.json"
    config = tmp_path / "config.toml"
    state = tmp_path / "state.json"
    binary = tmp_path / "codex"
    hooks.write_text(json.dumps(document), encoding="utf-8")
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    actual_source = str(hooks)
    for item in before["hooks"]:
        item["sourcePath"] = actual_source
        item["key"] = item["key"].replace(SOURCE, actual_source)
    trusted = {key.replace(SOURCE, actual_source): value for key, value in trusted.items()}
    _write_config(config, trusted)
    after = {"hooks": [
        {
            **_hook(0, THIRD, "sha256:third", trust="trusted", enabled=True),
            "sourcePath": actual_source,
            "key": f"{actual_source}:pre_tool_use:0:0",
        },
        {
            **_hook(1, TRANFU, "sha256:tranfu", trust="trusted", enabled=True),
            "sourcePath": actual_source,
            "key": f"{actual_source}:pre_tool_use:1:0",
        },
    ]}
    responses = iter([before, after])
    monkeypatch.setattr(guard, "_notify_user",
                        lambda _message: (_ for _ in ()).throw(AssertionError("must not notify")))

    result = guard.run_check(
        hooks, config, state, str(binary), tmp_path, rpc=lambda *_args: next(responses)
    )

    assert result["status"] == "repaired"
    repaired = json.loads(hooks.read_text(encoding="utf-8"))
    assert repaired["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == THIRD
    assert repaired["hooks"]["PreToolUse"][1]["thirdPartyField"] == "keep"
    assert json.loads(state.read_text(encoding="utf-8"))["status"] == "repaired"


def test_invalid_hooks_json_notifies_once_without_rewriting(tmp_path, monkeypatch):
    hooks = tmp_path / "hooks.json"
    state = tmp_path / "state.json"
    hooks.write_text("{broken", encoding="utf-8")
    notices = []
    monkeypatch.setattr(guard, "_notify_user", lambda message: notices.append(message) or True)

    first = guard.run_check(hooks, tmp_path / "config.toml", state, notify=True)
    second = guard.run_check(hooks, tmp_path / "config.toml", state, notify=True)

    assert first["status"] == "needs_user"
    assert second["notified"] is False
    assert notices and len(notices) == 1
    assert hooks.read_text(encoding="utf-8") == "{broken"


def test_notification_fingerprint_dedupes_and_health_resets(tmp_path, monkeypatch):
    _document, entry, _trusted = _permuted_fixture()
    state = tmp_path / "state.json"
    notices = []
    monkeypatch.setattr(guard, "_notify_user", lambda message: notices.append(message) or True)

    first = guard._needs_user_result("new_hash", entry, SOURCE, state, notify=True)
    second = guard._needs_user_result("new_hash", entry, SOURCE, state, notify=True)
    assert first["notified"] is True
    assert second["notified"] is False
    assert len(notices) == 1

    guard._save_result(state, {"status": "healthy", "reason": "ok"},
                       clear_notification=True)
    third = guard._needs_user_result("new_hash", entry, SOURCE, state, notify=True)
    assert third["notified"] is True
    assert len(notices) == 2


def test_launch_agent_install_is_idempotent_and_uninstall_is_managed_only(tmp_path, monkeypatch):
    plist = tmp_path / "guard.plist"
    hooks = tmp_path / "hooks.json"
    config = tmp_path / "config.toml"
    state = tmp_path / "state.json"
    codex = tmp_path / "codex"
    hooks.write_text("{}", encoding="utf-8")
    config.write_text("", encoding="utf-8")
    codex.write_text("#!/bin/sh\n", encoding="utf-8")
    codex.chmod(0o755)
    launch_calls = []
    monkeypatch.setattr(guard.sys, "platform", "darwin")
    monkeypatch.setattr(guard, "_launchctl", lambda args: launch_calls.append(args) or True)

    first = guard.install_launch_agent(plist, hooks, config, state, str(codex), tmp_path)
    first_call_count = len(launch_calls)
    second = guard.install_launch_agent(plist, hooks, config, state, str(codex), tmp_path)
    payload = plistlib.loads(plist.read_bytes())
    assert first == {"status": "installed", "changed": True, "plist": str(plist)}
    assert second["changed"] is False
    assert payload["Label"] == guard.LABEL
    assert payload["RunAtLoad"] is True
    assert payload["StartInterval"] == 300
    assert payload["WatchPaths"] == [str(hooks.resolve())]
    assert all(Path(value).is_absolute() for value in payload["ProgramArguments"][:2])
    assert any(call[0] == "bootstrap" for call in launch_calls)
    assert len(launch_calls) == first_call_count + 1
    assert launch_calls[-1][0] == "print"

    removed = guard.uninstall_launch_agent(plist)
    assert removed["status"] == "uninstalled" and not plist.exists()

    plist.write_bytes(plistlib.dumps({"Label": "someone.else"}))
    refused = guard.uninstall_launch_agent(plist)
    assert refused["status"] == "invalid" and plist.exists()


def test_fallback_parser_reads_nested_hook_state_tables(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        '[hooks.state."/tmp/hooks.json:stop:0:0"]\n'
        'trusted_hash = "sha256:abc"\n',
        encoding="utf-8",
    )
    assert guard.load_trusted_hashes(config) == {
        "/tmp/hooks.json:stop:0:0": "sha256:abc",
    }


def test_resolve_codex_preserves_stable_symlink(tmp_path):
    versioned = tmp_path / "codex-0.144.1"
    stable = tmp_path / "codex"
    versioned.write_text("#!/bin/sh\n", encoding="utf-8")
    versioned.chmod(0o755)
    stable.symlink_to(versioned)

    assert guard._resolve_codex(str(stable)) == str(stable)
