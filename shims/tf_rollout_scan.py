#!/usr/bin/env python3
"""
TRANFU//AGENTS — Codex skill-usage scanner (rollout fallback).

Codex does NOT surface skill invocations as a `Skill` tool call the way Claude
Code does, so the PreToolUse path in tf_hook.py never sees them. Instead, Codex
writes a per-session rollout transcript on disk; when an agent actually uses a
skill it reads the installed `.codex/skills/<name>/SKILL.md` (or `.claude/...`)
through a shell command. Older rollouts store that command as a `function_call`;
Codex Desktop stores a JavaScript `custom_tool_call` wrapper around
`tools.exec_command(...)`. That read is the strong, low-false-positive signal we
trust: prompt name-drops, discussion of a skill, edits, or a random SKILL.md file
in some repo do NOT count.

tf_hook.py calls scan_session() on Codex turn/session end and reports each name
through tf_report.py --skill. Per-session×skill dedup is enforced server-side, so
re-scanning the same growing file every turn never double-counts.

Conventions match the rest of the shim family: never raise into the host agent,
fall back to "no data" on any error, and bound the work so a huge transcript
can't blow the hook's 5s timeout.

Manual verification (layer-1 of the verify plan):
  python3 tf_rollout_scan.py --session <session_id> --print   # list names, no POST
"""
import os, re, sys, glob, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

MAX_SKILL_NAME = 160          # bounded like the server (app.py MAX_SKILL_NAME)
MAX_BYTES = 80 * 1024 * 1024  # stop reading a single transcript past this (timeout guard)

# Path of an *installed* skill's manifest: a dot-dir (.codex / .claude) → skills →
# <name> → SKILL.md. The dot-dir prefix is what separates a real installed skill
# from a stray SKILL.md living in some skills-authoring repo (docs/skills/x.md,
# skillsbench/tasks/.../SKILL.md, a repo-root SKILL.md — all excluded).
SKILL_RE = re.compile(r"[/\\]\.(?:codex|claude)[/\\]skills[/\\]([^/\\]+)[/\\]SKILL\.md")
EXEC_CALLEE = "tools.exec_command"


def codex_home():
    return os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")


def find_rollouts(session_id, home=None):
    """All rollout transcripts for a session id (normally one)."""
    if not session_id:
        return []
    home = home or codex_home()
    pat = os.path.join(home, "sessions", "**", f"rollout-*-{session_id}.jsonl")
    try:
        return sorted(glob.glob(pat, recursive=True))
    except Exception:
        return []


def _skip_js_string(source, start):
    """Index after a JS string/template literal, or len(source) if unclosed."""
    quote = source[start]
    i = start + 1
    while i < len(source):
        ch = source[i]
        if ch == "\\":
            i += 2
            continue
        if quote == "`" and ch == "$" and i + 1 < len(source) and source[i + 1] == "{":
            i = _skip_js_template_expression(source, i + 2)
            continue
        if ch == quote:
            return i + 1
        i += 1
    return len(source)


def _skip_js_template_expression(source, start):
    """Skip a ${...} expression, including nested strings/templates/comments."""
    depth = 1
    i = start
    while i < len(source):
        if source[i] in "'\"`":
            i = _skip_js_string(source, i)
            continue
        if source.startswith("//", i) or source.startswith("/*", i):
            i = _skip_js_trivia(source, i)
            continue
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(source)


def _skip_js_trivia(source, start):
    """Skip whitespace and JS comments without evaluating the source."""
    i = start
    while i < len(source):
        if source[i].isspace():
            i += 1
            continue
        if source.startswith("//", i):
            end = source.find("\n", i + 2)
            i = len(source) if end < 0 else end + 1
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = len(source) if end < 0 else end + 2
            continue
        break
    return i


def _js_call_arguments(source, callee=EXEC_CALLEE):
    """Yield argument source for real callee(...) calls outside strings/comments."""
    i = 0
    while i < len(source):
        ch = source[i]
        if ch in "'\"`":
            i = _skip_js_string(source, i)
            continue
        if source.startswith("//", i) or source.startswith("/*", i):
            i = _skip_js_trivia(source, i)
            continue
        if not source.startswith(callee, i):
            i += 1
            continue
        before = source[i - 1] if i else ""
        after_at = i + len(callee)
        after = source[after_at] if after_at < len(source) else ""
        if ((before and (before.isalnum() or before in "_$"))
                or (after and (after.isalnum() or after in "_$"))):
            i += 1
            continue
        open_at = _skip_js_trivia(source, after_at)
        if open_at >= len(source) or source[open_at] != "(":
            i = after_at
            continue
        depth = 1
        j = open_at + 1
        while j < len(source) and depth:
            if source[j] in "'\"`":
                j = _skip_js_string(source, j)
                continue
            if source.startswith("//", j) or source.startswith("/*", j):
                j = _skip_js_trivia(source, j)
                continue
            if source[j] == "(":
                depth += 1
            elif source[j] == ")":
                depth -= 1
                if depth == 0:
                    yield source[open_at + 1:j]
                    j += 1
                    break
            j += 1
        if depth:
            return
        i = j


def _read_static_js_string(source, start):
    """Return (value, end) for a static JS string literal; reject interpolation."""
    quote = source[start]
    out = []
    i = start + 1
    escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v"}
    while i < len(source):
        ch = source[i]
        if ch == quote:
            return "".join(out), i + 1
        if quote == "`" and ch == "$" and i + 1 < len(source) and source[i + 1] == "{":
            return None
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= len(source):
            return None
        esc = source[i]
        if esc in "\n\r":
            if esc == "\r" and i + 1 < len(source) and source[i + 1] == "\n":
                i += 1
        elif esc == "x" and i + 2 < len(source):
            try:
                out.append(chr(int(source[i + 1:i + 3], 16)))
                i += 2
            except ValueError:
                out.append(esc)
        elif esc == "u" and i + 4 < len(source):
            try:
                out.append(chr(int(source[i + 1:i + 5], 16)))
                i += 4
            except ValueError:
                out.append(esc)
        else:
            out.append(escapes.get(esc, esc))
        i += 1
    return None


def _static_cmd(call_args):
    """Extract the top-level inline object's static string `cmd` property."""
    i = _skip_js_trivia(call_args, 0)
    if i >= len(call_args) or call_args[i] != "{":
        return None
    depth = 1
    i += 1
    while i < len(call_args) and depth:
        i = _skip_js_trivia(call_args, i)
        if i >= len(call_args):
            break
        ch = call_args[i]
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth -= 1
            i += 1
            continue
        key = None
        key_end = i
        if depth == 1 and ch in "'\"`":
            parsed = _read_static_js_string(call_args, i)
            if parsed is None:
                i = _skip_js_string(call_args, i)
                continue
            key, key_end = parsed
        elif depth == 1 and call_args.startswith("cmd", i):
            before = call_args[i - 1] if i else ""
            after = call_args[i + 3] if i + 3 < len(call_args) else ""
            if (not (before and (before.isalnum() or before in "_$"))
                    and not (after and (after.isalnum() or after in "_$"))):
                key, key_end = "cmd", i + 3
        if key is not None:
            colon = _skip_js_trivia(call_args, key_end)
            if key == "cmd" and colon < len(call_args) and call_args[colon] == ":":
                value_at = _skip_js_trivia(call_args, colon + 1)
                if value_at < len(call_args) and call_args[value_at] in "'\"`":
                    parsed = _read_static_js_string(call_args, value_at)
                    return parsed[0] if parsed is not None else None
                return None
            i = key_end
            continue
        if ch in "'\"`":
            i = _skip_js_string(call_args, i)
            continue
        i += 1
    return None


def _commands_in_payload(payload):
    """Known rollout formats -> statically confirmed shell command strings."""
    if not isinstance(payload, dict):
        return []
    if payload.get("type") == "function_call" and payload.get("name") == "exec_command":
        args = payload.get("arguments")
        if not isinstance(args, str):
            return []
        try:
            obj = json.loads(args)
        except Exception:
            return []
        cmd = obj.get("cmd") if isinstance(obj, dict) else None
        return [cmd] if isinstance(cmd, str) else []
    if payload.get("type") == "custom_tool_call" and payload.get("name") == "exec":
        source = payload.get("input")
        if not isinstance(source, str):
            return []
        commands = []
        for call_args in _js_call_arguments(source):
            cmd = _static_cmd(call_args)
            if cmd is not None:
                commands.append(cmd)
        return commands
    return []


def skills_in_file(path):
    """Skill names read via a statically confirmed shell command in a rollout.

    Known old/new command containers count; messages, outputs, edits and dynamic
    JavaScript do not. The cheap `SKILL.md` substring pre-filter keeps us from
    JSON-parsing 99% of lines.
    """
    found = set()
    try:
        read = 0
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                read += len(line)
                if read > MAX_BYTES:
                    break
                if "SKILL.md" not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                payload = d.get("payload") if isinstance(d, dict) else None
                for command in _commands_in_payload(payload):
                    for m in SKILL_RE.finditer(command):
                        name = m.group(1).strip()
                        if name:
                            found.add(name[:MAX_SKILL_NAME])
    except Exception:
        pass
    return found


def scan_session(session_id, home=None):
    """Sorted, deduped skill names a session used (read of an installed SKILL.md)."""
    names = set()
    for fp in find_rollouts(session_id, home):
        names |= skills_in_file(fp)
    return sorted(names)


def report_skills(session_id, names):
    """Emit one tf_report event per skill so the server records session×skill.
    Best-effort: each call is fire-and-forget and never raises."""
    for nm in names:
        args = ["python3", os.path.join(HERE, "tf_report.py"),
                "--status", "done", "--step", f"skill: {nm}",
                "--session", str(session_id), "--skill", nm]
        try:
            subprocess.run(args, timeout=8,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def main():
    session = ""
    dry = False
    av = sys.argv[1:]
    for i, a in enumerate(av):
        if a == "--session" and i + 1 < len(av):
            session = av[i + 1]
        elif a == "--print":
            dry = True
    if not session:
        sys.exit("usage: tf_rollout_scan.py --session <session_id> [--print]")
    names = scan_session(session)
    if dry or os.environ.get("TF_REPORT_SKILLS") == "0":
        print(json.dumps({"session": session, "skills": names}, ensure_ascii=False))
        return
    report_skills(session, names)


if __name__ == "__main__":
    main()
