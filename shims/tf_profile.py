#!/usr/bin/env python3
"""
TRANFU//AGENTS — local agent profile auto-detector (stdlib only).

Detects, best-effort and NEVER raising, the optional profile fields the
dashboard's agent-detail page shows. Used by all three shim paths
(tf-run / local agent hooks / MCP reporter).

Auto-detected:
  cf.ver        runtime + version  (e.g. "Claude Code 1.2.3")
  cf.location   current working dir
  cf.terminal   terminal app + shell  (e.g. "iTerm2 · zsh")
  cf.ims        integrated IMs (heuristic from env / known config files)
  mcp           connected MCP servers (parsed from mcp config files)
  skills        installed skills (scans .claude/skills/*/SKILL.md frontmatter)
  integrations  derived from mcp + ims
  config        best-effort key params (model / permission mode)
  models        from config, or $TF_MODELS

Optional env overrides (the few things a machine can't infer):
  TF_ROLE       cf.role     — what this agent is for (human-defined)
  TF_ABOUT      about       — what it's good at
  TF_TIPS       tips        — dispatcher's how-to note
  TF_MODELS     models      — comma-separated, overrides detection
  TF_REPORT_MEMORY=1         — also attach memory file path+mtime (opt-in, sensitive)

Run standalone to see what it detects:  python3 tf_profile.py
"""
import os, sys, json, glob, re, subprocess
from pathlib import Path

HOME = Path.home()
RT_LABEL = {"claude-code": "Claude Code", "claude-desktop": "Claude Desktop",
            "codex": "Codex", "open-claw": "Open Claw", "hermes": "Hermes",
            "manus": "Manus", "mulerun": "MuleRun", "chatgpt": "ChatGPT"}
VER_CMD = {"claude-code": ["claude", "--version"], "codex": ["codex", "--version"],
           "open-claw": ["claw", "--version"]}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=4).stdout.strip()
    except Exception:
        return ""


def _read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def _read_toml(p):
    try:
        import tomllib
        with open(p, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return None


def detect_terminal():
    tp = os.environ.get("TERM_PROGRAM") or ""
    name = {"iTerm.app": "iTerm2", "Apple_Terminal": "Terminal", "vscode": "VS Code 终端",
            "WezTerm": "WezTerm", "Hyper": "Hyper", "tmux": "tmux"}.get(tp, tp)
    if not name and os.environ.get("TMUX"):
        name = "tmux"
    shell = os.path.basename(os.environ.get("SHELL", "")) or ""
    parts = [p for p in (name, shell) if p]
    return " · ".join(parts) or None


def detect_version(runtime):
    label = RT_LABEL.get(runtime, runtime)
    cmd = VER_CMD.get(runtime)
    if cmd:
        out = _sh(cmd)
        m = re.search(r"\d+\.\d+(\.\d+)?", out)
        if m:
            return f"{label} {m.group(0)}"
    return label or None


def detect_mcp(runtime, cwd):
    servers = set()
    json_candidates = [
        HOME / ".claude.json",
        HOME / ".config" / "claude" / "claude_desktop_config.json",
        HOME / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        HOME / ".config" / "Claude" / "claude_desktop_config.json",
        Path(cwd) / ".mcp.json",
        Path(cwd) / ".claude" / "settings.json",
        HOME / ".claude" / "settings.json",
        HOME / ".codex" / "config.json",
    ]
    for c in json_candidates:
        d = _read_json(c)
        if isinstance(d, dict):
            ms = d.get("mcpServers") or d.get("mcp_servers")
            if isinstance(ms, dict):
                servers.update(ms.keys())
    # codex toml
    d = _read_toml(HOME / ".codex" / "config.toml")
    if isinstance(d, dict):
        ms = d.get("mcp_servers") or d.get("mcpServers")
        if isinstance(ms, dict):
            servers.update(ms.keys())
    return sorted(servers)


def _parse_skill_md(p):
    txt = Path(p).read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^---\s*(.*?)\s*---", txt, re.S | re.M)
    front = m.group(1) if m else txt[:500]
    nm = re.search(r"^name:\s*(.+)$", front, re.M)
    ds = re.search(r"^description:\s*(.+)$", front, re.M)
    name = (nm.group(1).strip() if nm else Path(p).parent.name).strip("\"' ")
    desc = (ds.group(1).strip() if ds else "").strip("\"' ")
    if len(desc) > 90:
        desc = desc[:90].rstrip() + "…"
    return name, desc


def _skill_sources(runtime, cwd):
    """[(root_dir, [glob_patterns], skip_symlinks)] — where THIS runtime loads
    skills from. Per-runtime: Claude ~/.claude/skills, Codex ~/.codex/skills,
    Hermes ~/.hermes/skills (also one level deeper under category dirs).

    skip_symlinks differs by ecosystem:
      - Claude/Codex: their skills dir is a flat install dir where a shared pool
        (~/.agents/skills) gets SYMLINKED in as extras. Those are "borrowed",
        not this agent's own -> skip, so e.g. 赛博哪吒 doesn't advertise lark-*.
      - Hermes: ~/.hermes/skills is a CURATED repo; the agent deliberately
        symlinks its core toolset there (e.g. 多儿 the Lark assistant links the
        lark-* skills). Those ARE its skills -> keep. (This is the bug fix: the
        old blanket symlink-skip dropped 多儿's 24 lark-* skills.)"""
    rt = (runtime or "").lower()

    def flat(d, skip_symlinks=True):
        return (d, [str(d / "*" / "SKILL.md")], skip_symlinks)

    def nested(d, skip_symlinks):  # also match category/skill/SKILL.md
        return (d, [str(d / "*" / "SKILL.md"), str(d / "*" / "*" / "SKILL.md")], skip_symlinks)

    if rt == "hermes":
        return [nested(HOME / ".hermes" / "skills", skip_symlinks=False)]
    if rt == "codex":
        return [flat(HOME / ".codex" / "skills"), flat(Path(cwd) / ".codex" / "skills")]
    # claude-code / claude-desktop / cli / unknown -> Claude's skill dirs
    return [flat(HOME / ".claude" / "skills"), flat(Path(cwd) / ".claude" / "skills")]


def detect_skills(cwd, runtime=None):
    # Escape hatch: TF_SKILLS="name1,name2" reports exactly these (manual curation).
    override = os.environ.get("TF_SKILLS", "").strip()
    if override:
        names = [s.strip() for s in override.split(",") if s.strip()]
        return {"local": [{"name": n, "desc": ""} for n in names],
                "cross": [], "pitfalls": []} if names else None
    # TF_SKILLS_INCLUDE_LINKS=1 forces symlinked skills to count everywhere.
    force_links = os.environ.get("TF_SKILLS_INCLUDE_LINKS") == "1"
    local, seen = [], set()
    for d, patterns, skip_symlinks in _skill_sources(runtime, cwd):
        skip = skip_symlinks and not force_links
        for pat in patterns:
            for sk in sorted(glob.glob(pat)):
                if (os.sep + ".archive" + os.sep) in sk:
                    continue
                # the entry directly under the root on the path to this skill
                try:
                    first = Path(d) / Path(sk).relative_to(d).parts[0]
                except Exception:
                    first = Path(os.path.dirname(sk))
                if skip and first.is_symlink():
                    continue
                nm, desc = _safe(lambda: _parse_skill_md(sk), (None, None))
                if nm and nm not in seen:
                    seen.add(nm)
                    local.append({"name": nm, "desc": desc or ""})
    return {"local": local, "cross": [], "pitfalls": []} if local else None


def detect_ims():
    env = os.environ
    keys = " ".join(env.keys()).upper()
    ims = []
    if "FEISHU" in keys or "LARK" in keys or (HOME / ".hermes" / "secrets.env").exists():
        ims.append("飞书 / Lark")
    if "TELEGRAM" in keys:
        ims.append("Telegram")
    if "WECHAT" in keys or "WEIXIN" in keys:
        ims.append("微信")
    if "SLACK" in keys:
        ims.append("Slack")
    if "DISCORD" in keys:
        ims.append("Discord")
    return ims


def detect_config(cwd, runtime=None):
    cfg = {}
    # Codex keeps its model in ~/.codex/config.toml (or <repo>/.codex/config.toml),
    # NOT in Claude's settings.json. Read the runtime's OWN config so a codex card
    # never shows a model borrowed from a co-resident Claude install. A codex with
    # only a logged-in default (no `model` key) reports no model — correct, vs. the
    # old behavior of silently surfacing whatever Claude's settings had.
    if runtime == "codex":
        for p in [Path(cwd) / ".codex" / "config.toml", HOME / ".codex" / "config.toml"]:
            d = _read_toml(p)
            if isinstance(d, dict) and d.get("model"):
                cfg.setdefault("model", d["model"])
        return cfg or None
    for p in [Path(cwd) / ".claude" / "settings.json", HOME / ".claude" / "settings.json"]:
        d = _read_json(p)
        if isinstance(d, dict):
            if d.get("model"):
                cfg.setdefault("model", d["model"])
            perm = d.get("permissions")
            if isinstance(perm, dict) and perm.get("defaultMode"):
                cfg.setdefault("auto_approve", perm["defaultMode"])
    return cfg or None


def detect_memory(cwd):
    if os.environ.get("TF_REPORT_MEMORY") != "1":
        return None
    for p in [Path(cwd) / "CLAUDE.md", HOME / ".claude" / "CLAUDE.md", HOME / ".hermes" / "memory.md"]:
        if p.exists():
            import time
            age = int(time.time() - p.stat().st_mtime)
            return {"file": str(p).replace(str(HOME), "~"), "updated": age,
                    "conventions": [], "learned": []}
    return None


def collect(runtime=None, cwd=None):
    """Return a dict of optional profile fields. Never raises."""
    runtime = runtime or os.environ.get("TF_RUNTIME") or "cli"
    cwd = cwd or _safe(os.getcwd, str(HOME))
    cf = {
        "ver": _safe(lambda: detect_version(runtime)),
        "role": os.environ.get("TF_ROLE") or None,
        "location": str(cwd).replace(str(HOME), "~"),
        "terminal": _safe(detect_terminal),
        "ims": _safe(detect_ims, []) or [],
    }
    cf = {k: v for k, v in cf.items() if v not in (None, "", [])}

    mcp = _safe(lambda: detect_mcp(runtime, cwd), []) or []
    skills = _safe(lambda: detect_skills(cwd, runtime))
    ims = cf.get("ims", [])
    integrations = [{"name": m, "desc": "MCP 服务"} for m in mcp] + \
                   [{"name": im, "desc": "IM 集成"} for im in ims]
    config = _safe(lambda: detect_config(cwd, runtime))

    models = None
    if os.environ.get("TF_MODELS"):
        models = [m.strip() for m in os.environ["TF_MODELS"].split(",") if m.strip()]
    elif config and config.get("model"):
        models = [config["model"]]

    out = {
        "cf": cf or None,
        "mcp": mcp or None,
        "skills": skills,
        "integrations": integrations or None,
        "config": config,
        "models": models,
        "about": os.environ.get("TF_ABOUT") or None,
        "tips": os.environ.get("TF_TIPS") or None,
        "memory": _safe(lambda: detect_memory(cwd)),
    }
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


if __name__ == "__main__":
    rt = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(collect(runtime=rt), ensure_ascii=False, indent=2))
