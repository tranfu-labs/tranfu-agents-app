#!/usr/bin/env python3
"""
TRANFU//AGENTS — Claude Code hook dispatcher.

Claude Code passes the hook event as JSON on stdin (session_id, hook_event_name,
tool_name, ...). This maps the event to a report status and calls tf_report.py.
It NEVER blocks Claude (no stdout decision, always exits 0).

Wire it in ~/.claude/settings.json for the events you want; this one script
handles all of them (it reads hook_event_name from stdin):
  SessionStart -> started (+profile, registers the agent once)
  UserPromptSubmit -> running ("prompt")
  PreToolUse -> running ("tool: <name>")   # live step = which tool
  Stop -> done ("turn end")
  SessionEnd -> done ("session end")

Identity (operator/runtime/agent) + server/key come from the environment
(exported in your shell rc by install.sh). session_id comes from the hook JSON,
so every event in a session shares one identity = one card.
"""
import sys, os, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

# event -> (status, step, attach_profile)
MAP = {
    "SessionStart":     ("started", "session start", True),
    "UserPromptSubmit": ("running", "prompt",        False),
    "PreToolUse":       ("running", "tool",          False),
    "PostToolUse":      ("running", "tool done",     False),
    "Stop":             ("done",    "turn end",      False),
    "SessionEnd":       ("done",    "session end",   False),
}


def main():
    try:
        raw = sys.stdin.read()
        d = json.loads(raw) if raw.strip() else {}
    except Exception:
        d = {}
    ev = d.get("hook_event_name", "")
    if ev not in MAP:
        return
    status, step, prof = MAP[ev]
    tool = d.get("tool_name") or ""
    if ev in ("PreToolUse", "PostToolUse") and tool:
        step = f"{step.split(' ')[0]}: {tool}" if ev == "PreToolUse" else f"tool done: {tool}"
    sid = d.get("session_id") or ""
    args = ["python3", os.path.join(HERE, "tf_report.py"), "--status", status, "--step", step]
    if sid:
        args += ["--session", sid]
    if prof:
        args += ["--profile"]
    try:
        subprocess.run(args, timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # telemetry must never break the session


if __name__ == "__main__":
    main()
