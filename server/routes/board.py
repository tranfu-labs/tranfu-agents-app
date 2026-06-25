"""board 域(看板与计算):/api/state /api/skills /api/skill /api/operator /api/agent
(对应 openspec/specs/board/spec.md)。

_state_cache 与 _state_cache_lock 是模块状态,留在本模块定义;server/app.py 通过
`from server.routes.board import _state_cache, _state_cache_lock` re-export 以兼容
tests/conftest.py 的 monkeypatch 路径。
"""
import json
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from server.catalog import _catalog_context, _catalog_list, _installed_skill_names, _skill_source
from server.config import (
    ACTIVE_ST, CATALOG_COMPANY_TYPES, CLOUD_RUNTIMES, LIVE_ST,
    PROFILE_KEYS, SKILL_MODES, STALE_SECONDS, WINDOW_DAYS,
)
from server.db import _age, _day_cutoff, _parse, db, now_iso
from server.profile import _skill_names, _skill_use_name, load_profiles, load_shim_versions, reuse_map
from server.shim import _SHIM_MANIFEST

router = APIRouter()

# /api/state TTL 缓存(由 add-server-app-test-baseline 引入的 STATE_TTL_SECONDS 守护)。
_state_cache_lock = threading.Lock()
_state_cache = {"at": 0.0, "data": None}


def _now_utc():
    """通过 server.app 命名空间间接读 datetime,保留
    monkeypatch(app_mod, 'datetime', FixedDatetime) 的测试语义。"""
    from server import app
    return app.datetime.now(timezone.utc)




def _iter_sessions(conn):
    """Yield (key, session_id, [rows]) grouped by identity+session over the window."""
    win_start = (_now_utc().date() - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    # use server-authoritative recv time (fall back to ts/last_seen for legacy rows)
    rows = conn.execute("""SELECT operator, COALESCE(agent,runtime) k, runtime, session_id, status,
        COALESCE(recv, ts) rt_time, COALESCE(last_seen, recv, ts) ls FROM events WHERE day >= ?
        ORDER BY operator, k, session_id, id""", (win_start,)).fetchall()
    cur, buf = None, []
    for r in rows:
        sk = (r["operator"], r["k"], r["session_id"])
        if sk != cur:
            if buf:
                yield (buf[0]["operator"] + "\x00" + (buf[0]["k"] or ""), cur[2], buf)
            cur, buf = sk, []
        buf.append(r)
    if buf:
        yield (buf[0]["operator"] + "\x00" + (buf[0]["k"] or ""), cur[2], buf)


def metrics(conn):
    """Per identity: day-bucketed active time (today/week/series7/series90) AND
    quality (runs/done/error/avg_sec/auto_rate). One pass over the window."""
    now = _now_utc()
    today = now.date()
    buckets = {}   # key -> {dayiso: seconds}
    qual = {}      # key -> {runs,done,error,active,auto}

    def add(key, a, b):
        if b <= a:
            return
        d = buckets.setdefault(key, {})
        cur = a
        while cur < b:
            day = cur.date()
            day_end = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)
            seg = min(b, day_end)
            d[day.isoformat()] = d.get(day.isoformat(), 0) + (seg - cur).total_seconds()
            cur = seg

    for key, _sid, rows in _iter_sessions(conn):
        q = qual.setdefault(key, {"runs": 0, "done": 0, "error": 0, "blocked": 0, "active": 0.0, "auto": 0})
        active_start = last_ls = None
        saw_wait = False
        sess_active = 0.0
        for r in rows:
            t = _parse(r["rt_time"]); last_ls = _parse(r["ls"]); st = r["status"]
            if st in ACTIVE_ST:                       # running/started/waiting/blocked
                if st == "waiting":
                    saw_wait = True
                elif st == "blocked":
                    q["blocked"] += 1
                if active_start is None:
                    active_start = t
            elif st in ("done", "error", "idle"):
                if active_start is not None:
                    add(key, active_start, t); sess_active += (t - active_start).total_seconds(); active_start = None
                if st in ("done", "error"):
                    q["runs"] += 1
                    q[("done" if st == "done" else "error")] += 1
                    if st == "done" and not saw_wait:
                        q["auto"] += 1
        if active_start is not None:   # still running -> count up to last_seen
            add(key, active_start, last_ls); sess_active += (last_ls - active_start).total_seconds()
        q["active"] += sess_active

    week_start = (today - timedelta(days=today.weekday())).isoformat()
    days7 = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    days90 = [(today - timedelta(days=i)).isoformat() for i in range(WINDOW_DAYS - 1, -1, -1)]
    dur = {}
    for key, d in buckets.items():
        dur[key] = {
            "today": round(d.get(today.isoformat(), 0)),
            "week": round(sum(v for day, v in d.items() if day >= week_start)),
            "series": [round(d.get(day, 0)) for day in days7],
            "series90": [round(d.get(day, 0)) for day in days90],
        }
    qout = {}
    for key, q in qual.items():
        runs = q["runs"]
        qout[key] = {
            "runs": runs, "success": q["done"], "error": q["error"], "blocked": q["blocked"],
            "avg_sec": round(q["active"] / runs) if runs else None,
            "auto_rate": round(q["auto"] / runs, 3) if runs else None,
        }
    return dur, qout


def leverage(conn):
    today = _now_utc().date()
    wk = (today - timedelta(days=7)).isoformat()
    assets = conn.execute("SELECT COUNT(*) c FROM skills_seen").fetchone()["c"]
    week = conn.execute("SELECT COUNT(*) c FROM skills_seen WHERE first_day >= ?", (wk,)).fetchone()["c"]
    return {"assets": assets, "skills_week": week}


def skill_usage(conn):
    today = _now_utc().date()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    rows = conn.execute("""
      SELECT skill, mode,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        COUNT(*) sessions_total,
        COUNT(DISTINCT CASE WHEN day >= ? THEN operator END) users_30d,
        MAX(day) last_day
      FROM skill_uses
      GROUP BY skill, mode
      ORDER BY sessions_30d DESC, sessions_total DESC, skill ASC, mode ASC
    """, (d7, d30, d30)).fetchall()
    return [{
        "name": r["skill"],
        "mode": r["mode"] or "used",
        "sessions_7d": int(r["sessions_7d"] or 0),
        "sessions_30d": int(r["sessions_30d"] or 0),
        "sessions_total": int(r["sessions_total"] or 0),
        "users_30d": int(r["users_30d"] or 0),
        "last_day": r["last_day"],
    } for r in rows]


def skills_overview(conn, days):
    if days not in (7, 30, 90):
        raise HTTPException(400, "days must be one of 7, 30, 90")
    today = _now_utc().date()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    d14 = (today - timedelta(days=13)).isoformat()
    daily_start = _day_cutoff(days)
    _items, catalog_by, catalog_meta = _catalog_context(conn)

    daily_where, daily_params = ["mode='used'", "day IS NOT NULL"], []
    if daily_start:
        daily_where.append("day >= ?")
        daily_params.append(daily_start)
    daily_rows = conn.execute(f"""
      SELECT day, skill, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE {' AND '.join(daily_where)}
      GROUP BY day, skill, runtime
      ORDER BY day ASC, skill ASC, runtime ASC
    """, daily_params).fetchall()
    daily = [{
        "day": r["day"],
        "skill": r["skill"],
        "runtime": r["runtime"] or "unknown",
        "sessions": int(r["sessions"] or 0),
        "source": _skill_source(r["skill"], catalog_by),
    } for r in daily_rows]

    operator_daily_where = ["mode='used'", "day IS NOT NULL", "trim(COALESCE(operator,'')) <> ''"]
    operator_daily_params = []
    if daily_start:
        operator_daily_where.append("day >= ?")
        operator_daily_params.append(daily_start)
    operator_daily_rows = conn.execute(f"""
      SELECT day, operator, COALESCE(runtime,'') runtime, skill, COUNT(*) sessions
      FROM skill_uses
      WHERE {' AND '.join(operator_daily_where)}
      GROUP BY day, operator, runtime, skill
      ORDER BY day ASC, operator ASC, runtime ASC, skill ASC
    """, operator_daily_params).fetchall()
    operator_daily = [{
        "day": r["day"],
        "operator": r["operator"],
        "runtime": r["runtime"] or "unknown",
        "source": _skill_source(r["skill"], catalog_by),
        "sessions": int(r["sessions"] or 0),
    } for r in operator_daily_rows]

    base_rows = conn.execute("""
      SELECT skill,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        COUNT(*) sessions_total,
        COUNT(DISTINCT CASE WHEN day >= ? THEN operator END) users_30d,
        MAX(day) last_day
      FROM skill_uses
      WHERE mode='used'
      GROUP BY skill
    """, (d7, d30, d30)).fetchall()
    runtime_counts = {}
    for r in conn.execute("""
      SELECT skill, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used'
      GROUP BY skill, runtime
    """):
        runtime_counts.setdefault(r["skill"], {})[r["runtime"] or "unknown"] = int(r["sessions"] or 0)
    trend_days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    trend = {}
    for r in conn.execute("""
      SELECT skill, day, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND day >= ?
      GROUP BY skill, day
    """, (d14,)):
        trend.setdefault(r["skill"], {})[r["day"]] = int(r["sessions"] or 0)
    table = []
    for r in base_rows:
        skill = r["skill"]
        table.append({
            "name": skill,
            "source": _skill_source(skill, catalog_by),
            "sessions_7d": int(r["sessions_7d"] or 0),
            "sessions_30d": int(r["sessions_30d"] or 0),
            "sessions_total": int(r["sessions_total"] or 0),
            "users_30d": int(r["users_30d"] or 0),
            "runtime_counts": runtime_counts.get(skill, {}),
            "trend_14d": [trend.get(skill, {}).get(day, 0) for day in trend_days],
            "trend_days": trend_days,
            "last_day": r["last_day"],
        })
    table.sort(key=lambda x: (-x["sessions_30d"], -x["sessions_total"], x["name"]))

    operator_rows = conn.execute("""
      SELECT operator,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        COUNT(*) sessions_total,
        COUNT(DISTINCT skill) skill_count,
        COUNT(DISTINCT session_id) session_count,
        MAX(day) last_day
      FROM skill_uses
      WHERE mode='used' AND trim(COALESCE(operator,'')) <> ''
      GROUP BY operator
    """, (d7, d30)).fetchall()
    operator_runtime_counts = {}
    for r in conn.execute("""
      SELECT operator, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND trim(COALESCE(operator,'')) <> ''
      GROUP BY operator, runtime
    """):
        operator_runtime_counts.setdefault(r["operator"], {})[r["runtime"] or "unknown"] = int(r["sessions"] or 0)
    operator_source_counts = {}
    for r in conn.execute("""
      SELECT operator, skill, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND trim(COALESCE(operator,'')) <> ''
      GROUP BY operator, skill
    """):
        source = _skill_source(r["skill"], catalog_by)
        counts = operator_source_counts.setdefault(r["operator"], {})
        counts[source] = counts.get(source, 0) + int(r["sessions"] or 0)
    operator_trend = {}
    for r in conn.execute("""
      SELECT operator, day, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND day >= ? AND trim(COALESCE(operator,'')) <> ''
      GROUP BY operator, day
    """, (d14,)):
        operator_trend.setdefault(r["operator"], {})[r["day"]] = int(r["sessions"] or 0)
    operator_table = []
    for r in operator_rows:
        operator = r["operator"]
        operator_table.append({
            "operator": operator,
            "sessions_7d": int(r["sessions_7d"] or 0),
            "sessions_30d": int(r["sessions_30d"] or 0),
            "sessions_total": int(r["sessions_total"] or 0),
            "skill_count": int(r["skill_count"] or 0),
            "session_count": int(r["session_count"] or 0),
            "runtime_counts": operator_runtime_counts.get(operator, {}),
            "source_counts": operator_source_counts.get(operator, {}),
            "trend_14d": [operator_trend.get(operator, {}).get(day, 0) for day in trend_days],
            "trend_days": trend_days,
            "last_day": r["last_day"],
        })
    operator_table.sort(key=lambda x: (-x["sessions_30d"], -x["sessions_total"], x["operator"]))

    company_names = {n for n, src in catalog_by.items() if src in CATALOG_COMPANY_TYPES}
    installed_names = _installed_skill_names(conn) & company_names
    used_30d_names = {r["skill"] for r in conn.execute("""
      SELECT DISTINCT skill FROM skill_uses
      WHERE mode='used' AND day >= ?
    """, (d30,)) if r["skill"] in company_names}
    funnel = {
        "available": bool(company_names),
        "catalog": _catalog_list(company_names, catalog_by),
        "installed": _catalog_list(installed_names, catalog_by),
        "used_30d": _catalog_list(used_30d_names, catalog_by),
        "idle": _catalog_list(installed_names - used_30d_names, catalog_by),
    }
    return {
        "days": days,
        "today": today.isoformat(),
        "daily": daily,
        "table": table,
        "operator_daily": operator_daily,
        "operator_table": operator_table,
        "funnel": funnel,
        "catalog": catalog_meta,
    }


def operator_detail_payload(conn, name):
    operator = (name or "").strip()
    if not operator:
        raise HTTPException(404, "operator not found")
    row = conn.execute("SELECT display FROM identities WHERE norm=?", (operator.casefold(),)).fetchone()
    if row:
        operator = row["display"]
    exists = conn.execute("""
      SELECT COUNT(*) c FROM skill_uses
      WHERE operator=? AND mode='used' AND trim(COALESCE(operator,'')) <> ''
    """, (operator,)).fetchone()["c"]
    if not exists:
        raise HTTPException(404, "operator not found")
    today = _now_utc().date()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    _items, catalog_by, catalog_meta = _catalog_context(conn)
    m = conn.execute("""
      SELECT
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        COUNT(*) sessions_total,
        COUNT(DISTINCT skill) skill_count,
        COUNT(DISTINCT session_id) session_count,
        MIN(day) first_day,
        MAX(day) last_day
      FROM skill_uses
      WHERE operator=? AND mode='used'
    """, (d7, d30, operator)).fetchone()
    daily = [dict(r) for r in conn.execute("""
      SELECT day, skill, COUNT(*) sessions
      FROM skill_uses
      WHERE operator=? AND mode='used' AND day IS NOT NULL
      GROUP BY day, skill
      ORDER BY day ASC, skill ASC
    """, (operator,))]
    skill_runtime_counts = {}
    for r in conn.execute("""
      SELECT skill, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE operator=? AND mode='used'
      GROUP BY skill, runtime
    """, (operator,)):
        skill_runtime_counts.setdefault(r["skill"], {})[r["runtime"] or "unknown"] = int(r["sessions"] or 0)
    skill_rows = conn.execute("""
      SELECT skill,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        COUNT(*) sessions_total,
        MAX(day) last_day
      FROM skill_uses
      WHERE operator=? AND mode='used'
      GROUP BY skill
    """, (d7, d30, operator)).fetchall()
    skill_table = []
    for r in skill_rows:
        skill = r["skill"]
        skill_table.append({
            "name": skill,
            "source": _skill_source(skill, catalog_by),
            "sessions_7d": int(r["sessions_7d"] or 0),
            "sessions_30d": int(r["sessions_30d"] or 0),
            "sessions_total": int(r["sessions_total"] or 0),
            "runtime_counts": skill_runtime_counts.get(skill, {}),
            "last_day": r["last_day"],
        })
    skill_table.sort(key=lambda x: (-x["sessions_30d"], -x["sessions_total"], x["name"]))
    runtime = [{
        "runtime": r["runtime"] or "unknown",
        "used": int(r["sessions"] or 0),
    } for r in conn.execute("""
      SELECT COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE operator=? AND mode='used'
      GROUP BY runtime
      ORDER BY sessions DESC, runtime ASC
    """, (operator,))]
    records = [dict(r) for r in conn.execute("""
      SELECT day, skill, runtime, session_id, first_seen
      FROM skill_uses
      WHERE operator=? AND mode='used'
      ORDER BY COALESCE(first_seen, day) DESC
      LIMIT 50
    """, (operator,))]
    return {
        "operator": operator,
        "today": today.isoformat(),
        "metrics": {
            "sessions_7d": int(m["sessions_7d"] or 0),
            "sessions_30d": int(m["sessions_30d"] or 0),
            "sessions_total": int(m["sessions_total"] or 0),
            "skill_count": int(m["skill_count"] or 0),
            "session_count": int(m["session_count"] or 0),
            "first_day": m["first_day"],
            "last_day": m["last_day"],
        },
        "daily": daily,
        "skills": skill_table,
        "runtime": runtime,
        "records": records,
        "catalog": catalog_meta,
    }


def skill_detail_payload(conn, name):
    name = _skill_use_name(name)
    if not name:
        raise HTTPException(404, "skill not found")
    exists = conn.execute("SELECT COUNT(*) c FROM skill_uses WHERE skill=?", (name,)).fetchone()["c"]
    if not exists:
        raise HTTPException(404, "skill not found")
    today = _now_utc().date()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    _items, catalog_by, catalog_meta = _catalog_context(conn)
    m = conn.execute("""
      SELECT
        SUM(CASE WHEN mode='used' AND day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN mode='used' AND day >= ? THEN 1 ELSE 0 END) sessions_30d,
        SUM(CASE WHEN mode='used' THEN 1 ELSE 0 END) sessions_total,
        COUNT(DISTINCT CASE WHEN mode='used' AND day >= ? THEN operator END) users_30d,
        MIN(CASE WHEN mode='used' THEN day END) first_day,
        MAX(CASE WHEN mode='used' THEN day END) last_day,
        SUM(CASE WHEN mode='equipped' AND day >= ? THEN 1 ELSE 0 END) equipped_7d,
        SUM(CASE WHEN mode='equipped' AND day >= ? THEN 1 ELSE 0 END) equipped_30d,
        SUM(CASE WHEN mode='equipped' THEN 1 ELSE 0 END) equipped_total,
        COUNT(DISTINCT CASE WHEN mode='equipped' AND day >= ? THEN operator END) equipped_users_30d
      FROM skill_uses
      WHERE skill=?
    """, (d7, d30, d30, d7, d30, d30, name)).fetchone()
    daily_map = {}
    for r in conn.execute("""
      SELECT day, mode, COUNT(*) sessions
      FROM skill_uses
      WHERE skill=? AND day IS NOT NULL
      GROUP BY day, mode
      ORDER BY day ASC
    """, (name,)):
        day = daily_map.setdefault(r["day"], {"day": r["day"], "used": 0, "equipped": 0})
        day[r["mode"] if r["mode"] in SKILL_MODES else "used"] = int(r["sessions"] or 0)
    runtime_map = {}
    for r in conn.execute("""
      SELECT COALESCE(runtime,'') runtime, mode, COUNT(*) sessions
      FROM skill_uses
      WHERE skill=?
      GROUP BY runtime, mode
    """, (name,)):
        item = runtime_map.setdefault(r["runtime"] or "unknown", {"runtime": r["runtime"] or "unknown", "used": 0, "equipped": 0})
        item[r["mode"] if r["mode"] in SKILL_MODES else "used"] = int(r["sessions"] or 0)
    operator_map = {}
    for r in conn.execute("""
      SELECT COALESCE(operator,'') operator, mode, COUNT(*) sessions
      FROM skill_uses
      WHERE skill=?
      GROUP BY operator, mode
    """, (name,)):
        item = operator_map.setdefault(r["operator"] or "unknown", {"operator": r["operator"] or "unknown", "used": 0, "equipped": 0})
        item[r["mode"] if r["mode"] in SKILL_MODES else "used"] = int(r["sessions"] or 0)
    records = [dict(r) for r in conn.execute("""
      SELECT day, operator, runtime, mode, session_id, first_seen
      FROM skill_uses
      WHERE skill=?
      ORDER BY COALESCE(first_seen, day) DESC
      LIMIT 50
    """, (name,))]
    return {
        "name": name,
        "today": today.isoformat(),
        "source": _skill_source(name, catalog_by),
        "metrics": {
            "sessions_7d": int(m["sessions_7d"] or 0),
            "sessions_30d": int(m["sessions_30d"] or 0),
            "sessions_total": int(m["sessions_total"] or 0),
            "users_30d": int(m["users_30d"] or 0),
            "first_day": m["first_day"],
            "last_day": m["last_day"],
            "equipped_7d": int(m["equipped_7d"] or 0),
            "equipped_30d": int(m["equipped_30d"] or 0),
            "equipped_total": int(m["equipped_total"] or 0),
            "equipped_users_30d": int(m["equipped_users_30d"] or 0),
        },
        "daily": list(daily_map.values()),
        "runtime": sorted(runtime_map.values(), key=lambda x: (-(x["used"] + x["equipped"]), x["runtime"])),
        "operators": sorted(operator_map.values(), key=lambda x: (-(x["used"] + x["equipped"]), x["operator"])),
        "records": records,
        "catalog": catalog_meta,
    }


# ---------------------------------------------------------------- read: snapshot
def _snapshot(conn):
    sessions = conn.execute("""
      SELECT e.* FROM events e
      JOIN (SELECT operator,runtime,COALESCE(agent,runtime) ag,MAX(id) mid FROM events
            WHERE source='heartbeat' GROUP BY operator,runtime,ag) last
      ON e.id = last.mid ORDER BY e.operator ASC, e.id DESC LIMIT 200""").fetchall()
    feed = conn.execute("""SELECT * FROM events WHERE source='heartbeat'
      ORDER BY id DESC LIMIT 40""").fetchall()
    dur, qual = metrics(conn)
    profiles = load_profiles(conn)
    shim_versions = load_shim_versions(conn)
    reuse = reuse_map(profiles)

    def card(r):
        d = dict(r)
        d["meta"] = json.loads(d["meta"]) if d.get("meta") else None
        d["fidelity"] = "coarse" if r["runtime"] in CLOUD_RUNTIMES else "full"
        ak = (r["agent"] if "agent" in r.keys() else None) or r["runtime"] or ""
        key = r["operator"] + "\x00" + ak
        dd = dur.get(key, {"today": 0, "week": 0, "series": [0] * 7, "series90": [0] * WINDOW_DAYS})
        d["today_active"], d["week_active"], d["active_series"] = dd["today"], dd["week"], dd["series"]
        d["active_days"] = dd["series90"]
        # merged profile (optional, reported by shim)
        p = profiles.get(key, {})
        for k in PROFILE_KEYS:
            if k in p:
                d[k] = p[k]
        # sticky shim version (independent of profile full-replace; may be None
        # when this agent has never reported it -> frontend renders 'unknown')
        d["shim_version"] = shim_versions.get(key)
        # quality: computed + reuse, allow profile to add hints it can't compute
        q = dict(qual.get(key, {}))
        if key in reuse:
            q["reuse"] = reuse[key]
        if q:
            d["quality"] = q
        d["verified"] = bool(d.get("verified"))
        st = r["status"]
        if st in ACTIVE_ST and _age(r["last_seen"] or r["recv"] or r["ts"]) > STALE_SECONDS:
            st = "idle"
        d["status"] = st
        for big in ("input", "output"):
            if d.get(big) and len(d[big]) > 4000:
                d[big] = d[big][:4000] + "…[truncated]"
        return d

    cards = [card(r) for r in sessions]
    # collapse to ONE card per identity (operator + agent||runtime): keep the most
    # recently active session, so the same agent over many runs/sessions = one card.
    _best = {}
    for c in cards:
        k = (c["operator"], c.get("agent") or c.get("runtime") or "")
        tcur = c.get("last_seen") or c.get("ts") or ""
        prev = _best.get(k)
        if prev is None or tcur > (prev.get("last_seen") or prev.get("ts") or ""):
            _best[k] = c
    cards = list(_best.values())
    live = [c for c in cards if c["status"] in LIVE_ST]
    ops = {c["operator"] for c in cards}
    agents = {(c["operator"], (c.get("agent") or c["runtime"])) for c in cards}
    return {
        "now": now_iso(),
        "sessions": cards,
        "feed": [{"operator": r["operator"], "agent": r["agent"], "runtime": r["runtime"],
                  "status": r["status"], "current_step": r["current_step"],
                  "task": r["task"], "ts": r["ts"]} for r in feed],
        "leverage": leverage(conn),
        "skills": skill_usage(conn),
        "shim": {"version": _SHIM_MANIFEST["version"], "files": len(_SHIM_MANIFEST["files"])},
        "totals": {
            "live": len(live), "operators": len(ops), "agents": len(agents),
            "today_active": sum(v["today"] for v in dur.values()),
        },
    }


def _state_compute_or_cache():
    from server import app  # 延迟读 STATE_TTL_SECONDS(可变开关)
    now = time.monotonic()
    with _state_cache_lock:
        cached = _state_cache.get("data")
        cached_at = float(_state_cache.get("at") or 0.0)
        if cached is not None and now - cached_at < app.STATE_TTL_SECONDS:
            return cached

    with closing(db()) as conn:
        # 通过 app 命名空间间接调用,保留 monkeypatch(app_mod, "_snapshot", ...) 语义
        data = app._snapshot(conn)

    with _state_cache_lock:
        _state_cache["at"] = time.monotonic()
        _state_cache["data"] = data
    return data


@router.get("/api/state")
async def state():
    data = await run_in_threadpool(_state_compute_or_cache)
    return JSONResponse(data)


@router.get("/api/skills")
def skills_stats(days: int = 30):
    with closing(db()) as conn:
        return JSONResponse(skills_overview(conn, days))


@router.get("/api/skill/{name}")
def skill_detail(name: str):
    with closing(db()) as conn:
        return JSONResponse(skill_detail_payload(conn, name))


@router.get("/api/operator/{name}")
def operator_detail(name: str):
    with closing(db()) as conn:
        return JSONResponse(operator_detail_payload(conn, name))


@router.get("/api/agent/{key}")
def agent_detail(key: str):
    """Single agent detail. key = 'operator::agentOrRuntime' (matches dashboard keyOf)."""
    with closing(db()) as conn:
        snap = _snapshot(conn)
    want = key.replace("::", "\x00", 1)
    for c in snap["sessions"]:
        if (c["operator"] + "\x00" + ((c.get("agent") or c["runtime"]))) == want:
            return JSONResponse(c)
    raise HTTPException(404, "agent not found")


