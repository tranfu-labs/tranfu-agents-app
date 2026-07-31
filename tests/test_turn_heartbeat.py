"""Turn heartbeat lifecycle, no-spool transport and quality-safe idle closure."""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shims"))

import tf_heartbeat
import tf_hook
import tf_report
from conftest import ev


class _Proc:
    def __init__(self, pid):
        self.pid = pid


@pytest.fixture
def heartbeat_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tf_heartbeat, "STATE_DIR", tmp_path / "heartbeats")
    return tmp_path / "heartbeats"


def test_same_session_start_is_idempotent_and_other_sessions_are_independent(
        heartbeat_dir, monkeypatch):
    pids = iter((101, 102))
    spawned = []
    monkeypatch.setattr(tf_heartbeat, "_pid_alive", lambda pid: int(pid) in {101, 102})
    monkeypatch.setattr(tf_heartbeat, "process_start_token", lambda _pid: "owner-start")
    monkeypatch.setattr(tf_heartbeat, "_resolve_owner_pid", lambda pid: int(pid or 0))
    monkeypatch.setattr(
        tf_heartbeat.subprocess, "Popen",
        lambda *args, **kwargs: spawned.append(args[0]) or _Proc(next(pids)),
    )

    assert tf_heartbeat.start_session("s1", 55) is True
    assert tf_heartbeat.start_session("s1", 55) is False
    assert tf_heartbeat.start_session("s2", 55) is True

    assert len(spawned) == 2
    assert len(list(heartbeat_dir.glob("*.json"))) == 2


def test_stop_only_writes_drain_marker_and_returns_without_waiting(heartbeat_dir):
    path = tf_heartbeat._state_path("s1")
    state = {
        "session_id": "s1", "generation": "g1", "pid": 123,
        "owner_pid": 55, "owner_token": "owner-start",
        "lease_expires": time.time() + 100, "stop_requested": False,
    }
    assert tf_heartbeat._write_json(path, state)

    started = time.monotonic()
    assert tf_heartbeat.stop_session("s1") is True
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert tf_heartbeat._read_json(path)["stop_requested"] is True


def test_heartbeat_report_adds_no_spool_without_touching_shared_spool(
        monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(tf_heartbeat.subprocess, "run",
                        lambda args, **kwargs: calls.append(args))

    tf_heartbeat._report(["--status", "running", "--session", "s1"], no_spool=True)

    assert calls and calls[0][-1] == "--no-spool"


def test_report_no_spool_drops_failure_without_flush_or_append(monkeypatch, tmp_path):
    monkeypatch.setenv("TF_SERVER", "http://127.0.0.1:9")
    monkeypatch.setattr(tf_report, "SPOOL", str(tmp_path / "spool.ndjson"))
    monkeypatch.setattr(tf_report, "_post", lambda *_args: False)
    monkeypatch.setattr(tf_report, "_flush_spool",
                        lambda *_args: pytest.fail("heartbeat must not flush spool"))
    monkeypatch.setattr(tf_report, "_spool_append",
                        lambda *_args: pytest.fail("heartbeat must not append spool"))
    monkeypatch.setattr(sys, "argv", [
        "tf_report.py", "--status", "running", "--session", "s1", "--no-spool",
    ])

    tf_report.main()

    assert not (tmp_path / "spool.ndjson").exists()


def test_reliable_owner_check_renews_lease_and_unavailable_check_does_not(
        heartbeat_dir, monkeypatch):
    path = tf_heartbeat._state_path("s1")
    state = {
        "session_id": "s1", "generation": "g1", "pid": 123,
        "owner_pid": 55, "owner_token": "owner-start",
        "lease_expires": 1.0, "stop_requested": False,
    }
    assert tf_heartbeat._write_json(path, state)
    monkeypatch.setattr(tf_heartbeat.os, "kill", lambda *_args: None)
    monkeypatch.setattr(tf_heartbeat, "process_start_token", lambda _pid: "owner-start")
    monkeypatch.setattr(tf_heartbeat.time, "time", lambda: 100.0)

    status, reliable = tf_heartbeat._owner_status(state)
    assert (status, reliable) == ("alive", True)
    tf_heartbeat._renew_lease("s1", "g1", state)
    renewed = tf_heartbeat._read_json(path)
    assert renewed["lease_expires"] > 100.0

    monkeypatch.setattr(tf_heartbeat, "process_start_token", lambda _pid: None)
    status, reliable = tf_heartbeat._owner_status(state)
    assert (status, reliable) == ("unknown", False)


def test_daemon_self_renews_reliable_owner_during_long_turn(heartbeat_dir, monkeypatch):
    path = tf_heartbeat._state_path("long-turn")
    state = {
        "session_id": "long-turn", "generation": "g1", "pid": os.getpid(),
        "owner_pid": 55, "owner_token": "owner-start",
        "lease_expires": 1.0, "stop_requested": False,
    }
    assert tf_heartbeat._write_json(path, state)
    renewed = []
    original_renew = tf_heartbeat._renew_lease
    monkeypatch.setattr(tf_heartbeat, "_owner_status", lambda _state: ("alive", True))
    monkeypatch.setattr(tf_heartbeat, "_renew_lease",
                        lambda *args: renewed.append(True) or original_renew(*args))

    def fake_report(_args, **_kwargs):
        current = tf_heartbeat._read_json(path)
        current["stop_requested"] = True
        tf_heartbeat._write_json(path, current)

    monkeypatch.setattr(tf_heartbeat, "_report", fake_report)

    tf_heartbeat._daemon("long-turn", "g1")

    assert renewed
    assert not path.exists()


def test_unavailable_owner_uses_absolute_ttl_and_sends_idle_once(
        heartbeat_dir, monkeypatch):
    path = tf_heartbeat._state_path("ttl-close")
    state = {
        "session_id": "ttl-close", "generation": "g1", "pid": os.getpid(),
        "owner_pid": 55, "owner_token": "owner-start",
        "lease_expires": 1.0, "stop_requested": False,
    }
    assert tf_heartbeat._write_json(path, state)
    terminal = []
    monkeypatch.setattr(tf_heartbeat, "_owner_status", lambda _state: ("unknown", False))
    monkeypatch.setattr(tf_heartbeat, "_terminal_idle",
                        lambda session, step: terminal.append((session, step)))

    tf_heartbeat._daemon("ttl-close", "g1")

    assert terminal == [("ttl-close", "heartbeat ttl expired")]
    assert not path.exists()


def test_hook_stop_launches_nonblocking_drain_and_start_has_owner(monkeypatch):
    calls = []
    monkeypatch.setattr(tf_hook.os, "getppid", lambda: 456)
    monkeypatch.setattr(tf_hook.os.path, "exists", lambda path: path.endswith("tf_heartbeat.py"))
    monkeypatch.setattr(tf_hook.subprocess, "Popen",
                        lambda args, **kwargs: calls.append((args, kwargs)) or _Proc(1))

    tf_hook._heartbeat_action("start", {
        "hook_event_name": "UserPromptSubmit", "session_id": "s1",
    })
    tf_hook._heartbeat_action("stop", {
        "hook_event_name": "Stop", "session_id": "s1",
    })

    assert len(calls) == 2
    assert calls[0][0][2:4] == ["start", "--session"]
    assert calls[1][0][2:4] == ["stop", "--session"]
    assert all(call[1]["start_new_session"] is True for call in calls)


def test_hook_without_session_does_not_start_or_stop(monkeypatch):
    monkeypatch.setattr(tf_hook.subprocess, "Popen",
                        lambda *_args, **_kwargs: pytest.fail("no session must be a no-op"))
    tf_hook._heartbeat_action("start", {"hook_event_name": "PreToolUse"})
    tf_hook._heartbeat_action("stop", {"hook_event_name": "SessionEnd"})


def test_idle_terminal_closes_active_card_without_error_quality(client):
    ev(client, session_id="idle-close", current_step="work", status="running")
    ev(client, session_id="idle-close", current_step="owner exited", status="idle")

    card = next(item for item in client.get("/api/state").json()["sessions"]
                if item["operator"] == "alice")
    assert card["status"] == "idle"
    assert card["quality"]["runs"] == 0
    assert card["quality"]["error"] == 0
