"""Token usage read-only mirror.

This route intentionally does not touch the TATP ingest protocol or local
SQLite store. It only fetches already-aggregated key usage from the downstream
distribution service and normalizes a small dashboard payload.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool


router = APIRouter()

_DEFAULT_BASE_URL = "https://api.tranfu.com"
_DEFAULT_USAGE_PATH = "/api/data/keys"
_MAX_DAYS = 90
_MAX_RANGE_SECONDS = 180 * 86400
_UPSTREAM_CACHE = {}
_UPSTREAM_CACHE_LOCK = Lock()


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _config():
    return {
        "base_url": os.environ.get("TF_TOKEN_USAGE_BASE_URL", _DEFAULT_BASE_URL).rstrip("/"),
        "path": os.environ.get("TF_TOKEN_USAGE_PATH", _DEFAULT_USAGE_PATH),
        "access_token": os.environ.get("TF_TOKEN_USAGE_ACCESS_TOKEN", ""),
        "cookie": os.environ.get("TF_TOKEN_USAGE_COOKIE", ""),
        "user_id": os.environ.get("TF_TOKEN_USAGE_USER_ID", ""),
        "timeout": float(os.environ.get("TF_TOKEN_USAGE_TIMEOUT", "15")),
        "cache_ttl": float(os.environ.get("TF_TOKEN_USAGE_CACHE_TTL", "90")),
        "demo": _env_bool("TF_TOKEN_USAGE_DEMO", True),
    }


def _range(days):
    now = int(time.time())
    start = now - days * 86400
    return start, now


def _resolve_range(days, start_timestamp, end_timestamp):
    if start_timestamp and end_timestamp:
        start = int(start_timestamp)
        end = int(end_timestamp)
        if start >= end:
            raise HTTPException(status_code=400, detail="start_timestamp must be before end_timestamp")
        if end - start > _MAX_RANGE_SECONDS:
            raise HTTPException(status_code=400, detail="time range is too large")
        return start, end
    return _range(days)


def _upstream_granularity(granularity):
    return "hour" if granularity in {"hour", "four_hour"} else "day"


def _bucket_start(timestamp, granularity, timezone_offset_minutes):
    if granularity not in {"four_hour", "week", "month"}:
        return timestamp
    tz = timezone(timedelta(minutes=timezone_offset_minutes))
    dt = datetime.fromtimestamp(timestamp, tz)
    if granularity == "four_hour":
        dt = dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0)
    elif granularity == "week":
        dt = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        dt = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(dt.timestamp())


def _aggregate_trend(rows, granularity, timezone_offset_minutes):
    if granularity not in {"four_hour", "week", "month"}:
        return rows
    grouped = {}
    for row in rows:
        key = (row.get("token_id") or 0, row.get("token_name") or "", _bucket_start(int(row.get("created_at") or 0), granularity, timezone_offset_minutes))
        item = grouped.setdefault(key, {
            "token_id": row.get("token_id") or 0,
            "token_name": row.get("token_name") or "",
            "username": row.get("username") or "",
            "user_id": row.get("user_id") or 0,
            "created_at": key[2],
            "count": 0,
            "error_count": 0,
            "quota": 0,
            "token_used": 0,
        })
        item["count"] += int(row.get("count") or 0)
        item["error_count"] += int(row.get("error_count") or 0)
        item["quota"] += int(row.get("quota") or 0)
        item["token_used"] += int(row.get("token_used") or 0)
    return sorted(grouped.values(), key=lambda item: (item["created_at"], -item["quota"]))


def _query_upstream(cfg, start, end, granularity, timezone_offset_minutes):
    if not (cfg["access_token"] or cfg["cookie"]) or not cfg["user_id"]:
        raise RuntimeError("token usage upstream credentials are not configured")

    query = urllib.parse.urlencode({
        "start_timestamp": str(start),
        "end_timestamp": str(end),
        "time_granularity": _upstream_granularity(granularity),
        "timezone_offset_minutes": str(timezone_offset_minutes),
    })
    url = f"{cfg['base_url']}{cfg['path']}?{query}"
    headers = {
        "Accept": "application/json",
        "New-Api-User": cfg["user_id"],
    }
    if cfg["access_token"]:
        headers["Authorization"] = cfg["access_token"]
    if cfg["cookie"]:
        headers["Cookie"] = cfg["cookie"]
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"upstream returned {exc.code}: {body[:180]}") from exc
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc

    if not payload.get("success"):
        raise RuntimeError(payload.get("message") or "upstream returned success=false")
    return payload.get("data") or {}


def _cached_query_upstream(cfg, start, end, granularity, timezone_offset_minutes):
    upstream_granularity = _upstream_granularity(granularity)
    key = (cfg["base_url"], cfg["path"], cfg["user_id"], start, end, upstream_granularity, timezone_offset_minutes)
    now = time.time()
    if cfg["cache_ttl"] > 0:
        with _UPSTREAM_CACHE_LOCK:
            cached = _UPSTREAM_CACHE.get(key)
            if cached and now - cached["ts"] <= cfg["cache_ttl"]:
                return deepcopy(cached["data"]), True

    data = _query_upstream(cfg, start, end, granularity, timezone_offset_minutes)
    if cfg["cache_ttl"] > 0:
        with _UPSTREAM_CACHE_LOCK:
            _UPSTREAM_CACHE[key] = {"ts": now, "data": deepcopy(data)}
    return data, False


def _demo_payload(start, end, granularity):
    now = int(time.time())
    names = [
        (1, "个人-张三-Codex", "personal", "张三"),
        (2, "个人-李四-图片生成", "personal", "李四"),
        (3, "Dapp-官网助手-生产", "dapp", "官网助手"),
        (4, "Dapp-图片工具-测试", "dapp", "图片工具"),
        (5, "个人-王五-Claude", "personal", "王五"),
    ]
    summary = []
    for i, name, group, username in names:
        request_count = 18 + i * 7
        error_count = 0 if i not in (2, 4) else i
        quota = 1600 * i + (350 if group == "dapp" else 0)
        token_used = quota * 11
        remain = 20000 - quota * 2 if i != 4 else 900
        summary.append({
            "token_id": i,
            "token_name": name,
            "username": username,
            "user_id": i,
            "status": 1,
            "group": group,
            "remain_quota": remain,
            "used_quota": quota * 3,
            "unlimited_quota": i == 3,
            "created_time": now - 86400 * (20 + i),
            "accessed_time": now - 900 * i,
            "expired_time": -1,
            "request_count": request_count,
            "error_count": error_count,
            "quota": quota,
            "prompt_tokens": int(token_used * 0.55),
            "completion_tokens": int(token_used * 0.45),
            "token_used": token_used,
            "avg_use_time": 1.2 + i / 4,
            "last_used_at": now - 900 * i,
            "top_model": "gpt-image-2" if i in (2, 4) else "gpt-5.5",
            "model_count": 2 if i in (1, 3) else 1,
        })

    step = 3600 if granularity == "hour" else 86400
    buckets = list(range(max(start, end - step * 12), end + 1, step))
    trend = []
    for bucket_index, created_at in enumerate(buckets[-12:]):
        for i, name, group, username in names:
            value = max(0, (bucket_index + 1) * (i + 2) * (2 if group == "dapp" else 1))
            if value % 5 == 0:
                continue
            trend.append({
                "token_id": i,
                "token_name": name,
                "username": username,
                "user_id": i,
                "created_at": created_at,
                "count": max(1, value // 4),
                "error_count": 1 if i == 4 and bucket_index > 8 else 0,
                "quota": value * 60,
                "token_used": value * 640,
            })

    models = []
    for token_id, token_name, group, username in names:
        model_names = ["gpt-5.5", "gpt-5.4-mini"] if group == "personal" else ["gpt-5.5", "gpt-image-2"]
        for idx, model_name in enumerate(model_names):
            quota = (token_id + idx + 1) * 750
            models.append({
                "token_id": token_id,
                "token_name": token_name,
                "username": username,
                "user_id": token_id,
                "model_name": model_name,
                "count": 10 + token_id * 2 + idx,
                "quota": quota,
                "token_used": quota * 12,
            })
    return {"summary": summary, "trend": trend, "models": models}


@router.get("/api/token-usage")
async def token_usage(
    days: int = Query(7, ge=1, le=_MAX_DAYS),
    start_timestamp: int | None = Query(None, ge=1),
    end_timestamp: int | None = Query(None, ge=1),
    time_granularity: str = Query("day", pattern="^(hour|four_hour|day|week|month)$"),
    timezone_offset_minutes: int = Query(0, ge=-840, le=840),
):
    cfg = _config()
    start, end = _resolve_range(days, start_timestamp, end_timestamp)
    granularity = time_granularity
    warning = ""
    source = "upstream"
    configured = bool((cfg["access_token"] or cfg["cookie"]) and cfg["user_id"])

    try:
        data, cached = await run_in_threadpool(_cached_query_upstream, cfg, start, end, granularity, timezone_offset_minutes)
    except Exception as exc:
        if not cfg["demo"]:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        data = _demo_payload(start, end, granularity)
        cached = False
        source = "demo"
        warning = str(exc)

    trend = _aggregate_trend(data.get("trend") or [], granularity, timezone_offset_minutes)
    return {
        "ok": True,
        "source": source,
        "configured": configured,
        "cached": cached,
        "warning": warning,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "range": {
            "start_timestamp": start,
            "end_timestamp": end,
            "days": days,
            "time_granularity": granularity,
            "timezone_offset_minutes": timezone_offset_minutes,
        },
        "data": {
            "summary": data.get("summary") or [],
            "trend": trend,
            "models": data.get("models") or [],
        },
    }
