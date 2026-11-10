#!/usr/bin/env python3
"""
TRANFU//AGENTS — DSH (DeepSeek Harness) event dispatcher (stdlib only).

The DSH plugin shell (shims/dsh/index.js) spawns this with one JSON object on
stdin: {protocol, event, session_id, [type], [tool], [skill]}. We translate it to
the Claude-style hook payload that tf_hook.py already understands, so state,
turn heartbeats, Skill collection and self-update all reuse the existing path.

All mapping lives here (not in the JS shell) so it upgrades via shim self-update
without restarting DSH. NEVER raises, always exits 0.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUPPORTED_PROTOCOL = 1

# DSH event -> Claude/Codex hook_event_name understood by tf_hook.MAP.
EVENT_MAP = {
    "session/created": "SessionStart",
    "session/disposed": "SessionEnd",
    "tools/pre-execute": "PreToolUse",
    "tools/result": "PostToolUse",
    "agent/error": "Stop",
    "agent/turn-stopping": "Stop",
}
# session/event is multiplexed by its inner `type`.
TURN_TYPE_MAP = {"turn/start": "UserPromptSubmit", "turn/end": "Stop"}

_EXPORT = re.compile(r'^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$')
_UNSET = re.compile(r'^\s*unset\s+([A-Za-z_][A-Za-z0-9_]*)\s*$')


def load_env_file(path, environ=None):
    """Apply `export K="V"` / `unset K` lines of tf_env.dsh.sh to environ.
    The per-runtime file always wins: it is the identity of THIS runtime."""
    environ = os.environ if environ is None else environ
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return False
    for line in lines:
        m = _EXPORT.match(line)
        if m:
            val = m.group(2).strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            environ[m.group(1)] = val
            continue
        m = _UNSET.match(line)
        if m:
            environ.pop(m.group(1), None)
    return True


def to_hook_payload(msg):
    """Pure mapping: shell message -> tf_hook payload dict, or None to ignore."""
    if not isinstance(msg, dict) or msg.get("protocol") != SUPPORTED_PROTOCOL:
        return None
    event = msg.get("event")
    sid = msg.get("session_id")
    if not isinstance(sid, str) or not sid:
        return None
    if event == "session/event":
        name = TURN_TYPE_MAP.get(msg.get("type"))
    else:
        name = EVENT_MAP.get(event)
    if not name:
        return None
    d = {"hook_event_name": name, "session_id": sid}
    tool = msg.get("tool")
    if name in ("PreToolUse", "PostToolUse") and isinstance(tool, str) and tool:
        d["tool_name"] = tool
        skill = msg.get("skill")
        if name == "PreToolUse" and isinstance(skill, str) and skill:
            d["tool_input"] = {"name": skill}
    return d


def main():
    try:
        load_env_file(os.path.join(os.path.expanduser("~/.tranfu"), "tf_env.dsh.sh"))
        os.environ["TF_RUNTIME"] = "dsh"
        raw = sys.stdin.read()
        msg = json.loads(raw) if raw.strip() else {}
        d = to_hook_payload(msg)
        if d is None:
            return
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import tf_hook
        sys.stdin = io.StringIO(json.dumps(d))
        tf_hook.main()
    except Exception:
        pass  # telemetry must never break the host agent


if __name__ == "__main__":
    main()
    sys.exit(0)
