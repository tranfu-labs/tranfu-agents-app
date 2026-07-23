"""ingest 域路由(对应 openspec/specs/ingest/spec.md)。

- POST /v1/enroll  — admin 签发 per-operator token
- POST /v1/events  — 心跳事件采集

注:DELETE /v1/events(legacy 兼容路径)归属 admin 域,见 server/routes/admin.py。
"""
import json
import secrets
import threading
import time
from contextlib import closing

from fastapi import APIRouter, Header, HTTPException, Request

from server.config import STALE_SECONDS
from server.db import _audit, _clip, _maybe_prune, _parse, _sha, db, now_iso, now_utc, stats_day_for
from server.identity import canon_operator, verify_operator
from server.profile import _skill_mode, _skill_names, _skill_use_name
from server.security import (
    _client_host, _rate_register_failure, _rate_register_success, _rate_retry_after,
    check_auth,
)

router = APIRouter()

_heartbeat_pending_lock = threading.Lock()
_heartbeat_pending = {}
_heartbeat_thread_started = False


def _mark_state_dirty():
    from server.routes.board import mark_state_dirty
    mark_state_dirty()


def _heartbeat_batch_seconds():
    from server import app
    try:
        return max(0.0, float(app.HEARTBEAT_BATCH_SECONDS))
    except Exception:  # pragma: no cover
        return 15.0


def _start_heartbeat_flush_thread():
    global _heartbeat_thread_started
    with _heartbeat_pending_lock:
        if _heartbeat_thread_started:
            return
        _heartbeat_thread_started = True
    t = threading.Thread(target=_heartbeat_flush_loop, name="tf-heartbeat-flush", daemon=True)
    t.start()


def _heartbeat_flush_loop():
    while True:
        interval = _heartbeat_batch_seconds()
        time.sleep(interval if interval > 0 else 1.0)
        if interval > 0:
            flush_heartbeat_batch()


def _queue_heartbeat(event_id, last_seen):
    if _heartbeat_batch_seconds() <= 0:
        return False
    _start_heartbeat_flush_thread()
    with _heartbeat_pending_lock:
        _heartbeat_pending[int(event_id)] = last_seen
    return True


def _drop_pending_heartbeat(event_id):
    if event_id is None:
        return
    with _heartbeat_pending_lock:
        _heartbeat_pending.pop(int(event_id), None)


def _pending_heartbeat(event_id):
    if event_id is None:
        return None
    with _heartbeat_pending_lock:
        return _heartbeat_pending.get(int(event_id))


def _last_confirmed_heartbeat(last):
    return _pending_heartbeat(last["id"]) or last["last_seen"] or last["recv"] or last["ts"]


def _heartbeat_gap_exceeded(confirmed, recv_dt):
    """True when a same-state report resumes after the confirmed live segment."""
    if not confirmed:
        return False
    try:
        confirmed_dt = _parse(confirmed)
        return (recv_dt - confirmed_dt).total_seconds() > STALE_SECONDS
    except (TypeError, ValueError):
        return False


def flush_heartbeat_batch():
    with _heartbeat_pending_lock:
        batch = dict(_heartbeat_pending)
        _heartbeat_pending.clear()
    if not batch:
        return 0
    from server import app
    with app._lock, closing(db()) as conn:
        conn.executemany(
            "UPDATE events SET last_seen=? WHERE id=?",
            [(last_seen, event_id) for event_id, last_seen in sorted(batch.items())],
        )
        conn.commit()
    _mark_state_dirty()
    return len(batch)


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
    recv_dt = now_utc()                            # server-authoritative time (§6)
    recv = recv_dt.isoformat()
    day = stats_day_for(recv_dt)
    ts = e.get("ts") or recv
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
        state_dirty = False
        # normalize identity: operator case/space-insensitive, runtime lowercased
        op = canon_operator(conn, e["operator"], recv)
        rt = (e["runtime"] or "").strip().lower()
        ag = e.get("agent") or rt                      # agent identity label
        verified = 1 if verify_operator(conn, op, x_tf_token) else 0

        # Usage is processed before heartbeat dedup so a repeated tool step can
        # still record the first sighting of session×skill.
        if skill_name:
            if conn.execute("""INSERT OR IGNORE INTO skill_uses
              (session_id,skill,mode,operator,runtime,day,first_seen) VALUES(?,?,?,?,?,?,?)""",
              (sid, skill_name, skill_mode, op, rt, day, recv)).rowcount:
                state_dirty = True
            conn.execute("INSERT OR IGNORE INTO skills_seen(name,first_day) VALUES(?,?)",
                         (skill_name, day))

        # OPTIONAL profile payload — full-snapshot replace per identity (§6)
        profile = {k: e[k] for k in PROFILE_KEYS if e.get(k) is not None}
        if profile:
            state_dirty = True
            conn.execute("""INSERT INTO profiles(operator,ak,runtime,json,updated)
              VALUES(?,?,?,?,?)
              ON CONFLICT(operator,ak,runtime) DO UPDATE SET json=excluded.json,updated=excluded.updated""",
              (op, ag, rt, json.dumps(profile, ensure_ascii=False), recv))
            for nm in _skill_names(profile.get("skills")):
                conn.execute("INSERT OR IGNORE INTO skills_seen(name,first_day) VALUES(?,?)", (nm, day))

        # OPTIONAL shim_version — sticky per identity. Top-level field on every
        # heartbeat in the new protocol; older shims only set it inside the
        # SessionStart profile, but tf_profile.collect() flattens it to the same
        # top-level key, so a single read covers both. We never clear the row
        # when the field is absent — that's the whole point of sticky.
        sv = e.get("shim_version")
        if isinstance(sv, str) and sv.strip():
            if conn.execute("""INSERT INTO agent_shim_versions(operator,ak,runtime,shim_version,updated)
              VALUES(?,?,?,?,?)
              ON CONFLICT(operator,ak,runtime) DO UPDATE SET
                shim_version=excluded.shim_version, updated=excluded.updated
              WHERE agent_shim_versions.shim_version IS NOT excluded.shim_version""",
              (op, ag, rt, sv.strip(), recv)).rowcount:
                state_dirty = True

        # dedup key now includes session_id (§6) so concurrent sessions of one
        # identity don't swallow each other's liveness.
        last = conn.execute("""SELECT id,status,current_step,last_seen,recv,ts FROM events
            WHERE operator=? AND runtime=? AND COALESCE(agent,runtime)=? AND session_id=?
            ORDER BY id DESC LIMIT 1""", (op, rt, ag, sid)).fetchone()
        same_state = (last and last["status"] == status
                      and (last["current_step"] or "") == (step or ""))
        confirmed = _last_confirmed_heartbeat(last) if same_state else None
        if same_state and not _heartbeat_gap_exceeded(confirmed, recv_dt):
            if state_dirty or not _queue_heartbeat(last["id"], recv):
                # semantic writes stay immediate; otherwise pure liveness can batch.
                conn.execute("UPDATE events SET last_seen=? WHERE id=?", (recv, last["id"]))
                state_dirty = True
            conn.commit()
            if state_dirty:
                _mark_state_dirty()
            return {"ok": True, "heartbeat": True, "verified": bool(verified)}
        if same_state and confirmed and confirmed != last["last_seen"]:
            # Preserve the last pending heartbeat as the old segment endpoint
            # before a stale-gap recovery starts a new row.
            conn.execute("UPDATE events SET last_seen=? WHERE id=?", (confirmed, last["id"]))
        _drop_pending_heartbeat(last["id"] if last else None)
        event_source = "heartbeat_resume" if same_state else "heartbeat"
        conn.execute("""INSERT INTO events
          (ts,recv,day,last_seen,v,operator,agent,runtime,session_id,parent_session_id,verified,
           status,task,current_step,model,input,output,meta,source)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (ts, recv, day, recv, e.get("v"), op, e.get("agent"), rt, sid,
           e.get("parent_session_id"), verified, status,
           e.get("task"), step, e.get("model"), inp, outp, meta_json, event_source))
        _maybe_prune(conn)
        conn.commit()
    _mark_state_dirty()
    return {"ok": True, "logged": True, "verified": bool(verified)}
