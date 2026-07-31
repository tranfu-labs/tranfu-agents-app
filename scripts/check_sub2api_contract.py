#!/usr/bin/env python3
"""Read-only release gate for the Sub2API Token Usage contract."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class ContractError(RuntimeError):
    pass


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _number(value, field: str) -> float:
    _expect(isinstance(value, (int, float)) and not isinstance(value, bool), f"{field} must be numeric")
    _expect(value >= 0, f"{field} must be non-negative")
    return float(value)


class Checker:
    def __init__(self, base_url: str, admin_key: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key
        self.timeout = timeout

    def request(self, path: str, params=None, *, envelope=True):
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base_url}{path}{'?' + query if query else ''}"
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "x-api-key": self.admin_key},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ContractError(f"{path} returned HTTP {exc.code}") from None
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ContractError(f"{path} could not be read as JSON: {type(exc).__name__}") from None
        _expect(isinstance(payload, dict), f"{path} must return an object")
        if not envelope:
            return payload
        _expect(payload.get("code") == 0, f"{path} envelope code must equal 0")
        _expect("data" in payload, f"{path} envelope must contain data")
        return payload["data"]


def _check_paginated(data, path: str) -> list[dict]:
    _expect(isinstance(data, dict), f"{path} data must be an object")
    _expect(isinstance(data.get("items"), list), f"{path}.items must be an array")
    for field in ("total", "page", "page_size", "pages"):
        _number(data.get(field), f"{path}.{field}")
    return data["items"]


def _check_trend(rows, path: str, *, key_id: int | None = None) -> None:
    _expect(isinstance(rows, list), f"{path} must be an array")
    for index, row in enumerate(rows):
        prefix = f"{path}[{index}]"
        _expect(isinstance(row, dict), f"{prefix} must be an object")
        _expect(isinstance(row.get("date"), str) and row["date"], f"{prefix}.date must be a string")
        if key_id is None:
            _expect(isinstance(row.get("api_key_id"), int) and row["api_key_id"] > 0, f"{prefix}.api_key_id must be positive")
            _expect(isinstance(row.get("key_name"), str), f"{prefix}.key_name must be a string")
            _number(row.get("tokens"), f"{prefix}.tokens")
        _number(row.get("requests"), f"{prefix}.requests")


def check_contract(args) -> dict:
    checker = Checker(args.base_url, args.admin_key, args.timeout)
    health = checker.request("/health", envelope=False)
    _expect(health.get("status") == "ok", "/health status must equal ok")

    version_data = checker.request("/api/v1/admin/system/version")
    _expect(isinstance(version_data, dict), "version data must be an object")
    version = version_data.get("version")
    _expect(isinstance(version, str) and version, "version must be a non-empty string")

    all_keys = []
    page = 1
    while True:
        path = f"/api/v1/admin/users/{args.user_id}/api-keys"
        data = checker.request(path, {"page": page, "page_size": 100})
        items = _check_paginated(data, path)
        for index, raw in enumerate(items):
            prefix = f"{path}.items[{index}]"
            _expect(isinstance(raw, dict), f"{prefix} must be an object")
            _expect(isinstance(raw.get("id"), int) and raw["id"] > 0, f"{prefix}.id must be positive")
            _expect(isinstance(raw.get("name"), str), f"{prefix}.name must be a string")
            _number(raw.get("quota"), f"{prefix}.quota")
            _number(raw.get("quota_used"), f"{prefix}.quota_used")
            all_keys.append({key: value for key, value in raw.items() if key != "key"})
        if page >= data["pages"]:
            break
        page += 1

    if not all_keys:
        _expect(args.allow_empty_keys, "API key inventory is empty; per-key contract cannot be verified")
        return {"version": version, "key_count": 0, "checked_key_id": None}

    key_id = args.api_key_id or all_keys[0]["id"]
    _expect(any(item["id"] == key_id for item in all_keys), "selected api_key_id is not in the configured user's inventory")
    range_params = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "timezone": args.timezone,
    }

    trend_data = checker.request(
        "/api/v1/admin/dashboard/api-keys-trend",
        {**range_params, "granularity": "day", "limit": 100},
    )
    _expect(isinstance(trend_data, dict), "api-keys-trend data must be an object")
    _expect(trend_data.get("start_date") == args.start_date, "api-keys-trend start_date does not match the requested range")
    _expect(trend_data.get("end_date") == args.end_date, "api-keys-trend end_date does not match the requested range")
    _check_trend(trend_data.get("trend"), "api-keys-trend.trend")

    snapshot = checker.request(
        "/api/v1/admin/dashboard/snapshot-v2",
        {
            **range_params,
            "api_key_id": key_id,
            "granularity": "day",
            "include_stats": "false",
            "include_trend": "true",
            "include_model_stats": "true",
            "include_group_stats": "false",
            "include_users_trend": "false",
        },
    )
    _expect(isinstance(snapshot, dict), "snapshot-v2 data must be an object")
    _expect(snapshot.get("start_date") == args.start_date, "snapshot-v2 start_date does not match the requested range")
    _expect(snapshot.get("end_date") == args.end_date, "snapshot-v2 end_date does not match the requested range")
    snapshot_has_valid_range = isinstance(snapshot.get("start_date"), str) and isinstance(snapshot.get("end_date"), str)
    snapshot_trend = snapshot.get("trend")
    models = snapshot.get("models")
    if snapshot_trend is None and snapshot_has_valid_range:
        snapshot_trend = []
    if models is None and snapshot_has_valid_range:
        models = []
    _check_trend(snapshot_trend, "snapshot-v2.trend", key_id=key_id)
    _expect(isinstance(models, list), "snapshot-v2.models must be an array")
    for index, row in enumerate(models):
        prefix = f"snapshot-v2.models[{index}]"
        _expect(isinstance(row, dict), f"{prefix} must be an object")
        _expect(isinstance(row.get("model"), str) and row["model"], f"{prefix}.model must be a non-empty string")
        for field in ("requests", "total_tokens", "actual_cost"):
            _number(row.get(field), f"{prefix}.{field}")

    stats = checker.request("/api/v1/admin/usage/stats", {**range_params, "api_key_id": key_id})
    _expect(isinstance(stats, dict), "usage/stats data must be an object")
    for field in (
        "total_requests",
        "total_input_tokens",
        "total_output_tokens",
        "total_tokens",
        "total_actual_cost",
        "average_duration_ms",
    ):
        _number(stats.get(field), f"usage/stats.{field}")

    errors_path = "/api/v1/admin/ops/errors"
    timezone = ZoneInfo(args.timezone)
    error_start = datetime.fromisoformat(args.start_date).replace(tzinfo=timezone).isoformat()
    error_end = datetime.fromisoformat(args.end_date).replace(hour=23, minute=59, second=59, tzinfo=timezone).isoformat()
    error_params = {
        "start_time": error_start,
        "end_time": error_end,
        "page": 1,
        "page_size": 1,
        "view": "errors",
        "api_key_id": key_id,
    }
    errors = checker.request(errors_path, error_params)
    error_items = _check_paginated(errors, errors_path)
    for item in error_items:
        _expect(item.get("api_key_id") == key_id, "ops/errors api_key_id filter returned a different key")
    if errors["pages"] > 1:
        second = checker.request(errors_path, {**error_params, "page": 2})
        _check_paginated(second, errors_path)
        _expect(second["page"] == 2, "ops/errors pagination did not advance to page 2")

    return {"version": version, "key_count": len(all_keys), "checked_key_id": key_id}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("TF_TOKEN_USAGE_BASE_URL", ""))
    parser.add_argument("--admin-key", default=os.environ.get("TF_TOKEN_USAGE_SUB2API_ADMIN_KEY", ""))
    parser.add_argument("--user-id", type=int, default=int(os.environ.get("TF_TOKEN_USAGE_SUB2API_USER_ID", "1")))
    parser.add_argument("--api-key-id", type=int)
    parser.add_argument("--timezone", default=os.environ.get("TF_TOKEN_USAGE_TIMEZONE", "Asia/Shanghai"))
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--allow-empty-keys", action="store_true")
    args = parser.parse_args()
    _expect(bool(args.base_url), "base URL is required")
    _expect(bool(args.admin_key), "admin key is required")
    _expect(args.user_id > 0, "user ID must be positive")
    today = datetime.now(ZoneInfo(args.timezone)).date()
    args.end_date = args.end_date or today.isoformat()
    args.start_date = args.start_date or (today - timedelta(days=1)).isoformat()
    _expect(args.start_date <= args.end_date, "start date must not be after end date")
    return args


def main() -> int:
    try:
        result = check_contract(parse_args())
    except ContractError as exc:
        print(f"Sub2API contract check failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
