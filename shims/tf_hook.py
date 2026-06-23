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
import sys, os, json, re, subprocess

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
SKILL_TOOLS = {"skill", "skill_view"}
SELFUPDATE_EVENTS = ("SessionStart", "on_session_start")


def _name_from(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("skill", "name", "skill_name"):
            name = _name_from(value.get(key))
            if name:
                return name
    return ""


# Claude Code 把用户手敲的 /<skill> 写进 UserPromptSubmit 的 prompt 头部，
# 形如 <command-name>/openspec-driven-development</command-name>。前导斜杠可有可无。
_SLASH_CMD_RE = re.compile(r"<command-name>/?([\w-]{2,80})</command-name>")
_SLASH_PROMPT_HEAD = 1024


def _skill_from_slash_prompt(prompt):
    if not isinstance(prompt, str) or not prompt:
        return ""
    m = _SLASH_CMD_RE.search(prompt[:_SLASH_PROMPT_HEAD])
    if not m:
        return ""
    name = m.group(1)
    if name.isdigit():
        return ""
    if name.startswith(("-", "_")) or name.endswith(("-", "_")):
        return ""
    if "--" in name:
        return ""
    return name


def _skill_from_tool_input(d):
    for key in ("tool_input", "toolInput", "input", "arguments"):
        payload = d.get(key)
        if isinstance(payload, dict):
            name = _name_from(payload)
            if name:
                return name
    return ""


def _skill_name(d, ev, tool):
    if os.environ.get("TF_REPORT_SKILLS") == "0":
        return ""
    if ev == "UserPromptSubmit":
        return _skill_from_slash_prompt(d.get("prompt"))
    if ev in PRE_TOOL and str(tool).casefold() in SKILL_TOOLS:
        return _skill_from_tool_input(d)
    return ""


def _event_name(d):
    return d.get("hook_event_name") or d.get("event") or d.get("type") or ""


def _session_id(d):
    session_obj = d.get("session") if isinstance(d.get("session"), dict) else {}
    return (d.get("session_id") or d.get("conversation_id") or d.get("thread_id")
            or session_obj.get("id") or "")


def resolve(d):
    """Map a hook payload dict -> tf_report.py argv (sans the python3/script
    prefix), or None if the event isn't one we report. Pure & testable."""
    if not isinstance(d, dict):
        return None
    ev = _event_name(d)
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
    sid = _session_id(d)
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
        if ev == "UserPromptSubmit":
            # 让事件级 step 反映这是个 skill 调用，与 scan_codex_skills 输出对齐
            step_idx = args.index("--step") + 1
            args[step_idx] = f"skill: {skill}"
        args += ["--skill", skill]
    return args


def _run_report(rargs):
    args = ["python3", os.path.join(HERE, "tf_report.py")] + rargs
    try:
        subprocess.run(args, timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # telemetry must never break the session


def _spawn_selfupdate(d):
    if os.environ.get("TF_AUTO_UPDATE") == "0":
        return
    if _event_name(d) not in SELFUPDATE_EVENTS:
        return
    script = os.path.join(HERE, "tf_selfupdate.py")
    if not os.path.exists(script):
        return
    env = os.environ.copy()
    sid = _session_id(d)
    if sid:
        env["TF_SESSION"] = str(sid)
    try:
        subprocess.Popen(["python3", script], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, start_new_session=True, env=env)
    except Exception:
        pass  # self-update must never break the session


# Codex turn/session-end events that trigger a rollout scan. Codex never exposes
# skills as a `Skill` tool call (so resolve()/PreToolUse can't see them); instead
# we read its on-disk transcript once per turn end and report the skills it used.
CODEX_SCAN_EVENTS = ("Stop", "SessionEnd")


def scan_codex_skills(d):
    """Fallback skill-usage collection for Codex: at turn/session end, parse the
    session's rollout transcript for installed-SKILL.md reads and report each.
    Best-effort and self-contained — any failure means 'no data', never an error."""
    if os.environ.get("TF_REPORT_SKILLS") == "0":
        return
    if os.environ.get("TF_RUNTIME") != "codex":
        return
    if _event_name(d) not in CODEX_SCAN_EVENTS:
        return
    sid = _session_id(d)
    if not sid:
        return
    try:
        import tf_rollout_scan
        names = tf_rollout_scan.scan_session(sid)
    except Exception:
        return
    for nm in names:
        _run_report(["--status", "done", "--step", f"skill: {nm}",
                     "--session", str(sid), "--skill", nm])


def main():
    try:
        raw = sys.stdin.read()
        d = json.loads(raw) if raw.strip() else {}
    except Exception:
        d = {}
    try:
        _spawn_selfupdate(d)
    except Exception:
        pass  # self-update must never break the session
    rargs = resolve(d)
    if rargs is not None:
        _run_report(rargs)
    try:
        scan_codex_skills(d)
    except Exception:
        pass  # telemetry must never break the session


if __name__ == "__main__":
    main()
