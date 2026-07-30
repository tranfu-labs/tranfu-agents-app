"""Read-only Sub2API adapter for the optional Token Usage dashboard."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA_VERSION = 2
_LIVE_TTL = 60.0
_HISTORY_TTL = 900.0
_STALE_TTL = 86400.0
_ERROR_PAGE_SIZE = 500
_ERROR_BULK_LIMIT = 10000
_LEGACY_QUOTA_PER_USD = 500000
_SECRET_PATTERN = re.compile(r"(?:admin-|sk-)[A-Za-z0-9_.-]{8,}")
_JWT_PATTERN = re.compile(r"(?:Bearer\s+)?eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", re.IGNORECASE)


class Sub2APIError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Sub2APIConfig:
    base_url: str
    admin_key: str
    user_id: int
    timezone_name: str
    timeout: float
    max_concurrency: int
    access_token: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url and (self.admin_key or self.access_token) and self.user_id > 0)

    @property
    def auth_mode(self) -> str:
        if self.admin_key:
            return "admin_key"
        if self.access_token:
            return "access_token"
        return "unconfigured"


@dataclass
class _CacheEntry:
    stored_at: float
    payload: dict


_CACHE: dict[tuple, _CacheEntry] = {}
_CACHE_LOCK = threading.Lock()
_INFLIGHT: dict[tuple, threading.Event] = {}
_ENRICHMENT_CONTEXT: dict[tuple, dict] = {}
_ENRICHING: set[tuple] = set()
_STATUS_LOCK = threading.Lock()
_STATUS = {
    "upstream_version": "",
    "last_success_at": "",
    "last_error_code": "",
    "last_error_at": "",
    "capabilities": {},
}


def config_from_env() -> Sub2APIConfig:
    try:
        user_id = int(os.environ.get("TF_TOKEN_USAGE_SUB2API_USER_ID", "1"))
    except ValueError:
        user_id = 0
    try:
        max_concurrency = int(os.environ.get("TF_TOKEN_USAGE_MAX_CONCURRENCY", "4"))
    except ValueError:
        max_concurrency = 4
    return Sub2APIConfig(
        base_url=os.environ.get("TF_TOKEN_USAGE_BASE_URL", "https://api.tranfu.com").rstrip("/"),
        admin_key=os.environ.get("TF_TOKEN_USAGE_SUB2API_ADMIN_KEY", "").strip(),
        user_id=user_id,
        timezone_name=os.environ.get("TF_TOKEN_USAGE_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai",
        timeout=float(os.environ.get("TF_TOKEN_USAGE_TIMEOUT", "15")),
        max_concurrency=max(1, min(max_concurrency, 12)),
        access_token=(
            os.environ.get("TF_TOKEN_USAGE_SUB2API_ACCESS_TOKEN", "").strip()
            or os.environ.get("TF_TOKEN_USAGE_ACCESS_TOKEN", "").strip()
        ),
    )


def clear_caches():
    with _CACHE_LOCK:
        _CACHE.clear()
        _INFLIGHT.clear()
        _ENRICHMENT_CONTEXT.clear()
        _ENRICHING.clear()
    with _STATUS_LOCK:
        _STATUS.update({
            "upstream_version": "",
            "last_success_at": "",
            "last_error_code": "",
            "last_error_at": "",
            "capabilities": {},
        })


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_text(value) -> str:
    return _JWT_PATTERN.sub("[redacted]", _SECRET_PATTERN.sub("[redacted]", str(value or "")))[:240]


def _number(value, default=0):
    try:
        return float(value) if isinstance(value, float) else int(value or 0)
    except (TypeError, ValueError):
        return default


def _required_number(row: dict, field: str, context: str):
    value = row.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise Sub2APIError("CONTRACT_MISMATCH", f"{context} is missing non-negative {field}")
    return value


def _zone(name: str):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise Sub2APIError("INVALID_TIMEZONE", f"unknown timezone: {_safe_text(name)}", 500) from exc


def _range_params(start: int, end: int, cfg: Sub2APIConfig) -> dict[str, str]:
    tz = _zone(cfg.timezone_name)
    return {
        "start_date": datetime.fromtimestamp(start, tz).date().isoformat(),
        "end_date": datetime.fromtimestamp(max(start, end - 1), tz).date().isoformat(),
        "timezone": cfg.timezone_name,
    }


def _timestamp(value, cfg: Sub2APIConfig) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    normalized = text.replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_zone(cfg.timezone_name))
    return int(parsed.timestamp())


class Sub2APIClient:
    def __init__(self, cfg: Sub2APIConfig):
        self.cfg = cfg

    def _request(self, method: str, path: str, *, params=None, body=None):
        query = urllib.parse.urlencode(params or {}, doseq=True)
        url = f"{self.cfg.base_url}{path}{'?' + query if query else ''}"
        raw_body = json.dumps(body).encode() if body is not None else None
        headers = {"Accept": "application/json"}
        if self.cfg.admin_key:
            headers["x-api-key"] = self.cfg.admin_key
        elif self.cfg.access_token:
            token = self.cfg.access_token
            headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
            headers["X-Admin-UI-Request"] = "1"
        if raw_body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=raw_body, headers=headers, method=method)
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=self.cfg.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                code = "AUTH_FAILED" if exc.code in {401, 403} else "ENDPOINT_MISSING" if exc.code == 404 else "UPSTREAM_HTTP_ERROR"
                if attempt == 0 and exc.code >= 500:
                    time.sleep(0.15)
                    continue
                raise Sub2APIError(code, f"Sub2API returned HTTP {exc.code}") from exc
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                if attempt == 0:
                    time.sleep(0.15)
                    continue
                raise Sub2APIError("UPSTREAM_UNAVAILABLE", _safe_text(exc)) from exc
        if not isinstance(payload, dict) or payload.get("code") != 0 or "data" not in payload:
            message = payload.get("message") if isinstance(payload, dict) else "invalid JSON envelope"
            raise Sub2APIError("CONTRACT_MISMATCH", _safe_text(message or "invalid Sub2API response envelope"))
        return payload["data"]

    def version(self) -> str:
        data = self._request("GET", "/api/v1/admin/system/version")
        if not isinstance(data, dict) or not isinstance(data.get("version"), str):
            raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API version response is missing version")
        return data["version"]

    def list_keys(self) -> list[dict]:
        items = []
        page = 1
        while True:
            data = self._request(
                "GET", f"/api/v1/admin/users/{self.cfg.user_id}/api-keys",
                params={"page": page, "page_size": 1000},
            )
            if isinstance(data, list):
                page_items, pages = data, 1
            elif isinstance(data, dict) and isinstance(data.get("items"), list):
                page_items, pages = data["items"], int(data.get("pages") or 1)
            else:
                raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API API key list has invalid data")
            for raw in page_items:
                if not isinstance(raw, dict) or _number(raw.get("id")) <= 0:
                    raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API API key is missing id")
                if not isinstance(raw.get("name"), str):
                    raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API API key is missing name")
                _required_number(raw, "quota", "Sub2API API key")
                _required_number(raw, "quota_used", "Sub2API API key")
                item = {key: value for key, value in raw.items() if key != "key"}
                items.append(item)
            if page >= pages:
                return items
            page += 1

    def key_trend(self, start: int, end: int, granularity: str) -> list[dict]:
        params = _range_params(start, end, self.cfg)
        params.update({"granularity": "hour" if granularity in {"hour", "four_hour"} else "day", "limit": 100})
        data = self._request("GET", "/api/v1/admin/dashboard/api-keys-trend", params=params)
        rows = data.get("trend") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API API key trend is missing trend")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("date"), str) or _number(row.get("api_key_id")) <= 0:
                raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API API key trend has invalid identity")
            if not isinstance(row.get("key_name"), str):
                raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API API key trend is missing key_name")
            _required_number(row, "requests", "Sub2API API key trend")
            _required_number(row, "tokens", "Sub2API API key trend")
        return rows

    def key_snapshot(self, key_id: int, start: int, end: int, granularity: str) -> dict:
        params = _range_params(start, end, self.cfg)
        params.update({
            "api_key_id": key_id,
            "granularity": "hour" if granularity in {"hour", "four_hour"} else "day",
            "include_stats": "false",
            "include_trend": "true",
            "include_model_stats": "true",
            "include_group_stats": "false",
            "include_users_trend": "false",
        })
        data = self._request("GET", "/api/v1/admin/dashboard/snapshot-v2", params=params)
        if not isinstance(data, dict):
            raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API snapshot is missing trend or models")
        has_valid_range = isinstance(data.get("start_date"), str) and isinstance(data.get("end_date"), str)
        for field in ("trend", "models"):
            if data.get(field) is None and has_valid_range:
                data[field] = []
            if not isinstance(data.get(field), list):
                raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API snapshot is missing trend or models")
        for row in data["trend"]:
            if not isinstance(row, dict) or not isinstance(row.get("date"), str):
                raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API snapshot trend has invalid date")
            for field in ("requests", "input_tokens", "output_tokens", "total_tokens", "actual_cost"):
                _required_number(row, field, "Sub2API snapshot trend")
        for row in data["models"]:
            if not isinstance(row, dict) or not isinstance(row.get("model"), str) or not row["model"]:
                raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API snapshot model is missing model")
            for field in ("requests", "total_tokens", "actual_cost"):
                _required_number(row, field, "Sub2API snapshot model")
        return data

    def key_stats(self, key_id: int, start: int, end: int) -> dict:
        params = _range_params(start, end, self.cfg)
        params["api_key_id"] = key_id
        data = self._request("GET", "/api/v1/admin/usage/stats", params=params)
        if not isinstance(data, dict) or "average_duration_ms" not in data:
            raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API usage stats is missing average_duration_ms")
        _required_number(data, "average_duration_ms", "Sub2API usage stats")
        return data

    def errors_page(self, start: int, end: int, page: int, page_size: int, key_id: int | None = None) -> dict:
        params = {
            "start_time": datetime.fromtimestamp(start, timezone.utc).isoformat(),
            "end_time": datetime.fromtimestamp(end, timezone.utc).isoformat(),
            "page": page,
            "page_size": page_size,
            "view": "errors",
        }
        if key_id:
            params["api_key_id"] = key_id
        data = self._request("GET", "/api/v1/admin/ops/errors", params=params)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise Sub2APIError("CONTRACT_MISMATCH", "Sub2API errors response is missing items")
        for field in ("total", "page", "page_size", "pages"):
            _required_number(data, field, "Sub2API errors response")
        return data


def _legacy_quota(usd) -> float | None:
    if usd is None:
        return None
    return round(float(usd) * _LEGACY_QUOTA_PER_USD, 6)


def _key_meta(raw: dict) -> dict:
    group = raw.get("group") if isinstance(raw.get("group"), dict) else {}
    historical_only = bool(raw.get("_historical_only"))
    limit = None if historical_only else float(raw.get("quota") or 0)
    used = None if historical_only else float(raw.get("quota_used") or 0)
    return {
        "api_key_id": int(raw["id"]),
        "api_key_name": str(raw.get("name") or f"#{raw['id']}"),
        "user_id": int(raw.get("user_id") or 0),
        "status_text": str(raw.get("status") or "inactive"),
        "group": str(group.get("name") or ""),
        "quota_limit_usd": limit,
        "quota_used_lifetime_usd": used,
        "quota_remaining_usd": None if limit is None or limit <= 0 else max(0.0, limit - used),
        "unlimited_quota": None if limit is None else limit <= 0,
        "created_at": raw.get("created_at"),
        "last_used_at_raw": raw.get("last_used_at"),
        "expires_at": raw.get("expires_at"),
    }


def _discovered_keys(rows: list[dict]) -> dict[int, dict]:
    found = {}
    for row in rows:
        key_id = int(_number(row.get("api_key_id"))) if isinstance(row, dict) else 0
        if key_id > 0:
            found[key_id] = {
                "id": key_id,
                "name": str(row.get("key_name") or f"#{key_id}"),
                "user_id": 0,
                "status": "historical",
                "quota": 0,
                "quota_used": 0,
                "_historical_only": True,
            }
    return found


def _normalize_snapshot(key: dict, snapshot: dict, cfg: Sub2APIConfig):
    meta = _key_meta(key)
    key_id, key_name = meta["api_key_id"], meta["api_key_name"]
    trend = []
    totals = {"requests": 0, "input": 0, "output": 0, "tokens": 0, "cost": 0.0}
    for raw in snapshot.get("trend") or []:
        if not isinstance(raw, dict):
            continue
        point = {
            "api_key_id": key_id,
            "api_key_name": key_name,
            "created_at": _timestamp(raw.get("date"), cfg),
            "request_count": int(_number(raw.get("requests"))),
            "error_count": 0,
            "actual_cost_usd": float(raw.get("actual_cost") or 0),
            "input_tokens": int(_number(raw.get("input_tokens"))),
            "output_tokens": int(_number(raw.get("output_tokens"))),
            "total_tokens": int(_number(raw.get("total_tokens"))),
        }
        point.update({
            "token_id": key_id, "token_name": key_name, "count": point["request_count"],
            "quota": _legacy_quota(point["actual_cost_usd"]), "token_used": point["total_tokens"],
        })
        trend.append(point)
        totals["requests"] += point["request_count"]
        totals["input"] += point["input_tokens"]
        totals["output"] += point["output_tokens"]
        totals["tokens"] += point["total_tokens"]
        totals["cost"] += point["actual_cost_usd"]
    models = []
    for raw in snapshot.get("models") or []:
        if not isinstance(raw, dict) or not raw.get("model"):
            continue
        item = {
            "api_key_id": key_id,
            "api_key_name": key_name,
            "model_name": str(raw["model"]),
            "request_count": int(_number(raw.get("requests"))),
            "actual_cost_usd": float(raw.get("actual_cost") or 0),
            "total_tokens": int(_number(raw.get("total_tokens"))),
        }
        item.update({
            "token_id": key_id, "token_name": key_name, "count": item["request_count"],
            "quota": _legacy_quota(item["actual_cost_usd"]), "token_used": item["total_tokens"],
        })
        models.append(item)
    top_model = max(models, key=lambda row: row["actual_cost_usd"], default={}).get("model_name", "")
    return meta, trend, models, totals, top_model


def _normalize_error(raw: dict, cfg: Sub2APIConfig) -> dict:
    key_id = int(_number(raw.get("api_key_id")))
    key_name = str(raw.get("api_key_name") or "")
    return {
        "id": int(_number(raw.get("id"))),
        "created_at": _timestamp(raw.get("created_at"), cfg),
        "api_key_id": key_id,
        "api_key_name": key_name,
        "token_id": key_id,
        "token_name": key_name,
        "user_id": int(_number(raw.get("user_id"))),
        "group": str(raw.get("group_name") or ""),
        "model_name": str(raw.get("requested_model") or raw.get("model") or ""),
        "content": _safe_text(raw.get("message")),
        "request_id": str(raw.get("request_id") or raw.get("client_request_id") or ""),
        "upstream_request_id": "",
        "status_code": int(_number(raw.get("status_code"))),
        "error_type": str(raw.get("type") or ""),
        "error_code": str(raw.get("phase") or ""),
        "request_path": str(raw.get("request_path") or ""),
        "is_stream": bool(raw.get("stream")),
    }


def _all_errors(client: Sub2APIClient, start: int, end: int, key_ids: list[int]):
    first = client.errors_page(start, end, 1, _ERROR_PAGE_SIZE)
    total = int(first.get("total") or len(first["items"]))
    if total > _ERROR_BULK_LIMIT:
        def count_for_key(key_id):
            return key_id, int(client.errors_page(start, end, 1, 1, key_id).get("total") or 0)

        counts = {}
        with ThreadPoolExecutor(max_workers=client.cfg.max_concurrency) as pool:
            for key_id, count in pool.map(count_for_key, key_ids):
                counts[key_id] = count
        return counts, []
    rows = list(first["items"])
    pages = int(first.get("pages") or ((total + _ERROR_PAGE_SIZE - 1) // _ERROR_PAGE_SIZE) or 1)
    for page in range(2, pages + 1):
        rows.extend(client.errors_page(start, end, page, _ERROR_PAGE_SIZE)["items"])
    counts = {}
    normalized = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        item = _normalize_error(raw, client.cfg)
        normalized.append(item)
        counts[item["api_key_id"]] = counts.get(item["api_key_id"], 0) + 1
    return counts, normalized


def _core_window(keys: dict[int, dict], rows: list[dict], cfg: Sub2APIConfig) -> dict:
    trend = []
    totals: dict[int, dict[str, int]] = {
        key_id: {"requests": 0, "tokens": 0} for key_id in keys
    }
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        key_id = int(_number(raw.get("api_key_id")))
        if key_id not in keys:
            continue
        key_name = str(raw.get("key_name") or keys[key_id].get("name") or f"#{key_id}")
        requests = int(_number(raw.get("requests")))
        tokens = int(_number(raw.get("tokens")))
        trend.append({
            "api_key_id": key_id,
            "api_key_name": key_name,
            "created_at": _timestamp(raw.get("date"), cfg),
            "request_count": requests,
            "error_count": None,
            "actual_cost_usd": None,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": tokens,
            "token_id": key_id,
            "token_name": key_name,
            "count": requests,
            "quota": None,
            "token_used": tokens,
        })
        totals[key_id]["requests"] += requests
        totals[key_id]["tokens"] += tokens

    summary = []
    for key_id, key in keys.items():
        meta = _key_meta(key)
        known = totals[key_id]
        row = {
            **meta,
            "request_count": known["requests"],
            "error_count": None,
            "actual_cost_usd": None,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": known["tokens"],
            "average_duration_ms": None,
            "top_model": None,
            "model_count": None,
            "token_id": key_id,
            "token_name": meta["api_key_name"],
            "status": 1 if meta["status_text"] == "active" else 2,
            "remain_quota": _legacy_quota(meta["quota_remaining_usd"]),
            "used_quota": _legacy_quota(meta["quota_used_lifetime_usd"]),
            "quota": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "token_used": known["tokens"],
            "avg_use_time": None,
            "last_used_at": _timestamp(meta["last_used_at_raw"], cfg),
        }
        summary.append(row)
    return {"summary": summary, "trend": trend, "models": []}


def _build_window(
    client: Sub2APIClient,
    keys: dict[int, dict],
    start: int,
    end: int,
    granularity: str,
    include_latency: bool,
    core: dict,
):
    summary, trends, models, warnings = [], [], [], []
    core_rows = {row["api_key_id"]: row for row in core["summary"]}
    core_trends: dict[int, list[dict]] = {}
    for point in core["trend"]:
        core_trends.setdefault(point["api_key_id"], []).append(point)

    def load(key):
        key_id = int(key["id"])
        snapshot = client.key_snapshot(key_id, start, end, granularity)
        meta, trend, model_rows, totals, top_model = _normalize_snapshot(key, snapshot, client.cfg)
        latency = None
        if include_latency:
            latency = float(client.key_stats(key_id, start, end)["average_duration_ms"])
        return meta, trend, model_rows, totals, top_model, latency

    with ThreadPoolExecutor(max_workers=client.cfg.max_concurrency) as pool:
        future_keys = {pool.submit(load, key): key_id for key_id, key in keys.items()}
        for future in as_completed(future_keys):
            key_id = future_keys[future]
            try:
                meta, trend, model_rows, totals, top_model, latency = future.result()
            except Exception as exc:
                warnings.append({"api_key_id": key_id, "code": getattr(exc, "code", "KEY_ENRICHMENT_FAILED")})
                summary.append(deepcopy(core_rows[key_id]))
                trends.extend(deepcopy(core_trends.get(key_id, [])))
                continue
            row = {
                **meta,
                "request_count": totals["requests"],
                "error_count": 0,
                "actual_cost_usd": round(totals["cost"], 12),
                "input_tokens": totals["input"],
                "output_tokens": totals["output"],
                "total_tokens": totals["tokens"],
                "average_duration_ms": latency,
                "top_model": top_model,
                "model_count": len(model_rows),
            }
            row.update({
                "token_id": meta["api_key_id"], "token_name": meta["api_key_name"],
                "status": 1 if meta["status_text"] == "active" else 2,
                "remain_quota": None if meta["quota_remaining_usd"] is None else _legacy_quota(meta["quota_remaining_usd"]),
                "used_quota": _legacy_quota(meta["quota_used_lifetime_usd"]),
                "quota": _legacy_quota(row["actual_cost_usd"]),
                "prompt_tokens": row["input_tokens"], "completion_tokens": row["output_tokens"],
                "token_used": row["total_tokens"],
                "avg_use_time": None if latency is None else latency / 1000,
                "last_used_at": _timestamp(meta["last_used_at_raw"], client.cfg),
            })
            summary.append(row)
            trends.extend(trend)
            models.extend(model_rows)
    return {"summary": summary, "trend": trends, "models": models}, warnings


def _cache_load(key: tuple, ttl: float, loader):
    now = time.time()
    owner = False
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry and now - entry.stored_at <= ttl:
            return deepcopy(entry.payload), True, False
        event = _INFLIGHT.get(key)
        if event is None:
            event = threading.Event()
            _INFLIGHT[key] = event
            owner = True
    if not owner:
        event.wait(120)
        with _CACHE_LOCK:
            entry = _CACHE.get(key)
            if entry:
                return deepcopy(entry.payload), True, now - entry.stored_at > ttl
        raise Sub2APIError("REFRESH_FAILED", "Sub2API refresh failed")
    try:
        payload = loader()
        with _CACHE_LOCK:
            _CACHE[key] = _CacheEntry(time.time(), deepcopy(payload))
        return payload, False, False
    except Exception as exc:
        _mark_status(error_code=getattr(exc, "code", "UPSTREAM_FAILED"))
        with _CACHE_LOCK:
            entry = _CACHE.get(key)
        if entry and now - entry.stored_at <= _STALE_TTL:
            return deepcopy(entry.payload), True, True
        raise
    finally:
        with _CACHE_LOCK:
            _INFLIGHT.pop(key, None)
            event.set()


def _mark_status(*, version=None, success=False, error_code="", capabilities=None):
    with _STATUS_LOCK:
        if version is not None:
            _STATUS["upstream_version"] = version
        if capabilities is not None:
            _STATUS["capabilities"] = capabilities
        if success:
            _STATUS["last_success_at"] = _utc_iso()
            _STATUS["last_error_code"] = ""
        if error_code:
            _STATUS["last_error_code"] = error_code
            _STATUS["last_error_at"] = _utc_iso()


def _full_payload(client: Sub2APIClient, context: dict) -> dict:
    keys = context["keys"]
    current, current_warnings = _build_window(
        client,
        keys,
        context["start"],
        context["end"],
        context["granularity"],
        True,
        context["current_core"],
    )
    error_counts, _ = _all_errors(client, context["start"], context["end"], list(keys))
    for row in current["summary"]:
        row["error_count"] = error_counts.get(row["api_key_id"], 0)

    comparison = None
    warnings = list(current_warnings)
    if context["comparison_start"] and context["comparison_end"]:
        previous, previous_warnings = _build_window(
            client,
            keys,
            context["comparison_start"],
            context["comparison_end"],
            context["granularity"],
            False,
            context["previous_core"],
        )
        previous_error_counts, _ = _all_errors(
            client,
            context["comparison_start"],
            context["comparison_end"],
            list(keys),
        )
        for row in previous["summary"]:
            row["error_count"] = previous_error_counts.get(row["api_key_id"], 0)
        comparison = {
            "data": previous,
            "range": {
                "start_timestamp": context["comparison_start"],
                "end_timestamp": context["comparison_end"],
                "time_granularity": context["granularity"],
            },
        }
        warnings.extend(previous_warnings)
    return {
        "schema_version": SCHEMA_VERSION,
        "data": current,
        "comparison": comparison,
        "upstream_version": context["version"],
        "completeness": "complete" if not warnings else "partial",
        "warnings": warnings,
    }


def _start_enrichment(cache_key: tuple, cfg: Sub2APIConfig) -> None:
    with _CACHE_LOCK:
        if cache_key in _ENRICHING or cache_key not in _ENRICHMENT_CONTEXT:
            return
        _ENRICHING.add(cache_key)
        context = deepcopy(_ENRICHMENT_CONTEXT[cache_key])

    def enrich():
        try:
            payload = _full_payload(Sub2APIClient(cfg), context)
            with _CACHE_LOCK:
                _CACHE[cache_key] = _CacheEntry(time.time(), deepcopy(payload))
                _ENRICHMENT_CONTEXT.pop(cache_key, None)
            _mark_status(
                success=True,
                capabilities={
                    "inventory": True,
                    "api_keys_trend": True,
                    "snapshot_v2": True,
                    "usage_stats": True,
                    "ops_errors": True,
                },
            )
        except Exception as exc:  # pragma: no cover - exercised through observable cache state
            code = getattr(exc, "code", "ENRICHMENT_FAILED")
            with _CACHE_LOCK:
                entry = _CACHE.get(cache_key)
                if entry:
                    warnings = [item for item in entry.payload.setdefault("warnings", []) if item.get("code") != "DETAILS_SYNCING"]
                    if not any(item.get("code") == code for item in warnings):
                        warnings.append({"code": code})
                    entry.payload["warnings"] = warnings
            _mark_status(error_code=code)
        finally:
            with _CACHE_LOCK:
                _ENRICHING.discard(cache_key)

    threading.Thread(target=enrich, name="sub2api-token-usage-enrichment", daemon=True).start()


def get_usage(cfg: Sub2APIConfig, start: int, end: int, granularity: str, comparison_start: int | None = None, comparison_end: int | None = None):
    if not cfg.configured:
        raise Sub2APIError("NOT_CONFIGURED", "Sub2API Token Usage credentials are not configured", 503)
    now = int(time.time())
    ttl = _LIVE_TTL if end >= now - 300 else _HISTORY_TTL
    key = (
        "usage", cfg.base_url, cfg.auth_mode, cfg.user_id, cfg.timezone_name,
        start, end, granularity, comparison_start, comparison_end,
    )

    def load_core():
        client = Sub2APIClient(cfg)
        version = client.version()
        inventory = client.list_keys()
        current_discovery = client.key_trend(start, end, granularity)
        previous_discovery = client.key_trend(comparison_start, comparison_end, granularity) if comparison_start and comparison_end else []
        keys = {int(raw["id"]): raw for raw in inventory}
        for key_id, raw in {**_discovered_keys(current_discovery), **_discovered_keys(previous_discovery)}.items():
            keys.setdefault(key_id, raw)
        current = _core_window(keys, current_discovery, cfg)
        comparison = None
        if comparison_start and comparison_end:
            previous = _core_window(keys, previous_discovery, cfg)
            comparison = {
                "data": previous,
                "range": {"start_timestamp": comparison_start, "end_timestamp": comparison_end, "time_granularity": granularity},
            }
        context = {
            "version": version,
            "keys": keys,
            "start": start,
            "end": end,
            "granularity": granularity,
            "comparison_start": comparison_start,
            "comparison_end": comparison_end,
            "current_core": current,
            "previous_core": comparison["data"] if comparison else None,
        }
        with _CACHE_LOCK:
            _ENRICHMENT_CONTEXT[key] = deepcopy(context)
        capabilities = {"inventory": True, "api_keys_trend": True, "snapshot_v2": False, "usage_stats": False, "ops_errors": False}
        _mark_status(version=version, success=True, capabilities=capabilities)
        return {
            "schema_version": SCHEMA_VERSION,
            "data": current,
            "comparison": comparison,
            "upstream_version": version,
            "completeness": "partial",
            "warnings": [{"code": "DETAILS_SYNCING"}],
        }

    try:
        payload, cached, stale = _cache_load(key, ttl, load_core)
    except Exception as exc:
        _mark_status(error_code=getattr(exc, "code", "UPSTREAM_FAILED"))
        raise
    if payload.get("completeness") == "partial" and not stale:
        _start_enrichment(key, cfg)
    payload["cached"] = cached
    payload["freshness"] = "stale" if stale else "cached" if cached else "fresh"
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        payload["cache_age_seconds"] = 0 if not entry else max(0, int(time.time() - entry.stored_at))
    if stale:
        payload["completeness"] = "stale"
        payload.setdefault("warnings", []).append({"code": "STALE_IF_ERROR"})
    return payload


def get_errors(cfg: Sub2APIConfig, start: int, end: int, key_id: int | None, page_size: int):
    if not cfg.configured:
        raise Sub2APIError("NOT_CONFIGURED", "Sub2API Token Usage credentials are not configured", 503)
    ttl = _LIVE_TTL if end >= int(time.time()) - 300 else _HISTORY_TTL
    cache_key = (
        "errors", cfg.base_url, cfg.auth_mode, cfg.user_id, cfg.timezone_name,
        start, end, key_id, page_size,
    )

    def load():
        client = Sub2APIClient(cfg)
        data = client.errors_page(start, end, 1, min(page_size, 100), key_id)
        items = [_normalize_error(raw, cfg) for raw in data["items"] if isinstance(raw, dict)]
        return {
            "items": items,
            "total": int(data.get("total") or len(items)),
            "page": int(data.get("page") or 1),
            "page_size": int(data.get("page_size") or page_size),
        }

    payload, cached, stale = _cache_load(cache_key, ttl, load)
    payload["cached"] = cached
    payload["freshness"] = "stale" if stale else "cached" if cached else "fresh"
    return payload


def status_payload(cfg: Sub2APIConfig) -> dict:
    with _STATUS_LOCK:
        status = deepcopy(_STATUS)
    newest = 0.0
    with _CACHE_LOCK:
        for entry in _CACHE.values():
            newest = max(newest, entry.stored_at)
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": "sub2api",
        "configured": cfg.configured,
        "auth_mode": cfg.auth_mode,
        "upstream_version": status["upstream_version"],
        "capabilities": status["capabilities"],
        "last_success_at": status["last_success_at"],
        "last_error_code": status["last_error_code"],
        "last_error_at": status["last_error_at"],
        "cache_age_seconds": None if not newest else max(0, int(time.time() - newest)),
    }
