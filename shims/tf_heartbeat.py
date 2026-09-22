#!/usr/bin/env python3
"""Best-effort per-session turn heartbeat daemon.

The hook process only creates/updates a small state file and returns.  A
detached child owns the periodic reports, so a slow network request can never
stall Claude/Codex.  Periodic heartbeats are sent through tf_report's
``--no-spool`` path; terminal idle recovery remains reliable and may use the
normal spool.

This module deliberately uses only the Python standard library.  Every public
entry point is fail-silent because telemetry must never affect the host agent.
"""
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(os.environ.get("TF_TRANFU_HOME") or (Path.home() / ".tranfu"))
STATE_DIR = Path(os.environ.get("TF_HEARTBEAT_DIR") or (ROOT / "heartbeats"))
LOCK_WAIT_SECONDS = 0.5
LOCK_STALE_SECONDS = 10.0
CONTROL_POLL_SECONDS = 0.25
REPORT_TIMEOUT_SECONDS = 8.0
TOMBSTONE_SECONDS = 86400.0


def _env_float(name, default, minimum):
    try:
        value = float(os.environ.get(name, default))
    except Exception:
        value = float(default)
    return max(float(minimum), value)


def _interval_seconds():
    return _env_float("TF_HEARTBEAT_INTERVAL_SECONDS", 60.0, 1.0)


def _ttl_seconds():
    return _env_float("TF_HEARTBEAT_TTL_SECONDS", 1800.0, 1.0)


def _max_silence_seconds():
    return _env_float("TF_HEARTBEAT_MAX_SILENCE_SECONDS", 14400.0, 60.0)


def _request_ns(value=None):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else time.time_ns()
    except Exception:
        return time.time_ns()


def _state_key(session_id):
    return hashlib.sha256(str(session_id).encode("utf-8", "replace")).hexdigest()


def _state_path(session_id):
    return STATE_DIR / (_state_key(session_id) + ".json")


def _lock_path(session_id):
    return STATE_DIR / (_state_key(session_id) + ".lock")


def _ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path):
    try:
        with path.open(encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _write_json(path, value):
    try:
        _ensure_state_dir()
        tmp = path.with_name("." + path.name + ".%s.tmp" % os.getpid())
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        os.replace(str(tmp), str(path))
        return True
    except Exception:
        try:
            tmp.unlink()
        except Exception:
            pass
        return False


def _remove_if_same(path, generation, pid):
    try:
        state = _read_json(path)
        if (state and state.get("generation") == generation
                and int(state.get("pid") or 0) == int(pid)):
            path.unlink(missing_ok=True)
    except Exception:
        pass


def _finalize_state(session_id, generation, pid):
    """Remove an active generation or retain its short terminal tombstone."""
    with _state_lock(session_id) as acquired:
        if not acquired:
            return
        path = _state_path(session_id)
        state = _read_json(path)
        if not _state_matches(state, session_id, generation, pid):
            return
        if state.get("stop_requested") or state.get("stopped_at_ns"):
            state = dict(state)
            state["pid"] = 0
            state["lease_expires"] = 0
            state["activity_deadline"] = 0
            state["tombstone_expires"] = time.time() + TOMBSTONE_SECONDS
            _write_json(path, state)
        else:
            path.unlink(missing_ok=True)


@contextmanager
def _state_lock(session_id):
    """Short directory lock; stale lock recovery is bounded and fail-silent."""
    path = _lock_path(session_id)
    acquired = False
    try:
        _ensure_state_dir()
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while time.monotonic() < deadline:
            try:
                path.mkdir()
                acquired = True
                break
            except FileExistsError:
                try:
                    if time.time() - path.stat().st_mtime > LOCK_STALE_SECONDS:
                        path.rmdir()
                        continue
                except Exception:
                    pass
                time.sleep(0.01)
            except Exception:
                break
        yield acquired
    except Exception:
        yield False
    finally:
        if acquired:
            try:
                path.rmdir()
            except Exception:
                pass


def _prune_expired_tombstones():
    """Best-effort hourly cleanup; never remove a live daemon generation."""
    try:
        _ensure_state_dir()
        marker = STATE_DIR / ".tombstone-prune"
        now = time.time()
        try:
            if now - marker.stat().st_mtime < 3600:
                return
        except FileNotFoundError:
            pass
        marker.touch()
        for path in STATE_DIR.glob("*.json"):
            state = _read_json(path)
            if not state or not state.get("stop_requested"):
                continue
            if float(state.get("tombstone_expires") or 0) > now:
                continue
            session_id = state.get("session_id")
            if not session_id:
                continue
            with _state_lock(session_id) as acquired:
                latest = _read_json(path) if acquired else None
                if (latest and latest.get("stop_requested")
                        and float(latest.get("tombstone_expires") or 0) <= now
                        and not _pid_alive(latest.get("pid"))):
                    path.unlink(missing_ok=True)
    except Exception:
        pass


def _pid_alive(pid):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def process_start_token(pid):
    """Return a normalized ps start token, or None when unavailable."""
    try:
        proc = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(int(pid))],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=1,
        )
        if proc.returncode != 0:
            return None
        token = " ".join((proc.stdout or "").split())
        return token or None
    except Exception:
        return None


_WRAPPER_PROCESS_NAMES = frozenset({
    "sh", "bash", "zsh", "dash", "ksh", "fish", "python", "python3",
})


def _ps_field(pid, field):
    try:
        proc = subprocess.run(
            ["ps", "-o", f"{field}=", "-p", str(int(pid))],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=1,
        )
        if proc.returncode != 0:
            return ""
        return " ".join((proc.stdout or "").split())
    except Exception:
        return ""


def _resolve_owner_pid(pid):
    """Resolve shell/python hook wrappers outside the host hook process."""
    try:
        current = int(pid or 0)
    except Exception:
        return 0
    if current <= 0 or not _pid_alive(current):
        # A wrapper that already exited cannot be climbed, and treating its
        # dead PID as the owner would end the turn on the first daemon check.
        # Unknown owner falls back to the lease TTL instead.
        return 0
    for _ in range(3):
        name = os.path.basename(_ps_field(current, "comm")).casefold()
        if not name or (name not in _WRAPPER_PROCESS_NAMES
                        and not name.startswith("python")):
            break
        try:
            parent = int(_ps_field(current, "ppid"))
        except Exception:
            break
        if parent <= 1 or parent == current:
            break
        current = parent
    return current if _pid_alive(current) else 0


def _owner_status(state):
    """Return (state, reliable): alive/dead/unknown plus check reliability."""
    try:
        owner_pid = int(state.get("owner_pid") or 0)
    except Exception:
        owner_pid = 0
    if owner_pid <= 0:
        return "unknown", False
    try:
        os.kill(owner_pid, 0)
    except ProcessLookupError:
        return "dead", True
    except PermissionError:
        return "unknown", False
    except Exception:
        return "unknown", False

    expected = str(state.get("owner_token") or "")
    if not expected:
        return "alive", False
    actual = process_start_token(owner_pid)
    if not actual:
        return "unknown", False
    return ("alive", True) if actual == expected else ("dead", True)


def _report(args, *, no_spool=False):
    """Run tf_report detached from the hook; only the daemon may wait here."""
    script = Path(__file__).with_name("tf_report.py")
    argv = [sys.executable, str(script)] + list(args)
    if no_spool:
        argv.append("--no-spool")
    try:
        subprocess.run(argv, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=REPORT_TIMEOUT_SECONDS)
    except Exception:
        pass


def _terminal_idle(session_id, step):
    _report(["--status", "idle", "--step", step, "--session", str(session_id)])


def _state_matches(state, session_id, generation, pid=None):
    if not state or state.get("session_id") != str(session_id):
        return False
    if state.get("generation") != generation:
        return False
    return pid is None or int(state.get("pid") or 0) == int(pid)


def _stop_requested(session_id, generation):
    state = _read_json(_state_path(session_id))
    return bool(_state_matches(state, session_id, generation)
                and state.get("stop_requested"))


def _renew_lease(session_id, generation, state):
    # Merge under the same lock used by stop_session. Otherwise a concurrent
    # renew could replace a freshly written stop_requested marker.
    with _state_lock(session_id) as acquired:
        if not acquired:
            return
        path = _state_path(session_id)
        latest = _read_json(path)
        if not _state_matches(latest, session_id, generation) or latest.get("stop_requested"):
            return
        latest = dict(latest)
        latest["lease_expires"] = time.time() + _ttl_seconds()
        _write_json(path, latest)


def _ensure_activity_deadline(session_id, generation, state):
    """Upgrade a legacy state once; daemon renewals never move this deadline."""
    try:
        deadline = float(state.get("activity_deadline") or 0)
    except Exception:
        deadline = 0
    if deadline > 0:
        return deadline
    with _state_lock(session_id) as acquired:
        if not acquired:
            return time.time() + _max_silence_seconds()
        path = _state_path(session_id)
        latest = _read_json(path)
        if not _state_matches(latest, session_id, generation) or latest.get("stop_requested"):
            return 0
        try:
            deadline = float(latest.get("activity_deadline") or 0)
        except Exception:
            deadline = 0
        if deadline <= 0:
            trusted = time.time()
            latest = dict(latest)
            latest["last_trusted_activity"] = trusted
            latest["activity_deadline"] = trusted + _max_silence_seconds()
            _write_json(path, latest)
            deadline = latest["activity_deadline"]
        return deadline


def _mark_terminal(session_id, generation, reason, request_at_ns=None):
    """Claim one terminal transition before reporting it."""
    with _state_lock(session_id) as acquired:
        if not acquired:
            return False
        path = _state_path(session_id)
        state = _read_json(path)
        if not _state_matches(state, session_id, generation):
            return False
        if state.get("stop_requested") or state.get("stopped_at_ns"):
            return False
        state = dict(state)
        state["stop_requested"] = True
        state["stopped_at_ns"] = _request_ns(request_at_ns)
        state["terminal_reason"] = reason
        _write_json(path, state)
        return True


def _wait_for_next(session_id, generation, interval, stop_flag):
    deadline = time.monotonic() + interval
    while time.monotonic() < deadline:
        if stop_flag[0] or _stop_requested(session_id, generation):
            return False
        time.sleep(min(CONTROL_POLL_SECONDS, max(0.01, deadline - time.monotonic())))
    return True


def _daemon(session_id, generation):
    stop_flag = [False]

    def request_stop(_signum, _frame):
        stop_flag[0] = True

    try:
        signal.signal(signal.SIGTERM, request_stop)
    except Exception:
        pass

    path = _state_path(session_id)
    try:
        while True:
            state = _read_json(path)
            if not _state_matches(state, session_id, generation, os.getpid()):
                return
            if stop_flag[0] or state.get("stop_requested"):
                return

            now = time.time()
            deadline = _ensure_activity_deadline(session_id, generation, state)
            if deadline <= 0:
                return
            if now >= deadline:
                if _mark_terminal(session_id, generation, "activity_deadline"):
                    _terminal_idle(session_id, "heartbeat activity deadline")
                return

            owner_state, reliable = _owner_status(state)
            if owner_state == "dead":
                if _mark_terminal(session_id, generation, "owner_exited"):
                    _terminal_idle(session_id, "heartbeat owner exited")
                return
            if reliable:
                # The daemon, not a rare hook event, keeps a healthy long turn
                # alive. This is deliberately the only normal lease renewal.
                _renew_lease(session_id, generation, state)
            elif now >= float(state.get("lease_expires") or 0):
                if _mark_terminal(session_id, generation, "ttl_expired"):
                    _terminal_idle(session_id, "heartbeat ttl expired")
                return

            _report(["--status", "running", "--step", "turn heartbeat",
                     "--session", str(session_id)], no_spool=True)
            if not _wait_for_next(session_id, generation, _interval_seconds(), stop_flag):
                return
    except Exception:
        return
    finally:
        _finalize_state(session_id, generation, os.getpid())


def start_session(session_id, owner_pid=0, request_at_ns=None):
    session_id = str(session_id or "")
    if not session_id:
        return False
    _prune_expired_tombstones()
    requested = _request_ns(request_at_ns)
    with _state_lock(session_id) as acquired:
        if not acquired:
            return False
        path = _state_path(session_id)
        old = _read_json(path)
        try:
            stopped_at = int((old or {}).get("stopped_at_ns") or 0)
        except Exception:
            stopped_at = 0
        if stopped_at and requested <= stopped_at:
            return False
        now = time.time()
        if (old and not old.get("stop_requested")
                and _pid_alive(old.get("pid"))):
            old = dict(old)
            old["request_at_ns"] = requested
            old["last_trusted_activity"] = now
            old["activity_deadline"] = now + _max_silence_seconds()
            old["lease_expires"] = now + _ttl_seconds()
            _write_json(path, old)
            return False
        generation = uuid.uuid4().hex
        try:
            owner_pid = _resolve_owner_pid(owner_pid)
        except Exception:
            owner_pid = 0
        state = {
            "session_id": session_id,
            "generation": generation,
            "pid": 0,
            "owner_pid": owner_pid,
            "owner_token": process_start_token(owner_pid) if owner_pid > 0 else "",
            "request_at_ns": requested,
            "last_trusted_activity": now,
            "activity_deadline": now + _max_silence_seconds(),
            "lease_expires": now + _ttl_seconds(),
            "stop_requested": False,
            "stopped_at_ns": 0,
        }
        if not _write_json(path, state):
            return False
        try:
            proc = subprocess.Popen(
                [sys.executable, str(Path(__file__)), "daemon",
                 "--session", session_id, "--generation", generation],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True,
            )
            state["pid"] = proc.pid
            _write_json(path, state)
            return True
        except Exception:
            _remove_if_same(path, generation, 0)
            return False


def stop_session(session_id, request_at_ns=None):
    session_id = str(session_id or "")
    if not session_id:
        return False
    _prune_expired_tombstones()
    requested = _request_ns(request_at_ns)
    with _state_lock(session_id) as acquired:
        if not acquired:
            return False
        path = _state_path(session_id)
        state = _read_json(path)
        if not state:
            state = {
                "session_id": session_id,
                "generation": "",
                "pid": 0,
                "request_at_ns": requested,
                "stopped_at_ns": requested,
                "stop_requested": True,
                "tombstone_expires": time.time() + TOMBSTONE_SECONDS,
            }
            return _write_json(path, state)
        try:
            stopped_at = int(state.get("stopped_at_ns") or 0)
        except Exception:
            stopped_at = 0
        if stopped_at >= requested:
            return True
        state = dict(state)
        state["stop_requested"] = True
        state["request_at_ns"] = max(int(state.get("request_at_ns") or 0), requested)
        state["stopped_at_ns"] = requested
        state["tombstone_expires"] = time.time() + TOMBSTONE_SECONDS
        # No wait and no kill: the daemon polls this marker at most every
        # CONTROL_POLL_SECONDS, and if it is in _report it exits after the
        # report's own bounded timeout. This keeps the hook non-blocking and
        # avoids ever signalling a recycled PID.
        _write_json(path, state)
        return True


def main(argv=None):
    try:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command", required=True)
        start = sub.add_parser("start")
        start.add_argument("--session", required=True)
        start.add_argument("--owner-pid", type=int, default=0)
        start.add_argument("--request-at-ns", type=int, default=0)
        stop = sub.add_parser("stop")
        stop.add_argument("--session", required=True)
        stop.add_argument("--request-at-ns", type=int, default=0)
        daemon = sub.add_parser("daemon")
        daemon.add_argument("--session", required=True)
        daemon.add_argument("--generation", required=True)
        args = parser.parse_args(argv)
        if args.command == "start":
            start_session(args.session, args.owner_pid, args.request_at_ns)
        elif args.command == "stop":
            stop_session(args.session, args.request_at_ns)
        else:
            _daemon(args.session, args.generation)
        return 0
    except BaseException:
        # Even malformed internal state must never break the host hook.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
