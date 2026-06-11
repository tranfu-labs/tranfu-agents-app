#!/usr/bin/env python3
"""
TRANFU//AGENTS — local agent hook dispatcher.

Claude Code, Codex and Hermes all pass the hook event as JSON on stdin
(hook_event_name, tool_name, session_id, ...). This maps the event to a report
status and calls tf_report.py. It NEVER blocks the host agent (no stdout
decision, always exits 0).

Wire it through tf_hooks.py (Claude/Codex) or config.yaml `hooks:` (Hermes,
via the tf-hermes-hook.sh wrapper). One script handles all runtimes — it reads
hook_event_name from stdin:

  Claude Code / Codex        Hermes shell hook        -> report
  SessionStart               on_session_start         -> started (+profile)
  UserPromptSubmit           pre_llm_call             -> running ("prompt")
  PreToolUse                 pre_tool_call            -> running ("tool: <name>")
  PostToolUse                post_tool_call           -> running ("tool done: <name>")
  Stop                       post_llm_call            -> done ("turn end")
  SessionEnd                 on_session_end           -> done ("session end")

Identity (operator/runtime/agent) + server/key come from the environment, which
the wrapper/hook command loads from the per-runtime tf_env.<runtime>.sh file.
session_id comes from the hook JSON, so every event in a session shares one
identity = one card.
"""
import sys, os, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

# event -> (status, step, attach_profile). Both Claude/Codex CamelCase names and
# Hermes snake_case names map to the same report semantics.
MAP = {
    # Claude Code / Codex
    "SessionStart":     ("started", "session start", True),
    "UserPromptSubmit": ("running", "prompt",        False),
    "PreToolUse":       ("running", "tool",          False),
    "PostToolUse":      ("running", "tool done",     False),
    "Stop":             ("done",    "turn end",      False),
    "SessionEnd":       ("done",    "session end",   False),
    # Hermes (shell hooks — see hermes website/docs .../features/hooks.md)
    "on_session_start": ("started", "session start", True),
    "pre_llm_call":     ("running", "prompt",        False),
    "pre_tool_call":    ("running", "tool",          False),
    "post_tool_call":   ("running", "tool done",     False),
    "post_llm_call":    ("done",    "turn end",      False),
    "on_session_end":   ("done",    "session end",   False),
}
PRE_TOOL = ("PreToolUse", "pre_tool_call")
POST_TOOL = ("PostToolUse", "post_tool_call")


def _name_from(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("skill", "name", "skill_name"):
            name = _name_from(value.get(key))
            if name:
                return name
    return ""


def _skill_name(d, ev, tool):
    if os.environ.get("TF_REPORT_SKILLS") == "0":
        return ""
    if ev not in PRE_TOOL or str(tool).casefold() != "skill":
        return ""
    for key in ("tool_input", "toolInput", "input", "arguments"):
        payload = d.get(key)
        if isinstance(payload, dict):
            name = _name_from(payload)
            if name:
                return name
    return ""


def resolve(d):
    """Map a hook payload dict -> tf_report.py argv (sans the python3/script
    prefix), or None if the event isn't one we report. Pure & testable."""
    if not isinstance(d, dict):
        return None
    ev = d.get("hook_event_name") or d.get("event") or d.get("type") or ""
    if ev not in MAP:
        return None
    status, step, prof = MAP[ev]
    tool = d.get("tool_name") or d.get("tool") or ""
    if isinstance(tool, dict):
        tool = tool.get("name") or tool.get("tool_name") or ""
    if ev in PRE_TOOL and tool:
        step = f"tool: {tool}"
    elif ev in POST_TOOL and tool:
        step = f"tool done: {tool}"
    session_obj = d.get("session") if isinstance(d.get("session"), dict) else {}
    extra = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    sid = (d.get("session_id") or d.get("conversation_id") or d.get("thread_id")
           or session_obj.get("id") or "")
    # subagent -> parent run, so the agent tree can be reconstructed (TATP §1)
    parent = (d.get("parent_session_id") or d.get("parent_id")
              or extra.get("parent_session_id") or session_obj.get("parent_id") or "")
    args = ["--status", status, "--step", step]
    if sid:
        args += ["--session", str(sid)]
    if parent:
        args += ["--parent", str(parent)]
    if prof:
        args += ["--profile"]
    skill = _skill_name(d, ev, tool)
    if skill:
        args += ["--skill", skill]
    return args


def main():
    try:
        raw = sys.stdin.read()
        d = json.loads(raw) if raw.strip() else {}
    except Exception:
        d = {}
    rargs = resolve(d)
    if rargs is None:
        return
    args = ["python3", os.path.join(HERE, "tf_report.py")] + rargs
    try:
        subprocess.run(args, timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # telemetry must never break the session


if __name__ == "__main__":
    main()
