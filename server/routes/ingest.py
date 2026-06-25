"""ingest 域路由(对应 openspec/specs/ingest/spec.md)。

- POST /v1/enroll  — admin 签发 per-operator token
- POST /v1/events  — 心跳事件采集

注:DELETE /v1/events(legacy 兼容路径)归属 admin 域,见 server/routes/admin.py。
"""
import json
import secrets
from contextlib import closing

from fastapi import APIRouter, Header, HTTPException, Request

from server.db import _audit, _clip, _maybe_prune, _sha, db, now_iso
from server.identity import canon_operator, verify_operator
from server.profile import _skill_mode, _skill_names, _skill_use_name
from server.security import (
    _client_host, _rate_register_failure, _rate_register_success, _rate_retry_after,
    check_auth,
)

router = APIRouter()


# ---------------------------------------------------------------- enroll (§4)
@router.post("/v1/enroll")
async def enroll(request: Request, x_tf_key: str = Header(default="")):
    """Admin issues a per-operator token. Guarded by the team write key.
    The plaintext token is returned ONCE; the server stores only its sha256."""
    from server import app  # 延迟读全局 _lock
    # 签发持久 token 的写侧钥匙值得保护:与管理接口同类的按 IP 限流(独立 bucket)。
    ip = _client_host(request)
    retry = _rate_retry_after("enroll", ip)
    if retry is not None:
        raise HTTPException(status_code=429, detail="too many attempts",
                            headers={"Retry-After": str(retry)})
    try:
        check_auth(x_tf_key)
    except HTTPException:
        _, retry = _rate_register_failure("enroll", ip)
        if retry is not None:
            raise HTTPException(status_code=429, detail="too many attempts",
                                headers={"Retry-After": str(retry)})
        raise
    _rate_register_success("enroll", ip)
    body = await request.json()
    raw_op = (body.get("operator") or "").strip()
    if not raw_op:
        raise HTTPException(400, "operator required")
    token = "ttk_" + secrets.token_urlsafe(24)
    with app._lock, closing(db()) as conn:
        operator = canon_operator(conn, raw_op, now_iso())   # bind token to canonical identity
        conn.execute("""INSERT INTO operators(operator,token_hash,created) VALUES(?,?,?)
          ON CONFLICT(operator) DO UPDATE SET token_hash=excluded.token_hash,created=excluded.created""",
          (operator, _sha(token), now_iso()))
        conn.commit()
    return {"operator": operator, "token": token,
            "note": "保存到 TF_TOKEN，仅此一次可见"}


# ---------------------------------------------------------------- ingest
@router.post("/v1/events")
async def ingest_event(request: Request, x_tf_key: str = Header(default=""),
                       x_tf_token: str = Header(default="")):
    from server import app  # 延迟读 _lock / MAX_BODY 等等(MAX_BODY 是 config 常量,通过 app re-export)
    from server.config import MAX_BODY, MAX_CONTENT, MAX_META, PROFILE_KEYS, SENSITIVE_KEYS
    check_auth(x_tf_key)
    # §8 reject oversized bodies before parsing
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, f"body exceeds {MAX_BODY} bytes")
    try:
        e = json.loads(raw)
    except Exception:
        raise HTTPException(400, "invalid JSON body")
    if not all(e.get(k) for k in ("operator", "runtime", "status")):
        raise HTTPException(400, "operator, runtime, session_id, status are required")
    skill_name = _skill_use_name(e.get("skill"))
    skill_mode = _skill_mode(e.get("skill_mode"))
    if not e.get("session_id"):
        if skill_name:
            return {"ok": True, "logged": False, "skill_ignored": True}
        raise HTTPException(400, "operator, runtime, session_id, status are required")
    ts = e.get("ts") or now_iso()
    recv = now_iso()                               # server-authoritative time (§6)
    sid = e["session_id"]
    status, step = e["status"], e.get("current_step")

    # §5 read-side auth gate: drop sensitive fields unless read access is protected
    if not app.READ_AUTH_OK:
        for k in SENSITIVE_KEYS:
            e.pop(k, None)
    inp = _clip(e.get("input"), MAX_CONTENT)
    outp = _clip(e.get("output"), MAX_CONTENT)
    meta_json = _clip(json.dumps(e.get("meta"), ensure_ascii=False), MAX_META) if e.get("meta") else None

    with app._lock, closing(db()) as conn:
        # normalize identity: operator case/space-insensitive, runtime lowercased
        op = canon_operator(conn, e["operator"], recv)
        rt = (e["runtime"] or "").strip().lower()
        ag = e.get("agent") or rt                      # agent identity label
        verified = 1 if verify_operator(conn, op, x_tf_token) else 0

        # Usage is processed before heartbeat dedup so a repeated tool step can
        # still record the first sighting of session×skill.
        if skill_name:
            conn.execute("""INSERT OR IGNORE INTO skill_uses
              (session_id,skill,mode,operator,runtime,day,first_seen) VALUES(?,?,?,?,?,?,?)""",
              (sid, skill_name, skill_mode, op, rt, recv[:10], recv))
            conn.execute("INSERT OR IGNORE INTO skills_seen(name,first_day) VALUES(?,?)",
                         (skill_name, recv[:10]))

        # OPTIONAL profile payload — full-snapshot replace per identity (§6)
        profile = {k: e[k] for k in PROFILE_KEYS if e.get(k) is not None}
        if profile:
            conn.execute("""INSERT INTO profiles(operator,ak,runtime,json,updated)
              VALUES(?,?,?,?,?)
              ON CONFLICT(operator,ak,runtime) DO UPDATE SET json=excluded.json,updated=excluded.updated""",
              (op, ag, rt, json.dumps(profile, ensure_ascii=False), recv))
            for nm in _skill_names(profile.get("skills")):
                conn.execute("INSERT OR IGNORE INTO skills_seen(name,first_day) VALUES(?,?)", (nm, recv[:10]))

        # OPTIONAL shim_version — sticky per identity. Top-level field on every
        # heartbeat in the new protocol; older shims only set it inside the
        # SessionStart profile, but tf_profile.collect() flattens it to the same
        # top-level key, so a single read covers both. We never clear the row
        # when the field is absent — that's the whole point of sticky.
        sv = e.get("shim_version")
        if isinstance(sv, str) and sv.strip():
            conn.execute("""INSERT INTO agent_shim_versions(operator,ak,runtime,shim_version,updated)
              VALUES(?,?,?,?,?)
              ON CONFLICT(operator,ak,runtime) DO UPDATE SET
                shim_version=excluded.shim_version, updated=excluded.updated""",
              (op, ag, rt, sv.strip(), recv))

        # dedup key now includes session_id (§6) so concurrent sessions of one
        # identity don't swallow each other's liveness.
        last = conn.execute("""SELECT id,status,current_step FROM events
            WHERE operator=? AND runtime=? AND COALESCE(agent,runtime)=? AND session_id=?
            ORDER BY id DESC LIMIT 1""", (op, rt, ag, sid)).fetchone()
        if last and last["status"] == status and (last["current_step"] or "") == (step or ""):
            # pure heartbeat: nothing changed -> only refresh liveness (server time)
            conn.execute("UPDATE events SET last_seen=? WHERE id=?", (recv, last["id"]))
            conn.commit()
            return {"ok": True, "heartbeat": True, "verified": bool(verified)}
        conn.execute("""INSERT INTO events
          (ts,recv,day,last_seen,v,operator,agent,runtime,session_id,parent_session_id,verified,
           status,task,current_step,model,input,output,meta,source)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (ts, recv, recv[:10], recv, e.get("v"), op, e.get("agent"), rt, sid,
           e.get("parent_session_id"), verified, status,
           e.get("task"), step, e.get("model"), inp, outp, meta_json, "heartbeat"))
        _maybe_prune(conn)
        conn.commit()
    return {"ok": True, "logged": True, "verified": bool(verified)}
