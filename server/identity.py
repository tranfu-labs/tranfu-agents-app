"""身份归一化与令牌校验(由 refactor-server-app-by-domain 引入)。

operator 大小写/空格 → 同一身份;运行时令牌(TATP §4)绑定到归一化 operator,
保证一个人/一个 agent = 一张卡。
"""
from fastapi import HTTPException

from server.db import _sha


def canon_operator(conn, raw, when):
    """Resolve an operator string to its canonical display (first-seen casing),
    case/space-insensitively. 'NEZHA', ' nezha ' -> one identity = one Pod."""
    raw = (raw or "").strip()
    norm = raw.casefold()
    if not norm:
        return raw
    conn.execute("INSERT OR IGNORE INTO identities(norm,display,created) VALUES(?,?,?)",
                 (norm, raw, when))
    row = conn.execute("SELECT display FROM identities WHERE norm=?", (norm,)).fetchone()
    return row["display"] if row else raw


def verify_operator(conn, operator, token):
    """Per-operator attribution (§4). Returns True iff `token` is bound to
    `operator`. When TF_REQUIRE_TOKEN is on, a missing/mismatched token is a 403."""
    from server import app  # 延迟读 REQUIRE_TOKEN(可变开关)
    if not token:
        if app.REQUIRE_TOKEN:
            raise HTTPException(403, "X-TF-Token required (TF_REQUIRE_TOKEN on)")
        return False                                   # legacy: operator self-asserted
    row = conn.execute("SELECT operator FROM operators WHERE token_hash=?",
                       (_sha(token),)).fetchone()
    if not row or row["operator"] != operator:
        raise HTTPException(403, "token does not match operator")
    return True


def _norm_op(value):
    return (value or "").strip().casefold()
