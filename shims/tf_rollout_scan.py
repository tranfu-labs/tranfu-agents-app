#!/usr/bin/env python3
"""
TRANFU//AGENTS — Codex skill-usage scanner (rollout fallback).

Codex does NOT surface skill invocations as a `Skill` tool call the way Claude
Code does, so the PreToolUse path in tf_hook.py never sees them. Instead, Codex
writes a per-session rollout transcript on disk; when an agent actually uses a
skill it reads the installed `.codex/skills/<name>/SKILL.md` (or `.claude/...`)
via a shell `function_call`. That read is the strong, low-false-positive signal
we trust: prompt name-drops, discussion of a skill, or a random SKILL.md file in
some repo do NOT count — only a function_call whose command reads an installed
skill's SKILL.md.

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


def skills_in_file(path):
    """Skill names read via a shell function_call in one rollout file.

    Only `payload.type == "function_call"` records count — that excludes the
    developer skill catalog (a message listing every skill's path), tool *output*
    that echoes SKILL.md content, user/assistant text that name-drops a skill, and
    apply_patch edits (which are custom_tool_call, not function_call). The cheap
    `SKILL.md` substring pre-filter keeps us from JSON-parsing 99% of lines.
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
                if not isinstance(payload, dict) or payload.get("type") != "function_call":
                    continue
                args = payload.get("arguments")
                if not isinstance(args, str):
                    continue
                for m in SKILL_RE.finditer(args):
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
