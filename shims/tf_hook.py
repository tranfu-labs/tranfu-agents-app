#!/usr/bin/env python3
"""
TRANFU//AGENTS — local agent hook dispatcher.

Claude Code and Codex pass the hook event as JSON on stdin (session_id,
hook_event_name, tool_name, ...). This maps the event to a report status and
calls tf_report.py. It NEVER blocks the host agent (no stdout decision, always
exits 0).

Wire it through tf_hooks.py for the events you want; this one script handles
all of them (it reads hook_event_name from stdin):
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
    ev = d.get("hook_event_name") or d.get("event") or d.get("type") or ""
    if ev not in MAP:
        return
    status, step, prof = MAP[ev]
    tool = d.get("tool_name") or d.get("tool") or ""
    if isinstance(tool, dict):
        tool = tool.get("name") or tool.get("tool_name") or ""
    if ev in ("PreToolUse", "PostToolUse") and tool:
        step = f"{step.split(' ')[0]}: {tool}" if ev == "PreToolUse" else f"tool done: {tool}"
    session_obj = d.get("session") if isinstance(d.get("session"), dict) else {}
    sid = d.get("session_id") or d.get("conversation_id") or d.get("thread_id") or session_obj.get("id") or ""
    # subagent -> parent run, so the agent tree can be reconstructed (TATP §1)
    parent = d.get("parent_session_id") or d.get("parent_id") or session_obj.get("parent_id") or ""
    args = ["python3", os.path.join(HERE, "tf_report.py"), "--status", status, "--step", step]
    if sid:
        args += ["--session", sid]
    if parent:
        args += ["--parent", parent]
    if prof:
        args += ["--profile"]
    try:
        subprocess.run(args, timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # telemetry must never break the session


if __name__ == "__main__":
    main()
