"""board 域(看板与计算):/api/state /api/agents /api/skills /api/skill /api/operator /api/agent
(对应 openspec/specs/board/spec.md)。

_state_cache 与 _state_cache_lock 是模块状态,留在本模块定义;server/app.py 通过
`from server.routes.board import _state_cache, _state_cache_lock` re-export 以兼容
tests/conftest.py 的 monkeypatch 路径。
"""
import asyncio
import hashlib
import json
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from server.catalog import (
    _annotate_profile_skill_names, _catalog_context, _catalog_list,
    _installed_skill_names, _skill_display_fields, _skill_name_map, _skill_source,
)
from server.config import (
    ACTIVE_ST, CATALOG_COMPANY_TYPES, CATALOG_SOURCE_UNKNOWN, CLOUD_RUNTIMES, LIVE_ST,
    PROFILE_KEYS, SKILL_MODES, STALE_SECONDS, WINDOW_DAYS,
)
from server.db import STATS_TZ, _age, _day_cutoff, _parse, db, now_iso, stats_now, stats_today
from server.profile import _skill_names, _skill_use_name, load_profiles, load_shim_versions, reuse_map
from server.shim import _SHIM_MANIFEST

router = APIRouter()

# /api/state TTL 缓存(由 add-server-app-test-baseline 引入的 STATE_TTL_SECONDS 守护)。
_state_cache_lock = threading.Lock()
_state_cache_cond = threading.Condition(_state_cache_lock)
_state_cache = {"at": 0.0, "data": None, "computing": False}
_state_dirty_lock = threading.Lock()
_state_dirty_revision = 0


def _state_revision():
    with _state_dirty_lock:
        return _state_dirty_revision


def mark_state_dirty():
    """Invalidate the state cache and advance the SSE revision."""
    global _state_dirty_revision
    with _state_dirty_lock:
        _state_dirty_revision += 1
        rev = _state_dirty_revision
    with _state_cache_cond:
        _state_cache["at"] = 0.0
        _state_cache_cond.notify_all()
    return rev


def _query_fingerprint(request):
    return urlencode(sorted(request.query_params.multi_items()), doseq=True)


def _etag_matches(header, etag):
    return any(part.strip() == etag for part in (header or "").split(","))


def _conditional_json(request, payload):
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    identity = f"{request.url.path}?{_query_fingerprint(request)}".encode("utf-8")
    etag = '"' + hashlib.sha256(identity + b"\0" + body).hexdigest() + '"'
    headers = {"Cache-Control": "no-cache", "ETag": etag}
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)

def _iter_sessions(conn):
    """Yield (key, session_id, [rows]) grouped by identity+session over the window."""
    win_start = _day_cutoff(WINDOW_DAYS)
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
    now = stats_now()
    today = now.date()
    buckets = {}   # key -> {dayiso: seconds}
    qual = {}      # key -> {runs,done,error,active,auto}

    def add(key, a, b):
        if b <= a:
            return
        d = buckets.setdefault(key, {})
        cur = a.astimezone(STATS_TZ)
        end = b.astimezone(STATS_TZ)
        while cur < end:
            day = cur.date()
            day_end = datetime(day.year, day.month, day.day, tzinfo=STATS_TZ) + timedelta(days=1)
            seg = min(end, day_end)
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
    today = stats_today()
    d7 = (today - timedelta(days=6)).isoformat()
    assets = conn.execute("SELECT COUNT(DISTINCT skill) c FROM skill_uses WHERE mode='used'").fetchone()["c"]
    week = len(_new_used_skill_names(conn, d7, today.isoformat()))
    return {"assets": assets, "skills_week": week}


def _named_skill(name, skill_names, values=None, **extra):
    return {"name": name, **_skill_display_fields(name, skill_names), **(values or {}), **extra}


def _skill_record(skill, skill_names, values=None, **extra):
    return {"skill": skill, **_skill_display_fields(skill, skill_names), **(values or {}), **extra}


def skill_usage(conn, skill_names=None):
    today = stats_today()
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
    return [_named_skill(r["skill"], skill_names, {
        "mode": r["mode"] or "used",
        "sessions_7d": int(r["sessions_7d"] or 0),
        "sessions_30d": int(r["sessions_30d"] or 0),
        "sessions_total": int(r["sessions_total"] or 0),
        "users_30d": int(r["users_30d"] or 0),
        "last_day": r["last_day"],
    }) for r in rows]


def _agent_rate(success, runs):
    return round(success / runs, 3) if runs else None


def _agent_group_stats(cards, field):
    groups = {}
    for card in cards:
        name = str(card.get(field) or card.get("runtime") or "unknown")
        group = groups.setdefault(name, {
            field: name,
            "agents": 0,
            "live": 0,
            "today_active": 0,
            "week_active": 0,
            "runs": 0,
            "success": 0,
            "errors": 0,
            "blocked": 0,
        })
        group["agents"] += 1
        if card.get("status") in LIVE_ST:
            group["live"] += 1
        group["today_active"] += int(card.get("today_active") or 0)
        group["week_active"] += int(card.get("week_active") or 0)
        quality = card.get("quality") or {}
        group["runs"] += int(quality.get("runs") or 0)
        group["success"] += int(quality.get("success") or 0)
        group["errors"] += int(quality.get("error") or 0)
        group["blocked"] += int(quality.get("blocked") or 0)

    for group in groups.values():
        group["success_rate"] = _agent_rate(group["success"], group["runs"])
    return sorted(groups.values(), key=lambda item: (
        -item["agents"], -item["live"], -item["today_active"], item[field],
    ))


def _agent_overview(cards, latest_shim):
    today = stats_today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(WINDOW_DAYS - 1, -1, -1)]
    active_seconds = [0] * len(days)
    active_agents = [0] * len(days)
    runs = success = errors = blocked = today_active = week_active = 0
    outdated_shim = unknown_shim = 0

    for card in cards:
        quality = card.get("quality") or {}
        runs += int(quality.get("runs") or 0)
        success += int(quality.get("success") or 0)
        errors += int(quality.get("error") or 0)
        blocked += int(quality.get("blocked") or 0)
        today_active += int(card.get("today_active") or 0)
        week_active += int(card.get("week_active") or 0)
        version = card.get("shim_version")
        if not version:
            unknown_shim += 1
        elif latest_shim and version != latest_shim:
            outdated_shim += 1

        series = card.get("active_days") or []
        offset = len(days) - len(series)
        for index, value in enumerate(series[-len(days):]):
            target = index + max(0, offset)
            if target >= len(days):
                continue
            seconds = int(value or 0)
            active_seconds[target] += seconds
            if seconds > 0:
                active_agents[target] += 1

    return {
        "today": today.isoformat(),
        "days": days,
        "summary": {
            "agents": len(cards),
            "live": sum(1 for card in cards if card.get("status") in LIVE_ST),
            "operators": len({card.get("operator") for card in cards if card.get("operator")}),
            "today_active": today_active,
            "week_active": week_active,
            "runs": runs,
            "success": success,
            "errors": errors,
            "blocked": blocked,
            "success_rate": _agent_rate(success, runs),
            "outdated_shim": outdated_shim,
            "unknown_shim": unknown_shim,
        },
        "daily": [
            {"day": day, "active_seconds": active_seconds[index], "active_agents": active_agents[index]}
            for index, day in enumerate(days)
        ],
        "runtime": _agent_group_stats(cards, "runtime"),
        "operator": _agent_group_stats(cards, "operator"),
    }


_AGENT_STATUS_FILTERS = {"all", "live", "attention", "idle", "done"}
_AGENT_SIGNAL_FILTERS = {"", "error", "shim", "quiet", "quality"}
_AGENT_SORTS = {"recent", "window_time", "window_days", "success", "errors", "name"}


def _agent_identity(card):
    return f"{card.get('operator') or ''}::{card.get('agent') or card.get('runtime') or ''}"


def _agent_display_labels(cards):
    groups = {}
    for card in cards:
        name = str(card.get("agent") or "").strip() or "Agent"
        groups.setdefault(name, []).append(card)
    labels = {}
    for name, group in groups.items():
        ordered = sorted(group, key=_agent_identity)
        for index, card in enumerate(ordered, start=1):
            labels[_agent_identity(card)] = f"{name} · {index}" if len(ordered) > 1 else name
    return labels


def _agent_issue_signals(card, latest_shim):
    signals = []
    quality = card.get("quality") or {}
    if (card.get("status") in {"error", "blocked"}
            or int(quality.get("error") or 0) > 0
            or int(quality.get("blocked") or 0) > 0):
        signals.append("error")
    version = card.get("shim_version")
    if not version or (latest_shim and version != latest_shim):
        signals.append("shim")
    recent = (card.get("active_days") or [])[-14:]
    if card.get("status") not in LIVE_ST and len(recent) >= 14 and not any(int(value or 0) for value in recent):
        signals.append("quiet")
    runs = int(quality.get("runs") or 0)
    success = int(quality.get("success") or 0)
    if runs >= 3 and success / runs < 0.8:
        signals.append("quality")
    return signals


def _agent_days(start, end):
    return [(start + timedelta(days=index)).isoformat() for index in range((end - start).days + 1)]


def _agents_window(w=None, wstart=None, wend=None):
    today = stats_today()
    key = str(w or "today").strip()
    if key == "today":
        start = end = today
    elif key == "this_week":
        start, end = today - timedelta(days=today.weekday()), today
    elif key == "last_week":
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
    elif key in {"7d", "14d", "30d", "90d"}:
        start, end = today - timedelta(days=int(key[:-1]) - 1), today
    elif key == "custom":
        if wstart is None or wend is None:
            raise HTTPException(400, "custom window requires wstart and wend")
        try:
            start = datetime.fromtimestamp(int(wstart), tz=STATS_TZ).date()
            end = datetime.fromtimestamp(int(wend), tz=STATS_TZ).date()
        except (ValueError, TypeError, OverflowError, OSError) as exc:
            raise HTTPException(400, "wstart and wend must be Unix seconds") from exc
        if end < start:
            raise HTTPException(400, "custom window end must not be before start")
        if (end - start).days + 1 > WINDOW_DAYS:
            raise HTTPException(400, f"custom window must not exceed {WINDOW_DAYS} days")
        earliest = today - timedelta(days=WINDOW_DAYS - 1)
        if start < earliest:
            raise HTTPException(400, f"custom window must start on or after {earliest.isoformat()}")
    else:
        raise HTTPException(400, "w must be one of today,this_week,last_week,7d,14d,30d,90d,custom")

    days = _agent_days(start, end)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=len(days) - 1)
    return {
        "key": key,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "previous_start": previous_start.isoformat(),
        "previous_end": previous_end.isoformat(),
        "previous_days": _agent_days(previous_start, previous_end),
    }


def _agent_series(card, overview_days):
    series = card.get("active_days") or card.get("active_series") or []
    offset = len(overview_days) - len(series)
    return {
        overview_days[index + offset]: int(value or 0)
        for index, value in enumerate(series)
        if 0 <= index + offset < len(overview_days)
    }


def _agent_window_values(card, overview_days, selected_days):
    series = _agent_series(card, overview_days)
    values = [int(series.get(day) or 0) for day in selected_days]
    return sum(values), sum(1 for value in values if value > 0)


def _agent_window_stats(cards, overview_days, selected_days):
    available = bool(overview_days) and all(day >= overview_days[0] for day in selected_days)
    if not available:
        return {"active_agents": 0, "active_seconds": 0, "available": False}
    seconds = 0
    active_agents = 0
    for card in cards:
        agent_seconds, _active_days = _agent_window_values(card, overview_days, selected_days)
        seconds += agent_seconds
        if agent_seconds > 0:
            active_agents += 1
    return {"active_agents": active_agents, "active_seconds": seconds, "available": True}


def _filter_agent_cards(cards, q, status, signal, latest_shim):
    if status not in _AGENT_STATUS_FILTERS:
        raise HTTPException(400, "status must be one of all,live,attention,idle,done")
    if signal not in _AGENT_SIGNAL_FILTERS:
        raise HTTPException(400, "signal must be one of error,shim,quiet,quality")
    query = str(q or "").strip().casefold()
    filtered = []
    for card in cards:
        signals = _agent_issue_signals(card, latest_shim)
        searchable = " ".join(str(value) for value in [
            card.get("agent"), card.get("task"), card.get("current_step"), *(card.get("models") or []),
        ] if value).casefold()
        if query and query not in searchable:
            continue
        if status == "live" and card.get("status") not in LIVE_ST:
            continue
        if status == "attention" and not signals:
            continue
        if status == "idle" and card.get("status") != "idle":
            continue
        if status == "done" and card.get("status") != "done":
            continue
        if signal and signal not in signals:
            continue
        filtered.append(card)
    return filtered


def _sort_agent_rows(rows, sort):
    if sort in {"today", "week"}:
        sort = "window_time" if sort == "today" else "window_days"
    if sort not in _AGENT_SORTS:
        raise HTTPException(400, "sort must be one of recent,window_time,window_days,success,errors,name")
    ordered = sorted(rows, key=lambda row: row["key"])
    ordered.sort(key=lambda row: str(row.get("last_seen") or row.get("ts") or ""), reverse=True)
    if sort == "window_time":
        ordered.sort(key=lambda row: int(row["active_seconds"]), reverse=True)
    elif sort == "window_days":
        ordered.sort(key=lambda row: int(row["active_seconds"]), reverse=True)
        ordered.sort(key=lambda row: int(row["window_active_days"]), reverse=True)
    elif sort == "success":
        ordered.sort(key=lambda row: (
            int((row.get("quality") or {}).get("success") or 0) / int((row.get("quality") or {}).get("runs") or 1)
            if int((row.get("quality") or {}).get("runs") or 0) else -1
        ), reverse=True)
    elif sort == "errors":
        ordered.sort(key=lambda row: int((row.get("quality") or {}).get("error") or 0)
                     + int((row.get("quality") or {}).get("blocked") or 0), reverse=True)
    elif sort == "name":
        ordered.sort(key=lambda row: f"{row.get('agent') or row.get('runtime') or ''} {row.get('operator') or ''}")
    return ordered


def agents_overview_payload(cards, latest_shim, w=None, wstart=None, wend=None,
                            q="", status="all", signal="", sort="window_time"):
    window = _agents_window(w, wstart, wend)
    today = stats_today()
    overview_days = [(today - timedelta(days=index)).isoformat()
                     for index in range(WINDOW_DAYS - 1, -1, -1)]
    filtered = _filter_agent_cards(cards, q, status, signal, latest_shim)
    rows = []
    for card in filtered:
        active_seconds, active_days = _agent_window_values(card, overview_days, window["days"])
        rows.append({
            **card,
            "key": _agent_identity(card),
            "operator": card.get("operator") or "",
            "agent": card.get("agent"),
            "runtime": card.get("runtime") or "",
            "active_seconds": active_seconds,
            "window_active_days": active_days,
            "signals": _agent_issue_signals(card, latest_shim),
        })
    rows = _sort_agent_rows(rows, sort)

    ranking = []
    for index, row in enumerate(sorted(
            (item for item in rows if int(item["active_seconds"]) > 0),
            key=lambda item: (-int(item["active_seconds"]), item["key"])), start=1):
        ranking.append({
            "rank": index,
            "key": row["key"],
            "operator": row["operator"],
            "agent": row.get("agent"),
            "runtime": row["runtime"],
            "status": row.get("status"),
            "last_seen": row.get("last_seen") or row.get("ts"),
            "active_seconds": int(row["active_seconds"]),
            "active_days": int(row["window_active_days"]),
        })

    daily = []
    for day in window["days"]:
        segments = []
        for row in rows:
            seconds = int(_agent_series(row, overview_days).get(day) or 0)
            if seconds <= 0:
                continue
            segments.append({
                "key": row["key"],
                "operator": row["operator"],
                "agent": row.get("agent"),
                "runtime": row["runtime"],
                "active_agents": 1,
                "active_seconds": seconds,
            })
        segments.sort(key=lambda item: (-item["active_seconds"], item["key"]))
        daily.append({
            "day": day,
            "active_agents": len(segments),
            "active_seconds": sum(item["active_seconds"] for item in segments),
            "segments": segments,
        })

    current = _agent_window_stats(filtered, overview_days, window["days"])
    previous = _agent_window_stats(filtered, overview_days, window["previous_days"])
    overview_summary = _agent_overview(filtered, latest_shim)["summary"]
    signal_counts = {
        name: sum(1 for row in rows if name in row["signals"])
        for name in ("error", "shim", "quiet", "quality")
    }
    attention = sum(1 for row in rows if row["signals"])
    summary = {
        **overview_summary,
        "total_agents": len(cards),
        "active_agents": current["active_agents"],
        "active_seconds": current["active_seconds"],
        "average_active_seconds": (
            round(current["active_seconds"] / current["active_agents"])
            if current["active_agents"] else 0
        ),
        "attention": attention,
    }
    return {
        "today": today.isoformat(),
        "window": window,
        "summary": summary,
        "comparison": {"current": current, "previous": previous},
        "daily": daily,
        "ranking": ranking,
        "agents": rows,
        "signals": signal_counts,
        "agent_labels": _agent_display_labels(cards),
        "shim": {"version": latest_shim},
    }


def _skill_scope_sql(skill_names, prefix="AND"):
    if skill_names is None:
        return "", []
    if not skill_names:
        return f" {prefix} 0", []
    names = sorted(skill_names)
    return f" {prefix} skill IN ({','.join('?' for _ in names)})", names


def _used_skill_first_days(conn):
    return {r["skill"]: r["first_day"] for r in conn.execute("""
      SELECT skill, MIN(day) first_day
      FROM skill_uses
      WHERE mode='used' AND day IS NOT NULL
      GROUP BY skill
    """)}


def _new_used_skill_names(conn, window_start, window_end):
    return {
        skill for skill, first_day in _used_skill_first_days(conn).items()
        if first_day and window_start <= first_day <= window_end
    }


def _skills_governance_untracked(conn, window_start, window_end, d30, trend_days, catalog_by,
                                 scoped_names=None, display_names=None):
    scope_sql, scope_params = _skill_scope_sql(scoped_names)
    total = conn.execute(f"""
      SELECT COUNT(*) c FROM skill_uses
      WHERE mode='used' AND day >= ? AND day <= ?{scope_sql}
    """, (window_start, window_end, *scope_params)).fetchone()["c"] or 0
    window_rows = conn.execute(f"""
      SELECT skill,
        COUNT(*) sessions,
        COUNT(DISTINCT CASE WHEN day >= ? THEN operator END) users_30d,
        MAX(day) last_day
      FROM skill_uses
      WHERE mode='used' AND day >= ? AND day <= ?{scope_sql}
      GROUP BY skill
    """, (d30, window_start, window_end, *scope_params)).fetchall()
    runtime_counts = {}
    for r in conn.execute(f"""
      SELECT skill, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND day >= ? AND day <= ?{scope_sql}
      GROUP BY skill, runtime
    """, (window_start, window_end, *scope_params)):
        runtime_counts.setdefault(r["skill"], {})[r["runtime"] or "unknown"] = int(r["sessions"] or 0)
    trend = {}
    if trend_days:
        trend_scope_sql, trend_scope_params = _skill_scope_sql(scoped_names)
        for r in conn.execute(f"""
          SELECT skill, day, COUNT(*) sessions
          FROM skill_uses
          WHERE mode='used' AND day >= ?{trend_scope_sql}
          GROUP BY skill, day
        """, (trend_days[0], *trend_scope_params)):
            trend.setdefault(r["skill"], {})[r["day"]] = int(r["sessions"] or 0)

    top = []
    used_sessions = 0
    for r in window_rows:
        skill = r["skill"]
        if _skill_source(skill, catalog_by) != CATALOG_SOURCE_UNKNOWN:
            continue
        sessions = int(r["sessions"] or 0)
        used_sessions += sessions
        top.append(_named_skill(skill, display_names, {
            "source": CATALOG_SOURCE_UNKNOWN,
            "sessions": sessions,
            "share": (sessions / total) if total else 0,
            "users_30d": int(r["users_30d"] or 0),
            "runtime_counts": runtime_counts.get(skill, {}),
            "trend_14d": [trend.get(skill, {}).get(day, 0) for day in trend_days],
            "trend_days": trend_days,
            "last_day": r["last_day"],
        }))

    def _day_num(item):
        return int((item.get("last_day") or "0000-00-00").replace("-", ""))

    top.sort(key=lambda item: (-item["sessions"], -_day_num(item), item["name"]))
    return {
        "ratio": (used_sessions / total) if total else 0,
        "used_sessions": used_sessions,
        "total_sessions": int(total),
        "skill_count": len(top),
        "top": top,
    }


def _skill_source_key(value):
    return "non_catalog" if value == CATALOG_SOURCE_UNKNOWN else value


def _skills_window(days, w=None, wstart=None, wend=None):
    today = stats_today()

    def make(key, start, end):
        span = (end - start).days + 1
        return {
            "key": key,
            "days": max(1, span),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "previous_start": (start - timedelta(days=max(1, span))).isoformat(),
            "previous_end": (start - timedelta(days=1)).isoformat(),
        }

    if w:
        key = str(w).strip()
        if key == "today":
            return make(key, today, today)
        if key == "this_week":
            start = today - timedelta(days=today.weekday())
            return make(key, start, today)
        if key == "last_week":
            end = today - timedelta(days=today.weekday() + 1)
            start = end - timedelta(days=6)
            return make(key, start, end)
        if key == "custom":
            try:
                start = datetime.fromtimestamp(int(wstart), tz=STATS_TZ)
                end = datetime.fromtimestamp(int(wend), tz=STATS_TZ)
                start_day = start.date()
                end_day = end.date()
                if end_day < start_day:
                    raise ValueError("custom end before start")
                if (end_day - start_day).days >= 90:
                    end_day = start_day + timedelta(days=89)
                return make(key, start_day, end_day)
            except Exception:
                return make("30d", today - timedelta(days=29), today)
        if key.endswith("d") and key[:-1].isdigit():
            value = int(key[:-1])
            if value in (7, 14, 30, 90):
                return make(key, today - timedelta(days=value - 1), today)
        raise HTTPException(400, "w must be one of today,this_week,last_week,7d,14d,30d,90d,custom")
    if days not in (7, 30, 90):
        raise HTTPException(400, "days must be one of 7, 30, 90")
    return make(f"{days}d", today - timedelta(days=days - 1), today)


def _period_comparison(conn, window, catalog_by, skill_names=None):
    current_start = window["start"]
    current_end = window["end"]
    previous_start = window["previous_start"]
    previous_end = window["previous_end"]

    def stats(start, end):
        scope_sql, scope_params = _skill_scope_sql(skill_names)
        params = [start, end, *scope_params]
        row = conn.execute(f"""
          SELECT COUNT(*) sessions,
            COUNT(DISTINCT CASE WHEN trim(COALESCE(operator,'')) <> '' THEN operator END) operators,
            COUNT(DISTINCT session_id) session_count
          FROM skill_uses
          WHERE mode='used' AND day >= ? AND day <= ?{scope_sql}
        """, params).fetchone()
        skill_rows = conn.execute(f"""
          SELECT skill, COUNT(*) sessions
          FROM skill_uses
          WHERE mode='used' AND day >= ? AND day <= ?{scope_sql}
          GROUP BY skill
        """, params).fetchall()
        sessions = int(row["sessions"] or 0)
        session_count = int(row["session_count"] or 0)
        top3 = sum(int(r["sessions"] or 0) for r in sorted(skill_rows, key=lambda r: int(r["sessions"] or 0), reverse=True)[:3])
        untracked = sum(int(r["sessions"] or 0) for r in skill_rows if _skill_source(r["skill"], catalog_by) == CATALOG_SOURCE_UNKNOWN)
        company_skills = {r["skill"] for r in skill_rows if _skill_source(r["skill"], catalog_by) in CATALOG_COMPANY_TYPES and int(r["sessions"] or 0) > 0}
        return {
            "sessions": sessions,
            "operators": int(row["operators"] or 0),
            "session_count": session_count,
            "avg_skills_per_session": (sessions / session_count) if session_count else 0,
            "top3_share": (top3 / sessions) if sessions else 0,
            "untracked_share": (untracked / sessions) if sessions else 0,
            "company_skill_count": len(company_skills),
        }

    cur = stats(current_start, current_end)
    prev = stats(previous_start, previous_end)
    return {
        "window": window["key"],
        "current_window_start": current_start,
        "current_window_end": current_end,
        "previous_window_start": previous_start,
        "previous_window_end": previous_end,
        "current_sessions": cur["sessions"],
        "previous_sessions": prev["sessions"],
        "current_operators": cur["operators"],
        "previous_operators": prev["operators"],
        "current_session_count": cur["session_count"],
        "previous_session_count": prev["session_count"],
        "current_avg_skills_per_session": cur["avg_skills_per_session"],
        "previous_avg_skills_per_session": prev["avg_skills_per_session"],
        "current_top3_share": cur["top3_share"],
        "previous_top3_share": prev["top3_share"],
        "current_untracked_share": cur["untracked_share"],
        "previous_untracked_share": prev["untracked_share"],
        "current_company_skill_count": cur["company_skill_count"],
        "previous_company_skill_count": prev["company_skill_count"],
    }


def _installed_skill_counts(conn):
    counts = {}
    for r in conn.execute("SELECT json FROM profiles"):
        try:
            profile = json.loads(r["json"])
        except Exception:  # pragma: no cover  — profile JSON 损坏兜底
            continue
        for name in _skill_names(profile.get("skills")):
            clean = _skill_use_name(name)
            if clean:
                counts[clean] = counts.get(clean, 0) + 1
    return counts


def _installed_skill_details(conn):
    details = {}
    for r in conn.execute("SELECT operator,ak,runtime,json,updated FROM profiles"):
        try:
            profile = json.loads(r["json"])
        except Exception:  # pragma: no cover  — profile JSON 损坏兜底
            continue
        for name in {_skill_use_name(n) for n in _skill_names(profile.get("skills"))}:
            if not name:
                continue
            details.setdefault(name, []).append({
                "operator": r["operator"],
                "agent_key": r["ak"],
                "runtime": r["runtime"],
                "profile_updated_at": r["updated"],
            })
    for installers in details.values():
        installers.sort(key=lambda item: (
            str(item.get("operator") or ""),
            str(item.get("agent_key") or ""),
            str(item.get("runtime") or ""),
        ))
    return details


def _skills_attribution(conn, window_start, window_end, catalog_by, skill_names=None):
    by_source = {}
    scope_sql, scope_params = _skill_scope_sql(skill_names)
    for r in conn.execute(f"""
      SELECT skill, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND day >= ? AND day <= ?{scope_sql}
      GROUP BY skill
    """, (window_start, window_end, *scope_params)):
        source = _skill_source_key(_skill_source(r["skill"], catalog_by))
        by_source[source] = by_source.get(source, 0) + int(r["sessions"] or 0)
    by_runtime = [{
        "runtime": r["runtime"] or "unknown",
        "sessions": int(r["sessions"] or 0),
    } for r in conn.execute(f"""
      SELECT COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND day >= ? AND day <= ?{scope_sql}
      GROUP BY runtime
      ORDER BY sessions DESC, runtime ASC
    """, (window_start, window_end, *scope_params))]
    return {
        "by_source": [{"source": key, "sessions": by_source.get(key, 0)} for key in ("own", "meta", "external", "non_catalog")],
        "by_runtime": by_runtime,
    }


def _governance_buckets(conn, window_start, catalog_by, catalog_meta, company_names,
                        installed_names, used_names, skill_names=None):
    install_counts = _installed_skill_counts(conn)
    first_seen = {r["name"]: r["first_day"] for r in conn.execute("SELECT name,first_day FROM skills_seen")}
    last_days = {r["skill"]: r["last_day"] for r in conn.execute("""
      SELECT skill, MAX(day) last_day
      FROM skill_uses
      WHERE mode='used'
      GROUP BY skill
    """)}
    idle = []
    for name in installed_names - used_names:
        idle.append(_named_skill(name, skill_names, {
            "source": catalog_by.get(name),
            "installed_at": first_seen.get(name),
            "installers": int(install_counts.get(name, 0)),
            "last_day": last_days.get(name),
        }))
    idle.sort(key=lambda item: (item.get("installed_at") or "", item["name"]), reverse=True)
    missing = []
    for name in company_names - installed_names:
        missing.append(_named_skill(name, skill_names, {
            "source": catalog_by.get(name),
            "cataloged_at": catalog_meta.get("fetched_at"),
        }))
    missing.sort(key=lambda item: (item.get("cataloged_at") or "", item["name"]))
    return {
        "idle_installed": {"count": len(idle), "top": idle[:50]},
        "cataloged_not_installed": {"count": len(missing), "top": missing[:50]},
    }


def _catalog_published_day(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(STATS_TZ).date().isoformat()


def _published_skill_summary(conn, catalog_items, catalog_by, window, skill_names=None):
    install_counts = _installed_skill_counts(conn)
    usage = {
        r["skill"]: {
            "window_sessions": int(r["window_sessions"] or 0),
            "last_day": r["last_day"],
        }
        for r in conn.execute("""
          SELECT skill,
            SUM(CASE WHEN day >= ? AND day <= ? THEN 1 ELSE 0 END) window_sessions,
            MAX(day) last_day
          FROM skill_uses
          WHERE mode='used'
          GROUP BY skill
        """, (window["start"], window["end"]))
    }

    def is_company_item(item):
        name = item.get("name")
        return bool(name) and _skill_source(name, catalog_by) in CATALOG_COMPANY_TYPES

    current = []
    previous_count = 0
    for item in catalog_items or []:
        if not is_company_item(item):
            continue
        published_day = _catalog_published_day(item.get("published_at"))
        if not published_day:
            continue
        if window["previous_start"] <= published_day <= window["previous_end"]:
            previous_count += 1
        if not (window["start"] <= published_day <= window["end"]):
            continue
        name = item["name"]
        stat = usage.get(name, {})
        current.append(_named_skill(name, skill_names, {
            "source": _skill_source(name, catalog_by),
            "version": item.get("version") or "",
            "author": item.get("author") or "",
            "published_at": item.get("published_at"),
            "published_day": published_day,
            "updated_at": item.get("updated_at") or "",
            "path": item.get("path") or "",
            "sha": item.get("sha") or "",
            "installers": int(install_counts.get(name, 0)),
            "window_sessions": int(stat.get("window_sessions") or 0),
            "last_day": stat.get("last_day"),
        }))
    current.sort(key=lambda x: x["name"])
    current.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return {
        "items": current,
        "current_count": len(current),
        "previous_count": previous_count,
    }


EVIDENCE_KINDS = {
    "total", "untracked", "coverage", "operators", "avg_per_session",
    "idle", "unused_ratio", "zero_install", "top3", "runtime", "source",
}


def _clean_limit_offset(limit, offset):
    try:
        limit = int(limit)
        offset = int(offset)
    except Exception:
        raise HTTPException(400, "limit and offset must be integers")
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be between 1 and 500")
    if offset < 0:
        raise HTTPException(400, "offset must be >= 0")
    return limit, offset


def _evidence_actions(kind):
    labels = {
        "total": [("inspect-records", "看原始记录"), ("group-by-skill", "按 skill 分组"), ("group-by-operator", "按使用者分组")],
        "untracked": [("inspect-records", "看未收录记录"), ("group-by-operator", "按使用者分组"), ("collect-candidates", "复制收录候选")],
        "coverage": [("inspect-records", "看公司库触发"), ("group-by-skill", "看覆盖 skill"), ("group-by-operator", "按使用者分组")],
        "operators": [("group-by-operator", "看操作员"), ("inspect-records", "看原始记录")],
        "avg_per_session": [("group-by-session", "看会话分布"), ("inspect-records", "看原始记录")],
        "idle": [("inspect-list", "看闲置名单"), ("copy-list", "复制名单")],
        "unused_ratio": [("inspect-list", "看装了没用名单"), ("copy-list", "复制名单")],
        "zero_install": [("inspect-list", "看零装机名单"), ("copy-list", "复制名单")],
        "top3": [("inspect-records", "看集中记录"), ("group-by-skill", "看 Top3")],
        "runtime": [("group-by-runtime", "看 runtime"), ("inspect-records", "看原始记录")],
        "source": [("group-by-source", "看来源"), ("inspect-records", "看原始记录")],
    }
    return [{"id": key, "label": label} for key, label in labels.get(kind, labels["total"])]


def _forced_sources(kind):
    if kind == "untracked":
        return {"non_catalog"}
    if kind == "coverage":
        return set(CATALOG_COMPANY_TYPES)
    if kind in {"idle", "unused_ratio", "zero_install"}:
        return set(CATALOG_COMPANY_TYPES)
    return None


def _source_filter(kind, src, ignored):
    src = _skill_source_key(src) if src else ""
    forced = _forced_sources(kind)
    if forced is None:
        return {src} if src else None, src
    if src and src in forced:
        return {src}, src
    if src and src not in forced:
        ignored.append({
            "name": "src",
            "value": src,
            "reason": f"kind_{kind}_forces_{'_or_'.join(sorted(forced))}",
        })
    return forced, "non_catalog" if forced == {"non_catalog"} else ",".join(sorted(forced))


def _matching_skill_names(q, skill_names):
    needle = (q or "").strip().casefold()
    if not needle:
        return []
    return sorted(name for name, labels in (skill_names or {}).items() if any(
        needle in str(value or "").casefold()
        for value in (name, labels.get("display_name"), labels.get("display_name_zh"))
    ))


def _evidence_fetch_rows(conn, window_start, window_end, q="", rt="", skill="", operator="",
                         display_names=None):
    clauses = ["mode='used'", "day >= ?", "day <= ?"]
    params = [window_start, window_end]
    if rt:
        clauses.append("COALESCE(runtime,'') = ?")
        params.append(rt)
    if skill:
        clauses.append("skill = ?")
        params.append(skill)
    if operator:
        clauses.append("operator = ?")
        params.append(operator)
    if q:
        needle = f"%{q.casefold()}%"
        matched = _matching_skill_names(q, display_names)
        extra = f" OR skill IN ({','.join('?' for _ in matched)})" if matched else ""
        clauses.append(f"(lower(skill) LIKE ? OR lower(COALESCE(operator,'')) LIKE ?{extra})")
        params.extend([needle, needle])
        params.extend(matched)
    return [dict(r) for r in conn.execute(f"""
      SELECT day, first_seen, skill, COALESCE(operator,'') operator,
        COALESCE(runtime,'') runtime, session_id
      FROM skill_uses
      WHERE {' AND '.join(clauses)}
    """, params)]


def _annotate_evidence_rows(rows, catalog_by, skill_names=None):
    out = []
    for row in rows:
        item = dict(row)
        item["runtime"] = item.get("runtime") or "unknown"
        source = _skill_source(item["skill"], catalog_by)
        item.update(_skill_display_fields(item["skill"], skill_names))
        item["source"] = source
        item["_source_key"] = _skill_source_key(source)
        out.append(item)
    return out


def _filter_evidence_rows(rows, source_keys):
    if not source_keys:
        return rows
    return [row for row in rows if row.get("_source_key") in source_keys]


def _evidence_top_skills(rows):
    stats = {}
    for row in rows:
        item = stats.setdefault(row["skill"], {
            "name": row["skill"],
            "display_name": row.get("display_name") or row["skill"],
            "display_name_zh": row.get("display_name_zh") or row["skill"],
            "source": row.get("source"),
            "records": 0,
            "operators": set(),
            "last_day": "",
        })
        item["records"] += 1
        if row.get("operator"):
            item["operators"].add(row["operator"])
        if (row.get("day") or "") > (item.get("last_day") or ""):
            item["last_day"] = row.get("day") or ""
    out = []
    for item in stats.values():
        out.append({
            "name": item["name"],
            "display_name": item["display_name"],
            "display_name_zh": item["display_name_zh"],
            "source": item.get("source"),
            "records": item["records"],
            "operators": len(item["operators"]),
            "last_day": item.get("last_day"),
        })
    out.sort(key=lambda x: (-x["records"], x["name"]))
    return out


def _evidence_top_operators(rows):
    stats = {}
    for row in rows:
        operator = row.get("operator") or ""
        if not operator:
            continue
        item = stats.setdefault(operator, {"operator": operator, "records": 0, "skills": set(), "last_day": ""})
        item["records"] += 1
        item["skills"].add(row["skill"])
        if (row.get("day") or "") > (item.get("last_day") or ""):
            item["last_day"] = row.get("day") or ""
    out = [{
        "operator": item["operator"],
        "records": item["records"],
        "skills": len(item["skills"]),
        "last_day": item.get("last_day"),
    } for item in stats.values()]
    out.sort(key=lambda x: (-x["records"], x["operator"]))
    return out


def _evidence_daily(rows):
    stats = {}
    for row in rows:
        day = row.get("day") or ""
        if day:
            stats[day] = stats.get(day, 0) + 1
    return [{"day": day, "records": stats[day]} for day in sorted(stats)]


def _evidence_record_summary(rows, items=None, installed=0):
    skills = {row["skill"] for row in rows if row.get("skill")}
    operators = {row["operator"] for row in rows if row.get("operator")}
    sessions = {row["session_id"] for row in rows if row.get("session_id")}
    untracked = sum(1 for row in rows if row.get("_source_key") == "non_catalog")
    company = sum(1 for row in rows if row.get("_source_key") in CATALOG_COMPANY_TYPES)
    external = sum(1 for row in rows if row.get("_source_key") == "external")
    summary = {
        "records": len(rows),
        "skills": len(skills),
        "operators": len(operators),
        "sessions": len(sessions),
        "untracked_records": untracked,
        "company_records": company,
        "external_records": external,
    }
    if items is not None:
        summary["items"] = len(items)
        summary["installed"] = int(installed or 0)
        summary["unused_ratio"] = (len(items) / installed) if installed else 0
    if sessions:
        summary["avg_skills_per_session"] = len(rows) / len(sessions)
    return summary


def _evidence_list_items(conn, kind, window_start, window_end, source_keys, q="", skill="", rt="",
                         operator="", catalog_by=None, skill_names=None):
    catalog_by = catalog_by or {}
    company_names = {n for n, src in catalog_by.items() if src in CATALOG_COMPANY_TYPES}
    installed_names = _installed_skill_names(conn) & company_names
    used_rows = _evidence_fetch_rows(conn, window_start, window_end, q="", rt=rt, skill="",
                                     operator=operator, display_names=skill_names)
    used_rows = _annotate_evidence_rows(used_rows, catalog_by, skill_names)
    used_rows = _filter_evidence_rows(used_rows, source_keys)
    used_names = {row["skill"] for row in used_rows if row["skill"] in company_names}
    if kind == "zero_install":
        names = sorted(company_names - installed_names)
        installed_total = len(company_names)
    else:
        names = sorted(installed_names - used_names)
        installed_total = len(installed_names)
    if source_keys:
        names = [name for name in names if _skill_source_key(_skill_source(name, catalog_by)) in source_keys]
    if skill:
        names = [name for name in names if name == skill]
    if q:
        matched = set(_matching_skill_names(q, skill_names))
        names = [name for name in names if name in matched]
    installer_details = _installed_skill_details(conn)
    last_days = {r["skill"]: r["last_day"] for r in conn.execute("""
      SELECT skill, MAX(day) last_day
      FROM skill_uses
      WHERE mode='used'
      GROUP BY skill
    """)}
    items = []
    for name in names:
        details = [] if kind == "zero_install" else installer_details.get(name, [])
        items.append(_named_skill(name, skill_names, {
            "source": _skill_source(name, catalog_by),
            "installers": len(details),
            "installers_detail": details,
            "last_day": last_days.get(name),
        }))
    items.sort(key=lambda x: x["name"])
    items.sort(key=lambda x: x.get("last_day") or "", reverse=True)
    items.sort(key=lambda x: x["installers"] or 0, reverse=True)
    return items, installed_total


def skills_evidence_payload(conn, days=30, w=None, wstart=None, wend=None, kind="total",
                            q="", rt="", src="", skill="", operator="", limit=100, offset=0):
    kind = (kind or "total").strip()
    if kind not in EVIDENCE_KINDS:
        raise HTTPException(400, "kind is invalid")
    limit, offset = _clean_limit_offset(limit, offset)
    window = _skills_window(days, w, wstart, wend)
    window_start = window["start"]
    window_end = window["end"]
    catalog_items, catalog_by, catalog_meta = _catalog_context(conn)
    skill_names = _skill_name_map(conn, catalog_items)
    q = (q or "").strip()
    rt = (rt or "").strip()
    skill = _skill_use_name(skill) if skill else ""
    operator = (operator or "").strip()
    ignored = []
    source_keys, applied_src = _source_filter(kind, src, ignored)
    applied_filters = {
        "w": window["key"],
        "window_start": window_start,
        "window_end": window_end,
        "q": q,
        "rt": rt,
        "src": applied_src,
        "skill": skill,
        "operator": operator,
    }

    if kind in {"idle", "unused_ratio", "zero_install"}:
        items, installed = _evidence_list_items(
            conn, kind, window_start, window_end, source_keys, q=q, skill=skill,
            rt=rt, operator=operator, catalog_by=catalog_by, skill_names=skill_names,
        )
        page_items = items[offset:offset + limit]
        return {
            "kind": kind,
            "today": stats_today().isoformat(),
            "window": window,
            "summary": _evidence_record_summary([], items, installed),
            "actions": _evidence_actions(kind),
            "applied_filters": applied_filters,
            "ignored_filters": ignored,
            "top_skills": [],
            "top_operators": [],
            "daily": [],
            "records": [],
            "items": page_items,
            "skill_names": skill_names,
            "catalog": catalog_meta,
        }

    rows = _evidence_fetch_rows(conn, window_start, window_end, q=q, rt=rt, skill=skill,
                                operator=operator, display_names=skill_names)
    rows = _annotate_evidence_rows(rows, catalog_by, skill_names)
    rows = _filter_evidence_rows(rows, source_keys)
    if kind == "operators":
        rows = [row for row in rows if row.get("operator")]
    if kind == "top3":
        top3 = {item["name"] for item in _evidence_top_skills(rows)[:3]}
        rows = [row for row in rows if row["skill"] in top3]
    rows.sort(key=lambda row: (row.get("first_seen") or row.get("day") or "", row.get("skill") or ""), reverse=True)
    public_rows = []
    for row in rows[offset:offset + limit]:
        item = {k: row.get(k) for k in (
            "day", "first_seen", "skill", "display_name", "display_name_zh",
            "operator", "runtime", "source", "session_id")}
        public_rows.append(item)
    return {
        "kind": kind,
        "today": stats_today().isoformat(),
        "window": window,
        "summary": _evidence_record_summary(rows),
        "actions": _evidence_actions(kind),
        "applied_filters": applied_filters,
        "ignored_filters": ignored,
        "top_skills": _evidence_top_skills(rows)[:20],
        "top_operators": _evidence_top_operators(rows)[:20],
        "daily": _evidence_daily(rows),
        "records": public_rows,
        "items": [],
        "skill_names": skill_names,
        "catalog": catalog_meta,
    }


def _source_key_for_skill(skill, catalog_by):
    return _skill_source_key(_skill_source(skill, catalog_by))


def _matches_operator_scope(runtime, skill, catalog_by, rt="", src=""):
    normalized_runtime = runtime or "unknown"
    if rt and normalized_runtime != rt:
        return False
    if src and _source_key_for_skill(skill, catalog_by) != _skill_source_key(src):
        return False
    return True


def skills_overview(conn, days, w=None, wstart=None, wend=None, rt="", src="", scope=""):
    window = _skills_window(days, w, wstart, wend)
    days = window["days"]
    today = stats_today()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    d14 = (today - timedelta(days=13)).isoformat()
    window_start = window["start"]
    window_end = window["end"]
    previous_start = window["previous_start"]
    previous_end = window["previous_end"]
    catalog_items, catalog_by, catalog_meta = _catalog_context(conn)
    skill_names = _skill_name_map(conn, catalog_items)
    scope = (scope or "all").strip().lower()
    if scope not in ("", "all", "new"):
        raise HTTPException(400, "scope must be all or new")
    scope = "new" if scope == "new" else "all"
    new_skill_names = _new_used_skill_names(conn, window_start, window_end)
    scoped_skill_names = new_skill_names if scope == "new" else None
    scope_sql, scope_params = _skill_scope_sql(scoped_skill_names)

    daily_where, daily_params = ["mode='used'", "day IS NOT NULL"], []
    daily_where.append("day >= ?")
    daily_where.append("day <= ?")
    daily_params.extend([window_start, window_end])
    if scoped_skill_names is not None:
        daily_where.append(scope_sql.replace(" AND ", "", 1).strip())
        daily_params.extend(scope_params)
    daily_rows = conn.execute(f"""
      SELECT day, skill, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE {' AND '.join(daily_where)}
      GROUP BY day, skill, runtime
      ORDER BY day ASC, skill ASC, runtime ASC
    """, daily_params).fetchall()
    daily = [_skill_record(r["skill"], skill_names, {
        "day": r["day"],
        "runtime": r["runtime"] or "unknown",
        "sessions": int(r["sessions"] or 0),
        "source": _skill_source(r["skill"], catalog_by),
    }) for r in daily_rows]

    base_rows = conn.execute(f"""
      SELECT skill,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        SUM(CASE WHEN day >= ? AND day <= ? THEN 1 ELSE 0 END) sessions_window,
        SUM(CASE WHEN day >= ? AND day <= ? THEN 1 ELSE 0 END) previous_sessions,
        COUNT(*) sessions_total,
        COUNT(DISTINCT CASE WHEN day >= ? THEN operator END) users_30d,
        MAX(day) last_day
      FROM skill_uses
      WHERE mode='used'{scope_sql}
      GROUP BY skill
    """, (
        d7,
        d30,
        window_start,
        window_end,
        previous_start,
        previous_end,
        d30,
        *scope_params,
    )).fetchall()
    runtime_counts = {}
    for r in conn.execute(f"""
      SELECT skill, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used'{scope_sql}
      GROUP BY skill, runtime
    """, scope_params):
        runtime_counts.setdefault(r["skill"], {})[r["runtime"] or "unknown"] = int(r["sessions"] or 0)
    trend_days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    trend = {}
    for r in conn.execute(f"""
      SELECT skill, day, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND day >= ?{scope_sql}
      GROUP BY skill, day
    """, (d14, *scope_params)):
        trend.setdefault(r["skill"], {})[r["day"]] = int(r["sessions"] or 0)
    table = []
    for r in base_rows:
        skill = r["skill"]
        table.append(_named_skill(skill, skill_names, {
            "source": _skill_source(skill, catalog_by),
            "sessions_7d": int(r["sessions_7d"] or 0),
            "sessions_30d": int(r["sessions_30d"] or 0),
            "sessions_window": int(r["sessions_window"] or 0),
            "previous_sessions": int(r["previous_sessions"] or 0),
            "sessions_total": int(r["sessions_total"] or 0),
            "users_30d": int(r["users_30d"] or 0),
            "runtime_counts": runtime_counts.get(skill, {}),
            "trend_14d": [trend.get(skill, {}).get(day, 0) for day in trend_days],
            "trend_days": trend_days,
            "last_day": r["last_day"],
        }))
    table.sort(key=lambda x: (-x["sessions_window"], -x["sessions_total"], x["name"]))

    operator_stats = {}
    operator_daily_counts = {}

    def operator_stat(operator):
        return operator_stats.setdefault(operator, {
            "operator": operator,
            "sessions_7d": 0,
            "sessions_30d": 0,
            "sessions_window": 0,
            "previous_sessions": 0,
            "sessions_total": 0,
            "skills": set(),
            "window_skills": set(),
            "session_count": 0,
            "runtime_counts": {},
            "source_counts": {},
            "window_runtime_counts": {},
            "window_source_counts": {},
            "trend": {},
            "last_day": "",
        })

    for r in conn.execute(f"""
      SELECT operator, skill, COALESCE(runtime,'') runtime,
        COUNT(*) sessions_total,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_7d,
        SUM(CASE WHEN day >= ? THEN 1 ELSE 0 END) sessions_30d,
        SUM(CASE WHEN day >= ? AND day <= ? THEN 1 ELSE 0 END) sessions_window,
        SUM(CASE WHEN day >= ? AND day <= ? THEN 1 ELSE 0 END) previous_sessions,
        MAX(day) last_day
      FROM skill_uses
      WHERE mode='used' AND day IS NOT NULL AND trim(COALESCE(operator,'')) <> ''{scope_sql}
      GROUP BY operator, skill, runtime
      ORDER BY operator ASC, skill ASC, runtime ASC
    """, (d7, d30, window_start, window_end, previous_start, previous_end, *scope_params)):
        runtime = r["runtime"] or "unknown"
        skill = r["skill"]
        if not _matches_operator_scope(runtime, skill, catalog_by, rt, src):
            continue
        operator = r["operator"]
        source_key = _source_key_for_skill(skill, catalog_by)
        sessions_total = int(r["sessions_total"] or 0)
        sessions_window = int(r["sessions_window"] or 0)
        stat = operator_stat(operator)
        stat["sessions_total"] += sessions_total
        stat["sessions_7d"] += int(r["sessions_7d"] or 0)
        stat["sessions_30d"] += int(r["sessions_30d"] or 0)
        stat["sessions_window"] += sessions_window
        stat["previous_sessions"] += int(r["previous_sessions"] or 0)
        stat["skills"].add(skill)
        stat["last_day"] = max(stat["last_day"], r["last_day"] or "")
        stat["runtime_counts"][runtime] = stat["runtime_counts"].get(runtime, 0) + sessions_total
        stat["source_counts"][source_key] = stat["source_counts"].get(source_key, 0) + sessions_total
        if sessions_window:
            stat["window_skills"].add(skill)
            stat["window_runtime_counts"][runtime] = stat["window_runtime_counts"].get(runtime, 0) + sessions_window
            stat["window_source_counts"][source_key] = stat["window_source_counts"].get(source_key, 0) + sessions_window

    if not rt and not src:
        for r in conn.execute(f"""
          SELECT operator, COUNT(DISTINCT session_id) session_count
          FROM skill_uses
          WHERE mode='used' AND day IS NOT NULL AND trim(COALESCE(operator,'')) <> ''{scope_sql}
          GROUP BY operator
        """, scope_params):
            stat = operator_stats.get(r["operator"])
            if stat is not None:
                stat["session_count"] = int(r["session_count"] or 0)
    else:
        operator_sessions = {}
        for r in conn.execute(f"""
          SELECT operator, session_id, skill, COALESCE(runtime,'') runtime
          FROM skill_uses
          WHERE mode='used' AND day IS NOT NULL AND trim(COALESCE(operator,'')) <> ''{scope_sql}
          GROUP BY operator, session_id, skill, runtime
          ORDER BY operator ASC
        """, scope_params):
            runtime = r["runtime"] or "unknown"
            if not _matches_operator_scope(runtime, r["skill"], catalog_by, rt, src):
                continue
            operator_sessions.setdefault(r["operator"], set()).add(r["session_id"])
        for operator, sessions in operator_sessions.items():
            stat = operator_stats.get(operator)
            if stat is not None:
                stat["session_count"] = len(sessions)

    operator_day_start = min(window_start, d14)
    for r in conn.execute(f"""
      SELECT day, operator, skill, COALESCE(runtime,'') runtime, COUNT(*) sessions
      FROM skill_uses
      WHERE mode='used' AND day IS NOT NULL AND day >= ?
        AND trim(COALESCE(operator,'')) <> ''{scope_sql}
      GROUP BY day, operator, skill, runtime
      ORDER BY day ASC, operator ASC, runtime ASC, skill ASC
    """, (operator_day_start, *scope_params)):
        runtime = r["runtime"] or "unknown"
        skill = r["skill"]
        if not _matches_operator_scope(runtime, skill, catalog_by, rt, src):
            continue
        operator = r["operator"]
        stat = operator_stats.get(operator)
        if stat is None:
            continue
        day = r["day"]
        sessions = int(r["sessions"] or 0)
        source_key = _source_key_for_skill(skill, catalog_by)
        if day >= d14:
            stat["trend"][day] = stat["trend"].get(day, 0) + sessions
        if window_start <= day <= window_end:
            key = (day, operator, runtime, source_key)
            operator_daily_counts[key] = operator_daily_counts.get(key, 0) + sessions

    operator_daily = [{
        "day": day,
        "operator": operator,
        "runtime": runtime,
        "source": source,
        "sessions": sessions,
    } for (day, operator, runtime, source), sessions in sorted(operator_daily_counts.items())]

    operator_table = []
    for operator, stat in operator_stats.items():
        operator_table.append({
            "operator": operator,
            "sessions_7d": int(stat["sessions_7d"]),
            "sessions_30d": int(stat["sessions_30d"]),
            "sessions_window": int(stat["sessions_window"]),
            "previous_sessions": int(stat["previous_sessions"]),
            "sessions_total": int(stat["sessions_total"]),
            "skill_count": len(stat["skills"]),
            "window_skill_count": len(stat["window_skills"]),
            "session_count": int(stat["session_count"]),
            "runtime_counts": stat["runtime_counts"],
            "source_counts": stat["source_counts"],
            "window_runtime_counts": stat["window_runtime_counts"],
            "window_source_counts": stat["window_source_counts"],
            "trend_14d": [stat["trend"].get(day, 0) for day in trend_days],
            "trend_days": trend_days,
            "last_day": stat["last_day"] or None,
        })
    operator_table.sort(key=lambda x: (-x["sessions_window"], -x["sessions_total"], x["operator"]))

    company_names = {n for n, src in catalog_by.items() if src in CATALOG_COMPANY_TYPES}
    installed_names = _installed_skill_names(conn) & company_names
    used_window_names = {r["skill"] for r in conn.execute("""
      SELECT DISTINCT skill FROM skill_uses
      WHERE mode='used' AND day >= ? AND day <= ?
    """, (window_start, window_end)) if r["skill"] in company_names}
    funnel = {
        "available": bool(company_names),
        "catalog": _catalog_list(company_names, catalog_by, skill_names),
        "installed": _catalog_list(installed_names, catalog_by, skill_names),
        "used_30d": _catalog_list(used_window_names, catalog_by, skill_names),
        "idle": _catalog_list(installed_names - used_window_names, catalog_by, skill_names),
    }
    governance = {
        "untracked_usage": _skills_governance_untracked(
            conn, window_start, window_end, d30, trend_days, catalog_by,
            scoped_names=scoped_skill_names, display_names=skill_names),
    }
    governance.update(_governance_buckets(
        conn, window_start, catalog_by, catalog_meta, company_names,
        installed_names, used_window_names, skill_names))
    published = _published_skill_summary(conn, catalog_items, catalog_by, window, skill_names)
    period = _period_comparison(conn, window, catalog_by, scoped_skill_names)
    period.update({
        "current_published_skill_count": published["current_count"],
        "previous_published_skill_count": published["previous_count"],
    })
    return {
        "days": days,
        "scope": scope,
        "new_skill_count": len(new_skill_names),
        "published_skills": published["items"],
        "window": window,
        "today": today.isoformat(),
        "daily": daily,
        "table": table,
        "operator_daily": operator_daily,
        "operator_table": operator_table,
        "governance": governance,
        "period_comparison": period,
        "attribution": _skills_attribution(conn, window_start, window_end, catalog_by, scoped_skill_names),
        "funnel": funnel,
        "skill_names": skill_names,
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
    today = stats_today()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    catalog_items, catalog_by, catalog_meta = _catalog_context(conn)
    skill_names = _skill_name_map(conn, catalog_items)
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
    daily = [_skill_record(r["skill"], skill_names, {
        "day": r["day"], "sessions": int(r["sessions"] or 0),
    }) for r in conn.execute("""
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
        skill_table.append(_named_skill(skill, skill_names, {
            "source": _skill_source(skill, catalog_by),
            "sessions_7d": int(r["sessions_7d"] or 0),
            "sessions_30d": int(r["sessions_30d"] or 0),
            "sessions_total": int(r["sessions_total"] or 0),
            "runtime_counts": skill_runtime_counts.get(skill, {}),
            "last_day": r["last_day"],
        }))
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
    records = [_skill_record(r["skill"], skill_names, {
        "day": r["day"], "runtime": r["runtime"], "session_id": r["session_id"],
        "first_seen": r["first_seen"],
    }) for r in conn.execute("""
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
        "skill_names": skill_names,
        "catalog": catalog_meta,
    }


def skill_detail_payload(conn, name):
    name = _skill_use_name(name)
    if not name:
        raise HTTPException(404, "skill not found")
    exists = conn.execute("SELECT COUNT(*) c FROM skill_uses WHERE skill=?", (name,)).fetchone()["c"]
    if not exists:
        raise HTTPException(404, "skill not found")
    today = stats_today()
    d7 = (today - timedelta(days=6)).isoformat()
    d30 = (today - timedelta(days=29)).isoformat()
    catalog_items, catalog_by, catalog_meta = _catalog_context(conn)
    skill_names = _skill_name_map(conn, catalog_items)
    installed_count = _installed_skill_counts(conn).get(name, 0)
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
        **_skill_display_fields(name, skill_names),
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
            "installed_count": int(installed_count or 0),
        },
        "daily": list(daily_map.values()),
        "runtime": sorted(runtime_map.values(), key=lambda x: (-(x["used"] + x["equipped"]), x["runtime"])),
        "operators": sorted(operator_map.values(), key=lambda x: (-(x["used"] + x["equipped"]), x["operator"])),
        "records": records,
        "skill_names": {name: skill_names.get(name, _skill_display_fields(name, skill_names))},
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
    catalog_items, _catalog_by, _catalog_meta = _catalog_context(conn)
    skill_names = _skill_name_map(conn, catalog_items)
    profiles = load_profiles(conn)
    for profile in profiles.values():
        _annotate_profile_skill_names(profile, skill_names)
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
    agent_overview = _agent_overview(cards, _SHIM_MANIFEST["version"])
    return {
        "now": now_iso(),
        "sessions": cards,
        "feed": [{"operator": r["operator"], "agent": r["agent"], "runtime": r["runtime"],
                  "status": r["status"], "current_step": r["current_step"],
                  "task": r["task"], "ts": r["ts"]} for r in feed],
        "leverage": leverage(conn),
        "skills": skill_usage(conn, skill_names),
        "skill_names": skill_names,
        "shim": {"version": _SHIM_MANIFEST["version"], "files": len(_SHIM_MANIFEST["files"])},
        "agent_overview": agent_overview,
        "totals": {
            "live": len(live), "operators": len(ops), "agents": len(agents),
            "today_active": sum(v["today"] for v in dur.values()),
        },
    }


def _state_compute_or_cache(force=False):
    from server import app  # 延迟读 STATE_TTL_SECONDS(可变开关)
    while True:
        now = time.monotonic()
        with _state_cache_cond:
            cached = _state_cache.get("data")
            cached_at = float(_state_cache.get("at") or 0.0)
            ttl = float(app.STATE_TTL_SECONDS)
            if (not force) and ttl > 0 and cached is not None and now - cached_at < ttl:
                return cached
            if _state_cache.get("computing"):
                if cached is not None:
                    return cached
                _state_cache_cond.wait(timeout=5.0)
                continue
            _state_cache["computing"] = True
            break

    try:
        with closing(db()) as conn:
            # 通过 app 命名空间间接调用,保留 monkeypatch(app_mod, "_snapshot", ...) 语义
            data = app._snapshot(conn)
    except Exception:
        with _state_cache_cond:
            _state_cache["computing"] = False
            _state_cache_cond.notify_all()
        raise

    with _state_cache_cond:
        _state_cache["at"] = time.monotonic()
        _state_cache["data"] = data
        _state_cache["computing"] = False
        _state_cache_cond.notify_all()
    return data


@router.get("/api/state")
async def state():
    data = await run_in_threadpool(_state_compute_or_cache)
    return JSONResponse(data)


def _sse_state(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: state\ndata: {payload}\n\n"


@router.get("/api/state/stream")
async def state_stream(request: Request):
    async def events():
        data = await run_in_threadpool(_state_compute_or_cache)
        last_rev = _state_revision()
        last_keepalive = time.monotonic()
        yield _sse_state(data)
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(1.0)
            rev = _state_revision()
            if rev != last_rev:
                data = await run_in_threadpool(_state_compute_or_cache)
                last_rev = rev
                last_keepalive = time.monotonic()
                yield _sse_state(data)
            elif time.monotonic() - last_keepalive >= 25:
                last_keepalive = time.monotonic()
                yield ": keepalive\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/agents")
async def agents_stats(w: str = "today", wstart: int | None = Query(None), wend: int | None = Query(None),
                       q: str = "", status: str = "all", signal: str = "", sort: str = "window_time"):
    def compute():
        snapshot = _state_compute_or_cache()
        return agents_overview_payload(
            snapshot["sessions"], (snapshot.get("shim") or {}).get("version"),
            w, wstart, wend, q, status, signal, sort,
        )

    return JSONResponse(await run_in_threadpool(compute))


@router.get("/api/skills")
def skills_stats(request: Request, days: int = 30, w: str | None = None, wstart: int | None = Query(None), wend: int | None = Query(None),
                 rt: str = "", src: str = "", scope: str = ""):
    with closing(db()) as conn:
        payload = skills_overview(conn, days, w, wstart, wend, rt, src, scope)
    return _conditional_json(request, payload)


@router.get("/api/skills/evidence")
def skills_evidence(request: Request, kind: str = "total", days: int = 30, w: str | None = None,
                    wstart: int | None = Query(None), wend: int | None = Query(None),
                    q: str = "", rt: str = "", src: str = "", skill: str = "",
                    operator: str = "", limit: int = 100, offset: int = 0):
    with closing(db()) as conn:
        payload = skills_evidence_payload(
            conn, days, w, wstart, wend, kind, q, rt, src, skill, operator, limit, offset,
        )
    return _conditional_json(request, payload)


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
