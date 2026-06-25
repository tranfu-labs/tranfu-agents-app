"""Skill 名规范化 + profile 全量加载 + 跨人复用计算
(由 refactor-server-app-by-domain 引入)。

ingest 写 profile 时调 _skill_use_name / _skill_mode;board 读时调 load_profiles /
load_shim_versions / reuse_map。
"""
import json

from server.config import MAX_SKILL_NAME, SKILL_MODES


def _skill_names(skills):
    """Flatten a skills object {local:[{name}],cross:[...]} (or list) to names."""
    out = []
    if isinstance(skills, dict):
        for grp in ("local", "cross"):
            for s in skills.get(grp) or []:
                out.append(s.get("name") if isinstance(s, dict) else s)
    elif isinstance(skills, list):
        for s in skills:
            out.append(s.get("name") if isinstance(s, dict) else s)
    return [n for n in out if n]


def _skill_use_name(value):
    """Normalize the optional event-level skill usage name."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value:
        return ""
    return value[:MAX_SKILL_NAME]


def _skill_mode(value):
    """Normalize event-level skill semantic mode; invalid values are legacy used."""
    if not isinstance(value, str):
        return "used"
    value = value.strip().lower()
    return value if value in SKILL_MODES else "used"


def load_profiles(conn):
    out = {}
    for r in conn.execute("SELECT operator,ak,runtime,json FROM profiles"):
        try:
            out[r["operator"] + "\x00" + r["ak"]] = json.loads(r["json"])
        except Exception:  # pragma: no cover  — profile JSON 损坏兜底
            pass
    return out


def load_shim_versions(conn):
    """Sticky shim_version per (operator, agent_key). Same map key shape as
    load_profiles so card() can merge by the same identity tuple."""
    out = {}
    for r in conn.execute("SELECT operator,ak,shim_version FROM agent_shim_versions"):
        if r["shim_version"]:
            out[r["operator"] + "\x00" + r["ak"]] = r["shim_version"]
    return out


def reuse_map(profiles):
    """skill name -> set(operators) ; then per identity, fraction of its skills
    that also appear in another operator's profile (cross-Pod reuse signal)."""
    owners = {}
    for key, p in profiles.items():
        op = key.split("\x00", 1)[0]
        for nm in _skill_names(p.get("skills")):
            owners.setdefault(nm, set()).add(op)
    out = {}
    for key, p in profiles.items():
        op = key.split("\x00", 1)[0]
        names = _skill_names(p.get("skills"))
        if not names:
            continue
        shared = sum(1 for nm in names if len(owners.get(nm, set()) - {op}) > 0)
        out[key] = round(shared / len(names), 3)
    return out
