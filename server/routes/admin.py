"""admin 域路由与清理算子(对应 openspec/specs/admin/spec.md)。

包含:
- /api/admin/{inventory,preview,trash,restore,export}
- DELETE /api/admin/data
- DELETE /v1/events(legacy curl 兼容路径)
- targets 解析、resolve、preview、purge、restore 全部算子族
- _active_sessions / _active_sessions_all(看「是否还有活跃会话」用)

行为零变更:鉴权 / 限流 / 删除模型 / 审计 / 软删除 / 导出确认 / IP 取值 等所有 MUST
规则与 spec 完全一致。
"""
import hashlib
import json
import os
import uuid
from contextlib import closing

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from server.config import ACTIVE_ST, STALE_SECONDS
from server.db import (
    _age, _audit, _clip, _json, _maybe_prune_trash, db,
    now_iso,
)
from server.identity import _norm_op
from server.profile import _skill_use_name
from server.security import check_admin

router = APIRouter()


def _mark_state_dirty():
    from server.routes.board import mark_state_dirty
    mark_state_dirty()


# ---------------------------------------------------------------- destructive cleanup (admin)
def _rowdict(row):
    return {k: row[k] for k in row.keys()}


def _marks(items):
    return ",".join("?" for _ in items)


def _skill_key(row_or_key):
    if isinstance(row_or_key, tuple):
        return row_or_key
    return (row_or_key["session_id"], row_or_key["skill"], row_or_key["mode"] or "used")


def _skill_key_s(key):
    return "\x1f".join("" if v is None else str(v) for v in key)


def _profile_key(row_or_key):
    if isinstance(row_or_key, tuple):
        return row_or_key
    return (row_or_key["operator"], row_or_key["ak"], row_or_key["runtime"])


def _profile_key_s(key):
    return "\x1f".join("" if v is None else str(v) for v in key)


def _validate_targets(targets):
    if not isinstance(targets, list) or not targets:
        raise HTTPException(400, "targets must be a non-empty array")
    out = []
    for target in targets:
        if not isinstance(target, dict):
            raise HTTPException(400, "each target must be an object")
        kinds = []
        if target.get("session_ids") is not None:
            kinds.append("session_ids")
        if target.get("skill") is not None:
            kinds.append("skill")
        if target.get("before_day") is not None:
            kinds.append("before_day")
        elif target.get("operator") is not None:
            kinds.append("operator")
        if len(kinds) != 1:
            raise HTTPException(400, "each target must select exactly one target kind")
        if target.get("session_ids") is not None:
            sids = target.get("session_ids")
            if isinstance(sids, str):
                sids = [sids]
            if not isinstance(sids, list) or not all(isinstance(s, str) and s for s in sids):
                raise HTTPException(400, "session_ids must be non-empty strings")
            clean = dict(target)
            clean["session_ids"] = sids
            out.append(clean)
            continue
        if target.get("before_day") is not None:
            if not isinstance(target.get("before_day"), str) or len(target["before_day"]) != 10:
                raise HTTPException(400, "before_day must be YYYY-MM-DD")
            if not target.get("operator"):
                raise HTTPException(400, "before_day requires operator")
        if target.get("operator") is not None and not isinstance(target.get("operator"), str):
            raise HTTPException(400, "operator must be a string")
        if target.get("skill") is not None:
            skill = _skill_use_name(target.get("skill"))
            if not skill:
                raise HTTPException(400, "skill must be a non-empty string")
            clean = dict(target)
            clean["skill"] = skill
            out.append(clean)
            continue
        out.append(dict(target))
    return out


def _event_ids_for_sessions(conn, session_ids, operator_norm=None):
    # operator_norm 非空时收口到该 operator 自身的行(共用 session 不误伤他人);
    # 为 None 时整删 session 全部行(供 session_ids 显式选择器用)。
    if not session_ids:
        return set()
    sql = f"SELECT id FROM events WHERE session_id IN ({_marks(session_ids)})"
    params = list(session_ids)
    if operator_norm is not None:
        sql += " AND lower(trim(COALESCE(operator,'')))=?"
        params.append(operator_norm)
    rows = conn.execute(sql, params).fetchall()
    return {int(r["id"]) for r in rows}


def _skill_keys_for_sessions(conn, session_ids, operator_norm=None):
    if not session_ids:
        return set()
    sql = f"SELECT session_id,skill,mode FROM skill_uses WHERE session_id IN ({_marks(session_ids)})"
    params = list(session_ids)
    if operator_norm is not None:
        sql += " AND lower(trim(COALESCE(operator,'')))=?"
        params.append(operator_norm)
    rows = conn.execute(sql, params).fetchall()
    return {_skill_key(r) for r in rows}


def _session_ids_by_operator(conn, operator, agent=None, runtime=None):
    norm = _norm_op(operator)
    params = [norm]
    clauses = ["lower(trim(COALESCE(operator,'')))=?"]
    if agent:
        clauses.append("COALESCE(agent,runtime)=?")
        params.append(agent)
    if runtime:
        clauses.append("lower(trim(COALESCE(runtime,'')))=?")
        params.append((runtime or "").strip().lower())
    event_rows = conn.execute(f"""SELECT DISTINCT session_id FROM events
      WHERE session_id IS NOT NULL AND {' AND '.join(clauses)}""", params).fetchall()
    sids = {r["session_id"] for r in event_rows if r["session_id"]}
    if not agent:
        sk_params = [norm]
        sk_clauses = ["lower(trim(COALESCE(operator,'')))=?"]
        if runtime:
            sk_clauses.append("lower(trim(COALESCE(runtime,'')))=?")
            sk_params.append((runtime or "").strip().lower())
        sk_rows = conn.execute(f"""SELECT DISTINCT session_id FROM skill_uses
          WHERE session_id IS NOT NULL AND {' AND '.join(sk_clauses)}""", sk_params).fetchall()
        sids.update(r["session_id"] for r in sk_rows if r["session_id"])
    return sids


def _session_ids_before_day(conn, before_day, operator, agent=None, runtime=None):
    norm = _norm_op(operator)
    params = [before_day, norm]
    clauses = ["day < ?", "lower(trim(COALESCE(operator,'')))=?"]
    if agent:
        clauses.append("COALESCE(agent,runtime)=?")
        params.append(agent)
    if runtime:
        clauses.append("lower(trim(COALESCE(runtime,'')))=?")
        params.append((runtime or "").strip().lower())
    rows = conn.execute(f"""SELECT DISTINCT session_id FROM events
      WHERE session_id IS NOT NULL AND {' AND '.join(clauses)}""", params).fetchall()
    sids = {r["session_id"] for r in rows if r["session_id"]}
    if not agent:
        sk_params = [before_day, norm]
        sk_clauses = ["day < ?", "lower(trim(COALESCE(operator,'')))=?"]
        if runtime:
            sk_clauses.append("lower(trim(COALESCE(runtime,'')))=?")
            sk_params.append((runtime or "").strip().lower())
        sk_rows = conn.execute(f"""SELECT DISTINCT session_id FROM skill_uses
          WHERE session_id IS NOT NULL AND {' AND '.join(sk_clauses)}""", sk_params).fetchall()
        sids.update(r["session_id"] for r in sk_rows if r["session_id"])
    return sids


def _skill_keys_for_skill(conn, skill):
    rows = conn.execute("""SELECT session_id,skill,mode FROM skill_uses
      WHERE skill=?""", (skill,)).fetchall()
    return {_skill_key(r) for r in rows}


def _profile_keys_for_selector(conn, operator, agent=None, runtime=None):
    norm = _norm_op(operator)
    params = [norm]
    clauses = ["lower(trim(COALESCE(operator,'')))=?"]
    if agent:
        clauses.append("ak=?")
        params.append(agent)
    if runtime:
        clauses.append("lower(trim(COALESCE(runtime,'')))=?")
        params.append((runtime or "").strip().lower())
    rows = conn.execute(f"""SELECT operator,ak,runtime FROM profiles
      WHERE {' AND '.join(clauses)}""", params).fetchall()
    return {_profile_key(r) for r in rows}


def _expand_child_sessions(conn, session_ids, operator_norm=None):
    # operator_norm 非空时后代会话只在同 operator 范围内扩展,不借后代把他人行卷入。
    all_sids = set(session_ids)
    frontier = set(session_ids)
    while frontier:
        sql = f"""SELECT DISTINCT session_id FROM events
          WHERE parent_session_id IN ({_marks(frontier)})
            AND session_id IS NOT NULL"""
        params = list(frontier)
        if operator_norm is not None:
            sql += " AND lower(trim(COALESCE(operator,'')))=?"
            params.append(operator_norm)
        rows = conn.execute(sql, params).fetchall()
        found = {r["session_id"] for r in rows if r["session_id"] and r["session_id"] not in all_sids}
        if not found:
            break
        all_sids.update(found)
        frontier = found
    return all_sids


def _fetch_event_rows(conn, event_ids):
    if not event_ids:
        return []
    return [_rowdict(r) for r in conn.execute(
        f"SELECT * FROM events WHERE id IN ({_marks(event_ids)}) ORDER BY id",
        list(event_ids)).fetchall()]


def _fetch_skill_rows(conn, skill_keys):
    rows = []
    for sid, skill, mode in sorted(skill_keys):
        row = conn.execute("""SELECT * FROM skill_uses
          WHERE session_id=? AND skill=? AND mode=?""", (sid, skill, mode)).fetchone()
        if row:
            rows.append(_rowdict(row))
    return rows


def _fetch_profile_rows(conn, profile_keys):
    rows = []
    for operator, ak, runtime in sorted(profile_keys):
        row = conn.execute("""SELECT * FROM profiles
          WHERE operator=? AND ak=? AND runtime=?""", (operator, ak, runtime)).fetchone()
        if row:
            rows.append(_rowdict(row))
    return rows


def _fetch_operator_rows(conn, operators):
    rows, seen = [], set()
    for norm in sorted(_candidate_operator_norms(operators)):
        for row in conn.execute("""SELECT * FROM operators
          WHERE lower(trim(operator))=? ORDER BY operator""", (norm,)):
            item = _rowdict(row)
            key = item.get("operator") or ""
            if key not in seen:
                seen.add(key)
                rows.append(item)
    return rows


def _resolution_token(resolved):
    payload = {
        "events": sorted(int(i) for i in resolved["event_ids"]),
        "skill_uses": sorted(_skill_key_s(k) for k in resolved["skill_keys"]),
        "profiles": sorted(_profile_key_s(k) for k in resolved["profile_keys"]),
        "operators": sorted(resolved.get("operator_keys") or []),
    }
    return hashlib.sha256(_json(payload).encode()).hexdigest()


def _resolve_admin_targets(conn, targets, cascade_children=False, revoke=False):
    targets = _validate_targets(targets)
    # 逐 target 带各自 operator 约束解析后取并集:operator / before_day 路径收口到本人行;
    # 裸 session_ids 路径整删该 session(用户精确点选)。session_ids 仅用于活跃会话预警。
    session_ids, event_ids, skill_keys, profile_keys = set(), set(), set(), set()
    plain_session_ids = set()
    target_ops = set()
    for target in targets:
        if target.get("session_ids") is not None:
            plain_session_ids.update(target["session_ids"])
            continue
        if target.get("skill") is not None:
            skill_keys.update(_skill_keys_for_skill(conn, target["skill"]))
            continue
        operator = target.get("operator")
        agent = target.get("agent")
        runtime = target.get("runtime")
        if operator is not None:
            target_ops.add(operator)
        if target.get("before_day") is not None:
            sids = _session_ids_before_day(conn, target["before_day"], operator, agent, runtime)
        elif operator is not None:
            sids = _session_ids_by_operator(conn, operator, agent, runtime)
            if target.get("profile", True):
                profile_keys.update(_profile_keys_for_selector(conn, operator, agent, runtime))
        else:
            continue
        op_norm = _norm_op(operator)
        if cascade_children and sids:
            sids = _expand_child_sessions(conn, sids, op_norm)
        session_ids.update(sids)
        event_ids.update(_event_ids_for_sessions(conn, sids, op_norm))
        skill_keys.update(_skill_keys_for_sessions(conn, sids, op_norm))
    if plain_session_ids:
        if cascade_children:
            plain_session_ids = _expand_child_sessions(conn, plain_session_ids)
        session_ids.update(plain_session_ids)
        event_ids.update(_event_ids_for_sessions(conn, plain_session_ids))
        skill_keys.update(_skill_keys_for_sessions(conn, plain_session_ids))
    resolved = {
        "targets": targets,
        "session_ids": set(session_ids),
        "event_ids": event_ids,
        "skill_keys": skill_keys,
        "profile_keys": profile_keys,
        "target_operators": target_ops,
        "operator_keys": set(),
    }
    if revoke:
        event_rows = _fetch_event_rows(conn, event_ids)
        skill_rows = _fetch_skill_rows(conn, skill_keys)
        profile_rows = _fetch_profile_rows(conn, profile_keys)
        affected_ops = _operators_from_rows(event_rows, skill_rows, profile_rows) | set(target_ops)
        resolved["operator_keys"] = {r["operator"] for r in _fetch_operator_rows(conn, affected_ops)}
    resolved["preview_token"] = _resolution_token(resolved)
    return resolved


def _active_sessions(conn, session_ids):
    if not session_ids:
        return []
    rows = conn.execute(f"""
      SELECT e.* FROM events e
      JOIN (SELECT session_id, MAX(id) mid FROM events
            WHERE session_id IN ({_marks(session_ids)}) GROUP BY session_id) last
      ON e.id = last.mid
    """, list(session_ids)).fetchall()
    active = []
    for r in rows:
        if r["status"] in ACTIVE_ST and _age(r["last_seen"] or r["recv"] or r["ts"]) <= STALE_SECONDS:
            active.append({
                "session_id": r["session_id"],
                "operator": r["operator"],
                "runtime": r["runtime"],
                "agent": r["agent"],
                "status": r["status"],
                "last_seen": r["last_seen"] or r["recv"] or r["ts"],
            })
    active.sort(key=lambda x: (x["operator"] or "", x["session_id"] or ""))
    return active


def _active_sessions_all(conn):
    rows = conn.execute("""
      SELECT e.* FROM events e
      JOIN (SELECT session_id, MAX(id) mid FROM events
            WHERE session_id IS NOT NULL AND session_id != ''
            GROUP BY session_id) last
      ON e.id = last.mid
    """).fetchall()
    active = []
    for r in rows:
        if r["status"] in ACTIVE_ST and _age(r["last_seen"] or r["recv"] or r["ts"]) <= STALE_SECONDS:
            active.append({
                "session_id": r["session_id"],
                "operator": r["operator"],
                "runtime": r["runtime"],
                "agent": r["agent"],
                "status": r["status"],
                "last_seen": r["last_seen"] or r["recv"] or r["ts"],
            })
    active.sort(key=lambda x: (x["operator"] or "", x["session_id"] or ""))
    return active


def _operators_from_rows(*row_lists):
    out = set()
    for rows in row_lists:
        for row in rows:
            op = (row.get("operator") or "").strip()
            if op:
                out.add(op)
    return out


def _candidate_operator_norms(operators):
    return {_norm_op(op) for op in operators if _norm_op(op)}


def _first_day_changes(conn, skill_keys):
    by_skill = {}
    delete_keys = set(skill_keys)
    for key in skill_keys:
        by_skill.setdefault(key[1], set()).add(key)
    changes = []
    for skill in sorted(by_skill):
        old_row = conn.execute("SELECT first_day FROM skills_seen WHERE name=?", (skill,)).fetchone()
        old_day = old_row["first_day"] if old_row else None
        new_day = None
        for row in conn.execute("SELECT session_id,skill,mode,day FROM skill_uses WHERE skill=?", (skill,)):
            if _skill_key(row) in delete_keys:
                continue
            day = row["day"]
            if day and (new_day is None or day < new_day):
                new_day = day
        if old_day != new_day:
            changes.append({"skill": skill, "from": old_day, "to": new_day})
    return changes


def _identity_clears(conn, event_ids, skill_keys, operators):
    event_ids = set(event_ids)
    skill_keys = set(skill_keys)
    cleared = []
    for norm in sorted(_candidate_operator_norms(operators)):
        identity = conn.execute("SELECT display FROM identities WHERE norm=?", (norm,)).fetchone()
        if not identity:
            continue
        remains = False
        for r in conn.execute("""SELECT id FROM events
          WHERE lower(trim(COALESCE(operator,'')))=?""", (norm,)):
            if int(r["id"]) not in event_ids:
                remains = True
                break
        if not remains:
            for r in conn.execute("""SELECT session_id,skill,mode FROM skill_uses
              WHERE lower(trim(COALESCE(operator,'')))=?""", (norm,)):
                if _skill_key(r) not in skill_keys:
                    remains = True
                    break
        if not remains:
            cleared.append(identity["display"])
    return cleared


def _preview_admin_resolution(conn, resolved, revoke=False):
    from server import app  # 延迟读 ADMIN_MAX_ROWS
    event_rows = _fetch_event_rows(conn, resolved["event_ids"])
    skill_rows = _fetch_skill_rows(conn, resolved["skill_keys"])
    profile_rows = _fetch_profile_rows(conn, resolved["profile_keys"])
    operator_rows = _fetch_operator_rows(conn, resolved.get("operator_keys") or []) if revoke else []
    affected_ops = (
        _operators_from_rows(event_rows, skill_rows, profile_rows, operator_rows)
        | set(resolved["target_operators"])
    )
    active = _active_sessions(conn, resolved["session_ids"] | {r["session_id"] for r in skill_rows if r.get("session_id")})
    counts = {
        "events": len(event_rows),
        "skill_uses": len(skill_rows),
        "profiles": len(profile_rows),
        "operators": len(operator_rows),
    }
    total_rows = counts["events"] + counts["skill_uses"] + counts["profiles"] + counts["operators"]
    operators = sorted(op for op in affected_ops if op)
    return {
        "ok": True,
        "preview_token": resolved["preview_token"],
        "counts": counts,
        "total_rows": total_rows,
        "operators": operators,
        "active_sessions": active,
        "requires_force": bool(active),
        "requires_confirm": total_rows > app.ADMIN_MAX_ROWS or len(operators) > 1,
        "max_rows": app.ADMIN_MAX_ROWS,
        "effects": {
            "first_day_changes": _first_day_changes(conn, resolved["skill_keys"]),
            "identities_cleared": _identity_clears(conn, resolved["event_ids"], resolved["skill_keys"], affected_ops),
            "profiles_cleared": [
                {"operator": r["operator"], "agent": r["ak"], "runtime": r["runtime"]}
                for r in profile_rows
            ],
        },
    }


def _recompute_derived(conn, skills, operators):
    for skill in sorted({s for s in skills if s}):
        row = conn.execute("""SELECT MIN(day) first_day FROM skill_uses
          WHERE skill=? AND day IS NOT NULL""", (skill,)).fetchone()
        first_day = row["first_day"] if row else None
        if first_day:
            conn.execute("""INSERT INTO skills_seen(name,first_day) VALUES(?,?)
              ON CONFLICT(name) DO UPDATE SET first_day=excluded.first_day""",
              (skill, first_day))
        else:
            conn.execute("DELETE FROM skills_seen WHERE name=?", (skill,))

    for norm in sorted(_candidate_operator_norms(operators)):
        candidates = []
        for r in conn.execute("""SELECT operator, MIN(COALESCE(recv,ts,'')) first_seen
          FROM events WHERE lower(trim(COALESCE(operator,'')))=?
          GROUP BY operator""", (norm,)):
            candidates.append((r["first_seen"] or "", r["operator"]))
        for r in conn.execute("""SELECT operator, MIN(COALESCE(first_seen,day,'')) first_seen
          FROM skill_uses WHERE lower(trim(COALESCE(operator,'')))=?
          GROUP BY operator""", (norm,)):
            candidates.append((r["first_seen"] or "", r["operator"]))
        candidates = [(ts, op) for ts, op in candidates if (op or "").strip()]
        if candidates:
            first_seen, display = sorted(candidates, key=lambda x: (x[0] or "9999", x[1] or ""))[0]
            conn.execute("""INSERT INTO identities(norm,display,created) VALUES(?,?,?)
              ON CONFLICT(norm) DO UPDATE SET display=excluded.display,created=excluded.created""",
              (norm, display, first_seen))
        else:
            conn.execute("DELETE FROM identities WHERE norm=?", (norm,))


def _delete_skill_rows(conn, skill_keys):
    deleted = 0
    for sid, skill, mode in sorted(skill_keys):
        deleted += conn.execute("""DELETE FROM skill_uses
          WHERE session_id=? AND skill=? AND mode=?""", (sid, skill, mode)).rowcount
    return deleted


def _delete_profile_rows(conn, profile_keys):
    deleted = 0
    for operator, ak, runtime in sorted(profile_keys):
        deleted += conn.execute("""DELETE FROM profiles
          WHERE operator=? AND ak=? AND runtime=?""", (operator, ak, runtime)).rowcount
        # sticky shim version is per-agent identity too; admin cleanup that
        # removes the profile MUST drop this row alongside it, otherwise a
        # purge-then-reregister cycle resurrects a stale shim version.
        conn.execute("""DELETE FROM agent_shim_versions
          WHERE operator=? AND ak=? AND runtime=?""", (operator, ak, runtime))
    return deleted


def _purge(conn, resolved, actor, selector, revoke=False):
    event_rows = _fetch_event_rows(conn, resolved["event_ids"])
    skill_rows = _fetch_skill_rows(conn, resolved["skill_keys"])
    profile_rows = _fetch_profile_rows(conn, resolved["profile_keys"])
    operator_rows = _fetch_operator_rows(conn, resolved.get("operator_keys") or []) if revoke else []
    affected_skills = {r["skill"] for r in skill_rows if r.get("skill")}
    affected_ops = (
        _operators_from_rows(event_rows, skill_rows, profile_rows, operator_rows)
        | set(resolved["target_operators"])
    )
    batch_id = str(uuid.uuid4())
    counts = {
        "events": 0,
        "skill_uses": 0,
        "profiles": 0,
        "operators": 0,
    }
    if resolved["event_ids"]:
        counts["events"] = conn.execute(
            f"DELETE FROM events WHERE id IN ({_marks(resolved['event_ids'])})",
            list(resolved["event_ids"])).rowcount
    counts["skill_uses"] = _delete_skill_rows(conn, resolved["skill_keys"])
    counts["profiles"] = _delete_profile_rows(conn, resolved["profile_keys"])
    if revoke:
        for norm in _candidate_operator_norms(affected_ops):
            counts["operators"] += conn.execute(
                "DELETE FROM operators WHERE lower(trim(operator))=?", (norm,)).rowcount
    _recompute_derived(conn, affected_skills, affected_ops)
    payload = {
        "events": event_rows,
        "skill_uses": skill_rows,
        "profiles": profile_rows,
        "operators": operator_rows,
    }
    conn.execute("""INSERT INTO admin_trash(batch_id,created,actor,selector,payload,counts,restored)
      VALUES(?,?,?,?,?,?,0)""",
      (batch_id, now_iso(), actor, _json(selector), _json(payload), _json(counts)))
    _audit(conn, actor, "delete", selector, counts, batch_id)
    return {"ok": True, "batch_id": batch_id, "counts": counts, "deleted": counts["events"]}


def _insert_row(conn, table, row, omit=()):
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    data = {k: v for k, v in row.items() if k in existing and k not in omit}
    if not data:
        return 0
    cols = list(data.keys())
    sql = f"""INSERT OR IGNORE INTO {table}({','.join(cols)})
      VALUES ({','.join('?' for _ in cols)})"""
    return conn.execute(sql, [data[c] for c in cols]).rowcount


def _begin_admin_write(conn):
    conn.execute("BEGIN IMMEDIATE")


def _restore_admin_batch(conn, batch_id, actor):
    row = conn.execute("SELECT * FROM admin_trash WHERE batch_id=?", (batch_id,)).fetchone()
    if not row:
        raise HTTPException(404, "batch not found")
    if row["restored"]:
        raise HTTPException(409, "batch already restored")
    payload = json.loads(row["payload"] or "{}")
    report = {}
    affected_skills, affected_ops = set(), set()
    for table in ("events", "skill_uses", "profiles", "operators"):
        inserted = 0
        rows = payload.get(table) or []
        for item in rows:
            if table == "events":
                inserted += _insert_row(conn, table, item, omit=("id",))
            else:
                inserted += _insert_row(conn, table, item)
            if item.get("skill"):
                affected_skills.add(item["skill"])
            if item.get("operator"):
                affected_ops.add(item["operator"])
        report[table] = {"attempted": len(rows), "inserted": inserted, "skipped": len(rows) - inserted}
    _recompute_derived(conn, affected_skills, affected_ops)
    conn.execute("UPDATE admin_trash SET restored=1 WHERE batch_id=?", (batch_id,))
    _audit(conn, actor, "restore", {"batch_id": batch_id}, report, batch_id)
    return {"ok": True, "batch_id": batch_id, "restored": report}


def _admin_inventory(conn, q="", limit=200, offset=0):
    needle = (q or "").strip().casefold()
    limit = max(1, min(int(limit or 200), 500))
    offset = max(0, int(offset or 0))
    active_by_session = {r["session_id"]: r for r in _active_sessions_all(conn)}
    active_identity_keys = {
        (
            r.get("operator") or "",
            r.get("agent") or r.get("runtime") or "",
            r.get("runtime") or "",
        )
        for r in active_by_session.values()
    }
    active_operator_keys = {r.get("operator") or "" for r in active_by_session.values()}
    active_session_ids = set(active_by_session)
    active_skills = set()
    if active_session_ids:
        ordered_sids = sorted(active_session_ids)
        for r in conn.execute(
            f"SELECT DISTINCT skill FROM skill_uses WHERE session_id IN ({_marks(ordered_sids)})",
            ordered_sids,
        ):
            active_skills.add(r["skill"] or "")

    operators, identities, sessions, skill_rows = {}, {}, {}, {}

    def touch_operator(op):
        key = op or ""
        return operators.setdefault(key, {
            "kind": "operator", "operator": key, "name": key or "(empty)",
            "events": 0, "skill_uses": 0, "profiles": 0, "identities": 0,
            "last_seen": None, "active": False,
        })

    def update_last(item, ts):
        if ts and (not item.get("last_seen") or ts > item["last_seen"]):
            item["last_seen"] = ts

    event_ts = "COALESCE(NULLIF(last_seen,''),NULLIF(recv,''),NULLIF(ts,''),'')"
    skill_ts = "COALESCE(NULLIF(first_seen,''),NULLIF(day,''),'')"

    for r in conn.execute(f"""
      SELECT COALESCE(operator,'') operator, COUNT(*) events, MAX({event_ts}) last_seen
      FROM events GROUP BY COALESCE(operator,'')
    """):
        item = touch_operator(r["operator"])
        item["events"] += r["events"]
        update_last(item, r["last_seen"])
        if r["operator"] in active_operator_keys:
            item["active"] = True

    for r in conn.execute(f"""
      SELECT COALESCE(operator,'') operator, COUNT(*) skill_uses, MAX({skill_ts}) last_seen
      FROM skill_uses GROUP BY COALESCE(operator,'')
    """):
        item = touch_operator(r["operator"])
        item["skill_uses"] += r["skill_uses"]
        update_last(item, r["last_seen"])
        if r["operator"] in active_operator_keys:
            item["active"] = True

    for r in conn.execute("""
      SELECT COALESCE(operator,'') operator, COUNT(*) profiles, MAX(COALESCE(updated,'')) last_seen
      FROM profiles GROUP BY COALESCE(operator,'')
    """):
        item = touch_operator(r["operator"])
        item["profiles"] += r["profiles"]
        update_last(item, r["last_seen"])

    for r in conn.execute(f"""
      SELECT COALESCE(operator,'') operator,
             COALESCE(NULLIF(agent,''),NULLIF(runtime,''),'') agent,
             COALESCE(runtime,'') runtime,
             COUNT(*) events,
             MAX({event_ts}) last_seen
      FROM events
      GROUP BY COALESCE(operator,''), COALESCE(NULLIF(agent,''),NULLIF(runtime,''),''), COALESCE(runtime,'')
    """):
        ikey = (r["operator"], r["agent"], r["runtime"])
        ident = identities.setdefault(ikey, {
            "kind": "identity", "operator": ikey[0], "agent": ikey[1], "runtime": ikey[2],
            "name": f"{ikey[0] or '(empty)'} / {ikey[1] or ikey[2] or '(none)'}",
            "events": 0, "skill_uses": 0, "profiles": 0, "last_seen": None, "active": False,
        })
        ident["events"] += r["events"]
        update_last(ident, r["last_seen"])
        if ikey in active_identity_keys:
            ident["active"] = True

    for r in conn.execute("""
      SELECT COALESCE(operator,'') operator,
             COALESCE(ak,'') agent,
             COALESCE(runtime,'') runtime,
             COUNT(*) profiles,
             MAX(COALESCE(updated,'')) last_seen
      FROM profiles
      GROUP BY COALESCE(operator,''), COALESCE(ak,''), COALESCE(runtime,'')
    """):
        ikey = (r["operator"], r["agent"], r["runtime"])
        ident = identities.setdefault(ikey, {
            "kind": "identity", "operator": ikey[0], "agent": ikey[1], "runtime": ikey[2],
            "name": f"{ikey[0] or '(empty)'} / {ikey[1] or ikey[2] or '(none)'}",
            "events": 0, "skill_uses": 0, "profiles": 0, "last_seen": None, "active": False,
        })
        ident["profiles"] += r["profiles"]
        update_last(ident, r["last_seen"])
        if ikey in active_identity_keys:
            ident["active"] = True

    for r in conn.execute(f"""
      SELECT stats.session_id, COALESCE(e.operator,'') operator,
             COALESCE(NULLIF(e.agent,''),NULLIF(e.runtime,''),'') agent,
             COALESCE(e.runtime,'') runtime,
             stats.events, stats.last_seen
      FROM (
        SELECT COALESCE(session_id,'') session_id, COUNT(*) events, MAX(id) mid, MAX({event_ts}) last_seen
        FROM events GROUP BY COALESCE(session_id,'')
      ) stats
      JOIN events e ON e.id = stats.mid
    """):
        sid = r["session_id"]
        sess = sessions.setdefault(sid, {
            "kind": "session", "session_id": sid, "operator": r["operator"],
            "agent": r["agent"], "runtime": r["runtime"], "name": sid,
            "events": 0, "skill_uses": 0, "last_seen": None, "active": False,
        })
        sess["events"] += r["events"]
        update_last(sess, r["last_seen"])
        if sid in active_by_session:
            sess["active"] = True

    for r in conn.execute(f"""
      SELECT COALESCE(session_id,'') session_id, COALESCE(operator,'') operator,
             COALESCE(runtime,'') runtime, COUNT(*) skill_uses, MAX({skill_ts}) last_seen
      FROM skill_uses GROUP BY COALESCE(session_id,''), COALESCE(operator,''), COALESCE(runtime,'')
    """):
        sid = r["session_id"]
        sess = sessions.setdefault(sid, {
            "kind": "session", "session_id": sid, "operator": r["operator"],
            "agent": "", "runtime": r["runtime"], "name": sid,
            "events": 0, "skill_uses": 0, "last_seen": None, "active": False,
        })
        sess["skill_uses"] += r["skill_uses"]
        update_last(sess, r["last_seen"])
        if sid in active_by_session:
            sess["active"] = True

    for r in conn.execute(f"""
      SELECT COALESCE(skill,'') skill,
             COUNT(*) skill_uses,
             SUM(CASE WHEN mode='equipped' THEN 0 ELSE 1 END) used,
             SUM(CASE WHEN mode='equipped' THEN 1 ELSE 0 END) equipped,
             COUNT(DISTINCT NULLIF(operator,'')) operators,
             MIN(NULLIF(day,'')) first_day,
             MAX({skill_ts}) last_seen
      FROM skill_uses GROUP BY COALESCE(skill,'')
    """):
        sk = r["skill"]
        item = skill_rows.setdefault(sk, {
            "kind": "skill", "skill": sk, "name": sk,
            "events": 0, "skill_uses": 0, "used": 0, "equipped": 0,
            "operators": 0, "first_day": None, "last_seen": None, "active": False,
        })
        item["skill_uses"] += r["skill_uses"]
        item["used"] += r["used"] or 0
        item["equipped"] += r["equipped"] or 0
        item["operators"] += r["operators"] or 0
        item["first_day"] = r["first_day"]
        update_last(item, r["last_seen"])
        if sk in active_skills:
            item["active"] = True

    for item in operators.values():
        item["identities"] = sum(1 for key in identities if key[0] == item["operator"])

    def filt(items):
        rows = list(items)
        if needle:
            rows = [r for r in rows if needle in _json(r).casefold()]
        rows.sort(key=lambda r: (not bool(r.get("active")), r.get("name") or ""))
        return rows[offset:offset + limit]

    return {
        "ok": True,
        "operators": filt(operators.values()),
        "identities": filt(identities.values()),
        "sessions": filt(sessions.values()),
        "skills": filt(skill_rows.values()),
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------- 端点
@router.get("/api/admin/inventory")
def admin_inventory(request: Request, q: str = "", limit: int = 200, offset: int = 0,
                    x_tf_admin_key: str = Header(default="")):
    from server import app
    check_admin(x_tf_admin_key, request, {"path": "/api/admin/inventory"})
    with app._lock, closing(db()) as conn:
        _maybe_prune_trash(conn)
        data = _admin_inventory(conn, q, limit, offset)
        conn.commit()
        return JSONResponse(data)


@router.post("/api/admin/preview")
async def admin_preview(request: Request, x_tf_admin_key: str = Header(default="")):
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = check_admin(x_tf_admin_key, request, body)
    targets = body.get("targets")
    with closing(db()) as conn:
        resolved = _resolve_admin_targets(
            conn, targets, bool(body.get("cascade_children")), bool(body.get("revoke")))
        preview = _preview_admin_resolution(conn, resolved, bool(body.get("revoke")))
    preview["actor"] = actor
    return JSONResponse(preview)


@router.delete("/api/admin/data")
async def admin_delete_data(request: Request, x_tf_admin_key: str = Header(default="")):
    from server import app
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = check_admin(x_tf_admin_key, request, body)
    targets = body.get("targets")
    with app._lock, closing(db()) as conn:
        _begin_admin_write(conn)
        resolved = _resolve_admin_targets(
            conn, targets, bool(body.get("cascade_children")), bool(body.get("revoke")))
        if body.get("preview_token") != resolved["preview_token"]:
            raise HTTPException(409, "preview_token mismatch; preview again")
        preview = _preview_admin_resolution(conn, resolved, bool(body.get("revoke")))
        if preview["requires_force"] and not body.get("force"):
            _audit(conn, actor, "denied", body, {"reason": "active_sessions"}, None)
            conn.commit()
            raise HTTPException(400, "active sessions require force=true")
        if preview["requires_confirm"] and int(body.get("confirm_count") or -1) != preview["total_rows"]:
            _audit(conn, actor, "denied", body, {"reason": "confirm_count", "total_rows": preview["total_rows"]}, None)
            conn.commit()
            raise HTTPException(400, "confirm_count must match total_rows")
        result = _purge(conn, resolved, actor, body, bool(body.get("revoke")))
        _maybe_prune_trash(conn)
        conn.commit()
    _mark_state_dirty()
    return JSONResponse(result)


@router.get("/api/admin/trash")
def admin_trash(request: Request, x_tf_admin_key: str = Header(default="")):
    from server import app
    check_admin(x_tf_admin_key, request, {"path": "/api/admin/trash"})
    with app._lock, closing(db()) as conn:
        _maybe_prune_trash(conn)
        rows = []
        for r in conn.execute("""SELECT batch_id,created,actor,selector,counts,restored
          FROM admin_trash ORDER BY created DESC LIMIT 200"""):
            item = _rowdict(r)
            for key in ("selector", "counts"):
                try:
                    item[key] = json.loads(item[key] or "{}")
                except Exception:
                    item[key] = {}
            item["restored"] = bool(item["restored"])
            rows.append(item)
        conn.commit()
        return JSONResponse({"ok": True, "trash": rows})


@router.post("/api/admin/restore")
async def admin_restore(request: Request, x_tf_admin_key: str = Header(default="")):
    from server import app
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = check_admin(x_tf_admin_key, request, body)
    batch_id = body.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        raise HTTPException(400, "batch_id required")
    with app._lock, closing(db()) as conn:
        _begin_admin_write(conn)
        result = _restore_admin_batch(conn, batch_id, actor)
        _maybe_prune_trash(conn)
        conn.commit()
    _mark_state_dirty()
    return JSONResponse(result)


@router.post("/api/admin/export")
async def admin_export(background_tasks: BackgroundTasks, request: Request,
                       x_tf_admin_key: str = Header(default="")):
    """Download a consistent SQLite snapshot of the whole DB.

    This is the single most damaging consequence of an admin-key leak: one call
    walks off with the ENTIRE database, including the protocol §5 sensitive
    fields (instructions/memory/input/output), irreversibly. So it is the most
    guarded: a POST (never a prefetchable/cacheable GET), behind the same rate
    limiter as every other admin route, requiring an explicit `confirm=EXPORT`,
    and audited as a high-risk action.

    Copying tf.db directly is unsafe in WAL mode: the live -wal file may hold
    committed-but-not-checkpointed pages, so a raw file copy can be torn or
    stale. `VACUUM INTO` writes a single self-contained snapshot under the
    writer lock, which we then stream and delete after the response is sent.
    """
    from server import app
    actor = check_admin(x_tf_admin_key, request, {"path": "/api/admin/export"})
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not (isinstance(body, dict) and body.get("confirm") == "EXPORT"):
        raise HTTPException(400, "whole-DB export requires confirm=EXPORT")
    stamp = app.datetime.now(app.timezone.utc).strftime("%Y%m%d-%H%M%S")
    snap_path = os.path.join(os.path.dirname(os.path.abspath(app.DB_PATH)) or ".",
                             f".tf-export-{stamp}-{uuid.uuid4().hex[:8]}.db")
    with app._lock, closing(db()) as conn:
        conn.execute("VACUUM INTO ?", (snap_path,))
        _audit(conn, actor, "export", {"path": "/api/admin/export", "risk": "high"},
               {"snapshot": stamp, "high_risk": True}, None)
        conn.commit()
    background_tasks.add_task(lambda p: os.path.exists(p) and os.remove(p), snap_path)
    return FileResponse(snap_path, media_type="application/x-sqlite3",
                        filename=f"tf-{stamp}.db")


@router.delete("/v1/events")
async def delete_events(request: Request, x_tf_admin_key: str = Header(default="")):
    """Legacy cleanup kept for curl compatibility — DEPRECATED, prefer
    /api/admin/data. It used to bypass every cleanup guardrail; it now enforces
    the same ones that don't need a prior preview round-trip: active sessions
    require force=true, and deletions over TF_ADMIN_MAX_ROWS (or spanning >1
    operator) require confirm_count matching total_rows. The preview_token step
    is intentionally NOT required so a one-shot curl can: delete -> read the
    rejected total_rows -> delete again with confirm_count."""
    from server import app
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")
    actor = check_admin(x_tf_admin_key, request, {"legacy": True, **body})
    sids = list(body.get("session_ids") or [])
    if isinstance(body.get("session_id"), str):
        sids.append(body["session_id"])
    operator = body.get("operator")
    if not sids and not operator:
        raise HTTPException(400, "need session_ids or operator")
    if sids and not all(isinstance(s, str) for s in sids):
        raise HTTPException(400, "session_ids must be strings")
    if sids:
        targets = [{"session_ids": sids}]
        by = "session_ids"
    else:
        targets = [{
            "operator": operator,
            "agent": body.get("agent"),
            "runtime": body.get("runtime"),
            "profile": bool(body.get("profile")),
        }]
        by = "identity"
    selector = {"legacy": True, **body, "targets": targets}
    with app._lock, closing(db()) as conn:
        _begin_admin_write(conn)
        resolved = _resolve_admin_targets(
            conn, targets, bool(body.get("cascade_children")), bool(body.get("revoke")))
        preview = _preview_admin_resolution(conn, resolved, bool(body.get("revoke")))
        if preview["requires_force"] and not body.get("force"):
            _audit(conn, actor, "denied", selector, {"reason": "active_sessions"}, None)
            conn.commit()
            raise HTTPException(400, "active sessions require force=true")
        if preview["requires_confirm"] and int(body.get("confirm_count") or -1) != preview["total_rows"]:
            _audit(conn, actor, "denied", selector, {"reason": "confirm_count", "total_rows": preview["total_rows"]}, None)
            conn.commit()
            raise HTTPException(400, f"confirm_count must match total_rows ({preview['total_rows']})")
        result = _purge(conn, resolved, actor, selector, bool(body.get("revoke")))
        conn.commit()
    _mark_state_dirty()
    return {"ok": True, "deleted": result["counts"]["events"],
            "cleared_profile": result["counts"]["profiles"], "by": by,
            "counts": result["counts"], "batch_id": result["batch_id"]}
