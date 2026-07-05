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
from datetime import datetime, timezone

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
# Self-update checks piggy-back on these hook events. SessionStart is the
# canonical trigger; UserPromptSubmit / Stop / SessionEnd are added so that
# *long* sessions (which never see a fresh SessionStart) still get a chance
# to update. The 1h CHECK_INTERVAL throttle in tf_selfupdate.py shares one
# `.selfupdate.json` across all triggers, so adding events does not increase
# how often manifest is actually fetched.
SELFUPDATE_EVENTS = ("SessionStart", "on_session_start",
                     "UserPromptSubmit", "Stop", "SessionEnd")

# Hermes 钩子链路常态结构化诊断日志(ADR-0022 / spec onboarding §10)。
# 默认开,`TF_HOOK_DEBUG=0` 关闭;双文件 5MB rotate,总上限 10MB;只记 ev/tool/sid/skill/rc
# 等摘要,不写 stdin 全文 / tool_input 非 name 字段 / shell 命令文本。
HERMES_EVENTS = {
    "on_session_start", "pre_llm_call", "pre_tool_call",
    "post_tool_call",   "post_llm_call", "on_session_end",
}
LOG_DIR = os.path.join(os.path.expanduser("~/.tranfu"), "logs")
LOG_PATH = os.path.join(LOG_DIR, "hermes-hook.ndjson")
LOG_BAK = LOG_PATH + ".1"
LOG_MAX = 5 * 1024 * 1024


def _name_from(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("skill", "name", "skill_name"):
            name = _name_from(value.get(key))
            if name:
                return name
    return ""


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
        args += ["--skill", skill]
    return args


def _utcnow_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _rotate_if_needed():
    try:
        if os.stat(LOG_PATH).st_size >= LOG_MAX:
            os.rename(LOG_PATH, LOG_BAK)
    except FileNotFoundError:
        pass


def _hook_log(ev, tool, sid, skill, argv, rc, err):
    if ev not in HERMES_EVENTS:
        return  # Claude/Codex 链路不落盘;scan_* 调用 _run_report 时 ev=None 同样被守门
    if os.environ.get("TF_HOOK_DEBUG") == "0":
        return  # 显式逃逸口
    try:
        _ensure_log_dir()
        _rotate_if_needed()
        record = {
            "ts":        _utcnow_iso(),
            "ev":        ev,
            "tool":      (str(tool) if tool else "")[:32],
            "sid":       (str(sid) if sid else "")[:8],
            "skill":     (str(skill) if skill else "")[:64],
            "argv_tail": (" ".join(map(str, argv or [])))[-80:],
            "rc":        int(rc) if rc is not None else -1,
            "err":       (err or "")[:80],
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # diagnostic log must never break the hook


def _run_report(rargs, ev=None, tool=None, sid=None, skill=None):
    args = ["python3", os.path.join(HERE, "tf_report.py")] + rargs
    rc, err = -1, ""
    try:
        proc = subprocess.run(args, timeout=8,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE)
        rc = proc.returncode
        if proc.stderr:
            err = proc.stderr.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        err = "timeout"
    except Exception as e:
        err = type(e).__name__
    _hook_log(ev, tool, sid, skill, rargs, rc, err)


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


# Claude Code 用户手敲的 /<skill> 不走 Skill 工具,而是被 Claude 在 hook 之后
# 展开成 <command-name>/<name></command-name> 写进 transcript jsonl。hook stdin 上的
# prompt 字段是裸文本无 markup,所以必须在 Stop/SessionEnd 时去扫 transcript_path
# 指向的那份 jsonl —— 与 scan_codex_skills 同构,只是来源不同。
CLAUDE_SCAN_EVENTS = ("Stop", "SessionEnd")
_CLAUDE_BUILTIN_SLASH = frozenset({
    "add-dir",
    "agents",
    "bashes",
    "bug",
    "clear",
    "compact",
    "config",
    "context",
    "cost",
    "doctor",
    "exit",
    "fast",
    "help",
    "hooks",
    "ide",
    "login",
    "logout",
    "mcp",
    "memory",
    "microphone",
    "migrate-installer",
    "model",
    "output-style",
    "permissions",
    "pr-comments",
    "pr_comments",
    "quit",
    "release-notes",
    "resume",
    "status",
    "terminal-setup",
    "usage",
    "vim",
})


def _extract_user_command_name(line):
    try:
        row = json.loads(line)
    except Exception:
        return None
    if not isinstance(row, dict) or row.get("type") != "user":
        return None
    message = row.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    text = ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                value = block.get("text")
                if isinstance(value, str):
                    text = value
                break
    stripped = text.lstrip()
    if stripped.startswith("<command-name>"):
        match = re.match(r"<command-name>(/?[\w:-]{1,80})</command-name>", stripped)
        return match.group(1) if match else None
    if not stripped.startswith("<command-message>"):
        return None
    match = re.match(
        r"<command-message>[\s\S]{0,200}?</command-message>\s*"
        r"<command-name>(/?[\w:-]{1,80})</command-name>",
        stripped,
    )
    return match.group(1) if match else None


def _normalize_skill_name(raw):
    if not isinstance(raw, str):
        return None
    name = raw.lstrip("/").split(":", 1)[0]
    if not name:
        return None
    if name.isdigit():
        return None
    if name.startswith(("-", "_")) or name.endswith(("-", "_")):
        return None
    if "--" in name:
        return None
    return name


def scan_claude_skills(d):
    """Stop/SessionEnd 时扫 transcript jsonl 抓 <command-name> 标记。
    任何失败视为'无数据',静默退出,永远不阻塞主线程。"""
    if os.environ.get("TF_REPORT_SKILLS") == "0":
        return
    if os.environ.get("TF_RUNTIME") != "claude-code":
        return
    if _event_name(d) not in CLAUDE_SCAN_EVENTS:
        return
    if not isinstance(d, dict):
        return
    transcript = d.get("transcript_path")
    if not transcript or not os.path.exists(transcript):
        return
    sid = _session_id(d)
    if not sid:
        return
    names = set()
    try:
        with open(transcript, errors="replace") as f:
            for line in f:
                raw = _extract_user_command_name(line)
                nm = _normalize_skill_name(raw)
                if not nm or nm in _CLAUDE_BUILTIN_SLASH:
                    continue
                names.add(nm)
    except Exception:
        return
    for nm in sorted(names):
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
        ev = _event_name(d)
        tool = d.get("tool_name") or d.get("tool") or ""
        if isinstance(tool, dict):
            tool = tool.get("name") or tool.get("tool_name") or ""
        _run_report(rargs,
                    ev=ev,
                    tool=str(tool) if tool else "",
                    sid=_session_id(d),
                    skill=_skill_name(d, ev, tool))
    try:
        scan_codex_skills(d)
    except Exception:
        pass  # telemetry must never break the session
    try:
        scan_claude_skills(d)
    except Exception:
        pass  # telemetry must never break the session


if __name__ == "__main__":
    main()
