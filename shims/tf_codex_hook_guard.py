#!/usr/bin/env python3
"""Keep trusted Codex user hooks healthy without granting new trust.

Codex persists hook trust against positional handler keys.  When another
installer only reorders whole hook groups, unchanged handlers can therefore be
reported as ``modified`` and stop running.  This guard asks Codex for its own
hook hashes and only repairs a complete, unique permutation of hashes that were
already trusted.  New content is never trusted automatically.

The module is stdlib-only and best-effort: failures are recorded locally and
never raise into the host agent.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import plistlib
import re
import select
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = 1
LABEL = "com.tranfu.codex-hook-guard"
TRANFU_MARKER = "tf_hook.py"
CHECK_INTERVAL = 300
RPC_TIMEOUT = 12.0

TRANFU_HOME = Path(os.environ.get("TF_TRANFU_HOME") or Path.home() / ".tranfu")
HOOKS_PATH = Path.home() / ".codex" / "hooks.json"
CONFIG_PATH = Path.home() / ".codex" / "config.toml"
STATE_PATH = TRANFU_HOME / "codex-hook-guard-state.json"
LOCK_PATH = TRANFU_HOME / ".codex-hook-guard.lock"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


class GuardError(RuntimeError):
    """A guarded refusal or compatibility failure."""

    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = str(code)


def _utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(str(tmp), str(path))


def _fingerprint(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _acquire_lock(path=LOCK_PATH):
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(fd, str(os.getpid()).encode("ascii"))
        return fd
    except FileExistsError:
        try:
            if time.time() - path.stat().st_mtime > 120:
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


def _resolve_codex(explicit=""):
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("TF_CODEX_BIN"):
        candidates.append(os.environ["TF_CODEX_BIN"])
    found = shutil.which("codex")
    if found:
        candidates.append(found)
    candidates.extend([
        str(Path.home() / ".local" / "bin" / "codex"),
        "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex",
        "/Applications/Codex.app/Contents/Resources/codex",
    ])
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            # Keep a stable package-manager symlink (for example
            # /opt/homebrew/bin/codex) instead of pinning a versioned Caskroom
            # target that disappears on the next Codex upgrade.
            return os.path.abspath(str(path))
    raise GuardError("codex_not_found")


def _read_response(proc, request_id, deadline):
    if proc.stdout is None:
        raise GuardError("app_server_no_stdout")
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GuardError("app_server_timeout")
        ready, _, _ = select.select([proc.stdout], [], [], remaining)
        if not ready:
            continue
        line = proc.stdout.readline()
        if not line:
            raise GuardError("app_server_closed")
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if payload.get("id") != request_id:
            continue
        if payload.get("error") is not None:
            raise GuardError("app_server_method_error")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise GuardError("app_server_bad_result")
        return result


def hooks_list(cwd, codex_bin="", timeout=RPC_TIMEOUT):
    """Return the single cwd entry from Codex ``hooks/list``."""
    binary = _resolve_codex(codex_bin)
    try:
        proc = subprocess.Popen(
            [binary, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:
        raise GuardError("app_server_start_failed", type(exc).__name__) from exc
    deadline = time.monotonic() + float(timeout)
    try:
        if proc.stdin is None:
            raise GuardError("app_server_no_stdin")
        requests = (
            (1, "initialize", {
                "clientInfo": {"name": "tranfu-codex-hook-guard", "version": "1"},
            }),
            (2, "hooks/list", {"cwds": [str(cwd)]}),
        )
        results = {}
        for request_id, method, params in requests:
            proc.stdin.write(json.dumps({
                "id": request_id, "method": method, "params": params,
            }) + "\n")
            proc.stdin.flush()
            results[request_id] = _read_response(proc, request_id, deadline)
        data = results[2].get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise GuardError("hooks_list_bad_data")
        entry = data[0]
        if entry.get("errors"):
            raise GuardError("hooks_list_errors")
        if not isinstance(entry.get("hooks"), list):
            raise GuardError("hooks_list_missing_hooks")
        return entry
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass


_STATE_SECTION = re.compile(r'^\[hooks\.state\."((?:[^"\\]|\\.)*)"\]\s*(?:#.*)?$')
_TRUSTED_HASH = re.compile(r'^trusted_hash\s*=\s*"((?:[^"\\]|\\.)*)"\s*(?:#.*)?$')


def _fallback_trusted_hashes(text):
    result = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        section = _STATE_SECTION.match(line)
        if section:
            try:
                current = json.loads('"' + section.group(1) + '"')
            except Exception:
                current = None
            continue
        if line.startswith("["):
            current = None
            continue
        match = _TRUSTED_HASH.match(line)
        if current and match:
            try:
                result[current] = json.loads('"' + match.group(1) + '"')
            except Exception:
                pass
    return result


def load_trusted_hashes(path=CONFIG_PATH):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except Exception as exc:
        raise GuardError("config_unreadable") from exc
    try:
        import tomllib
        config = tomllib.loads(raw.decode("utf-8"))
        state = config.get("hooks", {}).get("state", {})
        result = {
            key: value.get("trusted_hash")
            for key, value in state.items()
            if isinstance(key, str) and isinstance(value, dict)
            and isinstance(value.get("trusted_hash"), str)
        }
    except Exception:
        result = _fallback_trusted_hashes(raw.decode("utf-8", errors="replace"))
    if not result:
        raise GuardError("trusted_state_missing")
    return result


def _source_hooks(entry, hooks_path):
    want = os.path.realpath(str(Path(hooks_path).expanduser()))
    result = []
    for hook in entry.get("hooks", []):
        if not isinstance(hook, dict) or hook.get("source") != "user":
            continue
        source = hook.get("sourcePath")
        if isinstance(source, str) and os.path.realpath(source) == want:
            result.append(hook)
    return result


def _is_tranfu(hook):
    command = hook.get("command") if isinstance(hook, dict) else None
    return isinstance(command, str) and TRANFU_MARKER in command.replace("\\", "/")


def _event_token(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _json_event_key(hooks_object, event_name):
    matches = [key for key in hooks_object if _event_token(key) == _event_token(event_name)]
    if len(matches) != 1:
        raise GuardError("event_name_ambiguous")
    return matches[0]


def _handler_position(key):
    try:
        prefix, group, handler = str(key).rsplit(":", 2)
        return prefix, int(group), int(handler)
    except Exception as exc:
        raise GuardError("unsupported_handler_key") from exc


def _group_vectors(groups, event_metadata, trusted):
    current = {}
    prefixes = set()
    for hook in event_metadata:
        prefix, group_index, handler_index = _handler_position(hook.get("key"))
        value = hook.get("currentHash")
        if not isinstance(value, str) or not value:
            raise GuardError("current_hash_missing")
        pos = (group_index, handler_index)
        if pos in current:
            raise GuardError("duplicate_handler_position")
        current[pos] = value
        prefixes.add(prefix)
    if len(prefixes) != 1:
        raise GuardError("handler_prefix_mismatch")
    prefix = next(iter(prefixes))

    current_vectors = []
    expected_positions = set()
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list) or not group["hooks"]:
            raise GuardError("unsupported_group_shape")
        current_vector = []
        for handler_index, _handler in enumerate(group["hooks"]):
            pos = (group_index, handler_index)
            expected_positions.add(pos)
            if pos not in current:
                raise GuardError("handler_metadata_incomplete")
            current_vector.append(current[pos])
        current_vectors.append(tuple(current_vector))
    if set(current) != expected_positions:
        raise GuardError("handler_metadata_mismatch")

    # Trusted positions describe the target shape.  Reconstruct them
    # independently: a whole-group permutation may move a two-handler group to
    # an index currently occupied by a one-handler group.
    trusted_positions = {}
    for key, value in trusted.items():
        if not isinstance(value, str) or not value:
            continue
        try:
            trusted_prefix, group_index, handler_index = _handler_position(key)
        except GuardError:
            continue
        if trusted_prefix == prefix:
            trusted_positions[(group_index, handler_index)] = value
    trusted_vectors = []
    group_indices = {group for group, _handler in trusted_positions}
    if group_indices != set(range(len(groups))):
        raise GuardError("trusted_hash_missing")
    for group_index in range(len(groups)):
        handlers = sorted(
            handler for group, handler in trusted_positions if group == group_index
        )
        if not handlers or handlers != list(range(len(handlers))):
            raise GuardError("trusted_hash_missing")
        trusted_vectors.append(tuple(
            trusted_positions[(group_index, handler)] for handler in handlers
        ))
    if sum(map(len, trusted_vectors)) != len(current):
        raise GuardError("trusted_handler_count_mismatch")
    return current_vectors, trusted_vectors


def build_reordered_document(document, entry, trusted, hooks_path=HOOKS_PATH):
    """Return ``(new_document, changed_event_names)`` for a pure permutation.

    The operation is deliberately all-or-nothing across unhealthy TRANFU
    events: if any event cannot be proven safe, no event is rewritten.
    """
    hooks_object = document.get("hooks") if isinstance(document, dict) else None
    if not isinstance(hooks_object, dict):
        raise GuardError("hooks_object_missing")
    metadata = _source_hooks(entry, hooks_path)
    tranfu = [hook for hook in metadata if _is_tranfu(hook)]
    if not tranfu:
        raise GuardError("tranfu_hooks_not_visible")
    unhealthy_events = {
        hook.get("eventName") for hook in tranfu
        if hook.get("trustStatus") != "trusted" or hook.get("enabled") is not True
    }
    if not unhealthy_events:
        return copy.deepcopy(document), []

    result = copy.deepcopy(document)
    result_hooks = result["hooks"]
    changed = []
    for event_name in sorted(unhealthy_events):
        json_name = _json_event_key(result_hooks, event_name)
        groups = result_hooks.get(json_name)
        if not isinstance(groups, list) or not groups:
            raise GuardError("event_groups_missing")
        event_metadata = [hook for hook in metadata if hook.get("eventName") == event_name]
        current_vectors, trusted_vectors = _group_vectors(groups, event_metadata, trusted)
        if len(set(current_vectors)) != len(current_vectors):
            raise GuardError("current_groups_not_unique")
        if len(set(trusted_vectors)) != len(trusted_vectors):
            raise GuardError("trusted_groups_not_unique")
        if set(current_vectors) != set(trusted_vectors):
            raise GuardError("not_a_trusted_permutation")
        if current_vectors == trusted_vectors:
            raise GuardError("unhealthy_without_permutation")
        target = {vector: index for index, vector in enumerate(trusted_vectors)}
        reordered = [None] * len(groups)
        for current_index, vector in enumerate(current_vectors):
            reordered[target[vector]] = groups[current_index]
        if any(group is None for group in reordered):
            raise GuardError("permutation_incomplete")
        result_hooks[json_name] = reordered
        changed.append(str(event_name))
    return result, changed


def _atomic_hooks_write(path, document):
    path = Path(path)
    mode = path.stat().st_mode
    tmp = path.with_name(path.name + ".tranfu-guard.tmp")
    tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.chmod(tmp, mode)
    os.replace(str(tmp), str(path))


def _backup_hooks(path):
    path = Path(path)
    base = path.with_name(path.name + f".tranfu-guard.bak.{_utc_timestamp()}")
    backup = base
    index = 1
    while backup.exists():
        backup = Path(str(base) + f".{index}")
        index += 1
    shutil.copy2(str(path), str(backup))
    return backup


def _restore_hooks_backup(path, backup):
    path = Path(path)
    backup = Path(backup)
    tmp = path.with_name(path.name + ".tranfu-guard-rollback.tmp")
    shutil.copy2(str(backup), str(tmp))
    os.replace(str(tmp), str(path))


def _summaries(entry, hooks_path):
    result = []
    for hook in _source_hooks(entry, hooks_path):
        if not _is_tranfu(hook):
            continue
        result.append({
            "event": hook.get("eventName"),
            "key": hook.get("key"),
            "hash": hook.get("currentHash"),
            "trust": hook.get("trustStatus"),
            "enabled": hook.get("enabled") is True,
        })
    return sorted(result, key=lambda item: (str(item["event"]), str(item["key"])))


def _all_healthy(entry, hooks_path, events=None):
    hooks = [hook for hook in _source_hooks(entry, hooks_path) if _is_tranfu(hook)]
    if events is not None:
        hooks = [hook for hook in hooks if hook.get("eventName") in set(events)]
    return bool(hooks) and all(
        hook.get("trustStatus") == "trusted" and hook.get("enabled") is True
        for hook in hooks
    )


def _notify_user(message):
    if sys.platform != "darwin" or not shutil.which("osascript"):
        return False
    script = (f'display notification {json.dumps(message, ensure_ascii=False)} '
              f'with title {json.dumps("TRANFU//AGENTS", ensure_ascii=False)}')
    try:
        proc = subprocess.run(["osascript", "-e", script], timeout=5,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return proc.returncode == 0
    except Exception:
        return False


def _save_result(state_path, result, notification_fingerprint=None, clear_notification=False):
    previous = _read_json(state_path) or {}
    state = {
        "schema": SCHEMA,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": result.get("status", "error"),
        "reason": result.get("reason", ""),
        "fingerprint": result.get("fingerprint", ""),
    }
    existing = previous.get("notified_fingerprint", "")
    if clear_notification:
        existing = ""
    if notification_fingerprint is not None:
        existing = notification_fingerprint
    if existing:
        state["notified_fingerprint"] = existing
    try:
        _write_json_atomic(state_path, state)
    except Exception:
        pass


def _needs_user_result(reason, entry, hooks_path, state_path, notify=True, detail=""):
    summaries = _summaries(entry, hooks_path) if isinstance(entry, dict) else []
    fingerprint = _fingerprint({"reason": reason, "hooks": summaries, "detail": detail})
    previous = _read_json(state_path) or {}
    notified = False
    stored = None
    if notify and previous.get("notified_fingerprint") != fingerprint:
        notified = _notify_user(
            "Codex Hook 需要检查：请打开 Codex 输入 /hooks，检查并信任 TRANFU Hook。"
        )
        if notified:
            stored = fingerprint
    result = {
        "status": "needs_user",
        "reason": reason,
        "fingerprint": fingerprint,
        "notified": notified,
        "hooks": summaries,
    }
    _save_result(state_path, result, notification_fingerprint=stored)
    return result


def run_check(hooks_path=HOOKS_PATH, config_path=CONFIG_PATH, state_path=STATE_PATH,
              codex_bin="", cwd="", notify=True, rpc=hooks_list):
    """Run one health check and return a machine-readable result."""
    hooks_path = Path(hooks_path).expanduser()
    config_path = Path(config_path).expanduser()
    state_path = Path(state_path).expanduser()
    lock_path = state_path.with_name("." + state_path.stem + ".lock")
    fd = _acquire_lock(lock_path)
    if fd is None:
        return {"status": "busy", "reason": "lock_held"}
    try:
        if not hooks_path.exists():
            result = {"status": "not_installed", "reason": "hooks_file_missing"}
            _save_result(state_path, result, clear_notification=True)
            return result
        try:
            document = json.loads(hooks_path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("not object")
        except Exception:
            try:
                detail = hashlib.sha256(hooks_path.read_bytes()).hexdigest()
            except Exception:
                detail = "unreadable"
            return _needs_user_result("hooks_json_invalid", None, hooks_path,
                                      state_path, notify, detail=detail)
        raw_text = json.dumps(document, ensure_ascii=False)
        if TRANFU_MARKER not in raw_text:
            result = {"status": "not_installed", "reason": "tranfu_hooks_absent"}
            _save_result(state_path, result, clear_notification=True)
            return result
        try:
            binary = _resolve_codex(codex_bin)
            entry = rpc(cwd or str(Path.home()), binary)
        except GuardError as exc:
            result = {"status": "unsupported", "reason": exc.code}
            _save_result(state_path, result)
            return result
        except Exception as exc:
            result = {"status": "error", "reason": type(exc).__name__}
            _save_result(state_path, result)
            return result
        if not [hook for hook in _source_hooks(entry, hooks_path) if _is_tranfu(hook)]:
            result = {"status": "unsupported", "reason": "tranfu_hooks_not_visible"}
            _save_result(state_path, result)
            return result
        if _all_healthy(entry, hooks_path):
            result = {
                "status": "healthy", "reason": "trusted_and_enabled",
                "hooks": _summaries(entry, hooks_path),
            }
            result["fingerprint"] = _fingerprint(result["hooks"])
            _save_result(state_path, result, clear_notification=True)
            return result

        try:
            trusted = load_trusted_hashes(config_path)
            repaired, changed_events = build_reordered_document(
                document, entry, trusted, hooks_path=hooks_path,
            )
        except GuardError as exc:
            return _needs_user_result(exc.code, entry, hooks_path, state_path, notify)

        backup = None
        try:
            backup = _backup_hooks(hooks_path)
            _atomic_hooks_write(hooks_path, repaired)
            after = rpc(cwd or str(Path.home()), binary)
            if not _all_healthy(after, hooks_path, events=changed_events):
                raise GuardError("post_repair_verification_failed")
        except Exception as exc:
            if backup is not None and backup.exists():
                try:
                    _restore_hooks_backup(hooks_path, backup)
                except Exception:
                    pass
            reason = exc.code if isinstance(exc, GuardError) else "repair_failed"
            return _needs_user_result(reason, entry, hooks_path, state_path, notify)

        result = {
            "status": "repaired",
            "reason": "trusted_permutation_restored",
            "changed_events": changed_events,
            "backup": str(backup),
            "hooks": _summaries(after, hooks_path),
        }
        result["fingerprint"] = _fingerprint(result["hooks"])
        _save_result(state_path, result, clear_notification=True)
        return result
    finally:
        _release_lock(fd, lock_path)


def _launchctl(args):
    try:
        return subprocess.run(["launchctl"] + list(args), timeout=8,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    except Exception:
        return False


def _plist_payload(hooks_path, config_path, state_path, codex_bin, cwd):
    script = str(Path(__file__).resolve())
    python = str(Path(sys.executable).resolve())
    return {
        "Label": LABEL,
        "ProgramArguments": [
            python, script, "check",
            "--hooks", str(Path(hooks_path).expanduser().resolve()),
            "--config", str(Path(config_path).expanduser().resolve()),
            "--state", str(Path(state_path).expanduser().resolve()),
            "--codex", os.path.abspath(str(Path(codex_bin).expanduser())),
            "--cwd", str(Path(cwd).expanduser().resolve()),
        ],
        "RunAtLoad": True,
        "StartInterval": CHECK_INTERVAL,
        "WatchPaths": [str(Path(hooks_path).expanduser().resolve())],
        "ProcessType": "Background",
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
    }


def install_launch_agent(plist_path=PLIST_PATH, hooks_path=HOOKS_PATH,
                         config_path=CONFIG_PATH, state_path=STATE_PATH,
                         codex_bin="", cwd=""):
    if sys.platform != "darwin":
        return {"status": "skipped", "reason": "not_darwin"}
    try:
        binary = _resolve_codex(codex_bin)
    except GuardError as exc:
        return {"status": "skipped", "reason": exc.code}
    plist_path = Path(plist_path).expanduser()
    payload = _plist_payload(hooks_path, config_path, state_path, binary,
                             cwd or str(Path.home()))
    encoded = plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)
    changed = True
    try:
        changed = not plist_path.exists() or plist_path.read_bytes() != encoded
        if changed:
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = plist_path.with_name(plist_path.name + ".tmp")
            tmp.write_bytes(encoded)
            os.replace(str(tmp), str(plist_path))
    except Exception as exc:
        return {"status": "error", "reason": type(exc).__name__}
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LABEL}"
    loaded = _launchctl(["print", service])
    if changed or not loaded:
        if changed:
            _launchctl(["bootout", domain, str(plist_path)])
        _launchctl(["bootstrap", domain, str(plist_path)])
        _launchctl(["kickstart", "-k", service])
    return {"status": "installed", "changed": changed, "plist": str(plist_path)}


def uninstall_launch_agent(plist_path=PLIST_PATH):
    plist_path = Path(plist_path).expanduser()
    if plist_path.exists():
        try:
            payload = plistlib.loads(plist_path.read_bytes())
        except Exception:
            payload = {}
        if payload.get("Label") != LABEL:
            return {"status": "invalid", "changed": False, "plist": str(plist_path)}
    if sys.platform == "darwin":
        _launchctl(["bootout", f"gui/{os.getuid()}", str(plist_path)])
    existed = plist_path.exists()
    try:
        plist_path.unlink()
    except FileNotFoundError:
        pass
    except Exception as exc:
        return {"status": "error", "reason": type(exc).__name__}
    return {"status": "uninstalled", "changed": existed, "plist": str(plist_path)}


def launch_agent_status(plist_path=PLIST_PATH):
    plist_path = Path(plist_path).expanduser()
    if not plist_path.exists():
        return {"status": "not_installed", "plist": str(plist_path)}
    try:
        payload = plistlib.loads(plist_path.read_bytes())
        managed = payload.get("Label") == LABEL
    except Exception:
        managed = False
    return {"status": "installed" if managed else "invalid",
            "plist": str(plist_path), "managed": managed}


def _add_paths(parser, include_runtime=True):
    parser.add_argument("--hooks", type=Path, default=HOOKS_PATH)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--state", type=Path, default=STATE_PATH)
    parser.add_argument("--plist", type=Path, default=PLIST_PATH)
    if include_runtime:
        parser.add_argument("--codex", default="")
        parser.add_argument("--cwd", default=str(Path.home()))


def build_parser():
    parser = argparse.ArgumentParser(description="Guard TRANFU Codex hook trust")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="check and safely repair a pure permutation")
    _add_paths(check)
    check.add_argument("--json", action="store_true")
    check.add_argument("--no-notify", action="store_true")
    install = sub.add_parser("install-launch-agent", help="install/update macOS LaunchAgent")
    _add_paths(install)
    install.add_argument("--json", action="store_true")
    uninstall = sub.add_parser("uninstall-launch-agent", help="remove managed LaunchAgent")
    _add_paths(uninstall, include_runtime=False)
    uninstall.add_argument("--json", action="store_true")
    status = sub.add_parser("status", help="show LaunchAgent status")
    _add_paths(status, include_runtime=False)
    status.add_argument("--json", action="store_true")
    return parser


def _print_result(result, as_json):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("TRANFU Codex hook guard: " + result.get("status", "error"))
        if result.get("reason"):
            print("reason: " + str(result["reason"]))
        if result.get("plist"):
            print("plist: " + str(result["plist"]))


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            result = run_check(args.hooks, args.config, args.state, args.codex,
                               args.cwd, notify=not args.no_notify)
        elif args.command == "install-launch-agent":
            result = install_launch_agent(args.plist, args.hooks, args.config,
                                          args.state, args.codex, args.cwd)
        elif args.command == "uninstall-launch-agent":
            result = uninstall_launch_agent(args.plist)
        else:
            result = launch_agent_status(args.plist)
    except Exception as exc:
        result = {"status": "error", "reason": type(exc).__name__}
    _print_result(result, getattr(args, "json", False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
