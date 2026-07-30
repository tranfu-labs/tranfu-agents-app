import json
import io
import threading
import time
import urllib.error

import pytest

from server import token_usage_sub2api as sub2


@pytest.fixture(autouse=True)
def clean_sub2(monkeypatch):
    sub2.clear_caches()
    monkeypatch.delenv("TF_TOKEN_USAGE_SUB2API_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("TF_TOKEN_USAGE_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("TF_TOKEN_USAGE_PROVIDER", "sub2api")
    monkeypatch.setenv("TF_TOKEN_USAGE_BASE_URL", "https://sub2.test")
    monkeypatch.setenv("TF_TOKEN_USAGE_SUB2API_ADMIN_KEY", "admin-secret-value")
    monkeypatch.setenv("TF_TOKEN_USAGE_SUB2API_USER_ID", "1")
    monkeypatch.setenv("TF_TOKEN_USAGE_TIMEZONE", "Asia/Shanghai")
    monkeypatch.setenv("TF_TOKEN_USAGE_MAX_CONCURRENCY", "2")


def _fake_request(self, method, path, params=None, body=None):
    if path.endswith("/system/version"):
        return {"version": "v0.1.166"}
    if path.endswith("/api-keys"):
        return {
            "items": [{
                "id": 7, "user_id": 1, "key": "sk-must-not-leak", "name": "Dapp-key",
                "status": "active", "quota": 10, "quota_used": 2,
                "created_at": "2026-07-01T00:00:00Z", "last_used_at": "2026-07-30T00:00:00Z",
                "expires_at": None, "group": {"name": "Dapp"},
            }],
            "page": 1, "pages": 1,
        }
    if path.endswith("/api-keys-trend"):
        return {"trend": [{"date": "2026-07-30 00:00", "api_key_id": 7, "key_name": "Dapp-key", "requests": 2, "tokens": 30}]}
    if path.endswith("/snapshot-v2"):
        return {
            "trend": [{
                "date": "2026-07-30 00:00", "requests": 2, "input_tokens": 10,
                "output_tokens": 20, "total_tokens": 30, "actual_cost": 0.25,
            }],
            "models": [{"model": "gpt-5", "requests": 2, "total_tokens": 30, "actual_cost": 0.25}],
        }
    if path.endswith("/usage/stats"):
        return {"average_duration_ms": 1250}
    if path.endswith("/ops/errors"):
        return {
            "items": [{
                "id": 9, "created_at": "2026-07-30T01:00:00Z", "api_key_id": 7,
                "api_key_name": "Dapp-key", "status_code": 429, "message": "rate limited",
                "type": "rate_limit", "phase": "upstream", "requested_model": "gpt-5",
                "request_id": "req-1", "group_name": "Dapp",
            }],
            "total": 1, "page": 1, "page_size": 500, "pages": 1,
        }
    raise AssertionError((method, path, params, body))


def _wait_for_enrichment(timeout=1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with sub2._CACHE_LOCK:
            if not sub2._ENRICHING:
                return
        time.sleep(0.005)
    raise AssertionError("background enrichment did not finish")


def test_sub2api_route_returns_schema_v2_and_never_leaks_keys(client, monkeypatch):
    monkeypatch.setattr(sub2.Sub2APIClient, "_request", _fake_request)
    response = client.get(
        "/api/token-usage?start_timestamp=1785340800&end_timestamp=1785427200"
        "&comparison_start_timestamp=1785254400&comparison_end_timestamp=1785340800"
    )
    assert response.status_code == 200
    body = response.json()
    row = body["data"]["summary"][0]
    assert body["schema_version"] == 2
    assert body["source"] == "sub2api"
    assert body["comparison"]["data"]["summary"]
    assert row["api_key_id"] == 7
    assert body["completeness"] == "partial"
    assert row["actual_cost_usd"] is None
    assert row["average_duration_ms"] is None
    assert row["error_count"] is None
    assert row["request_count"] == 2
    assert row["total_tokens"] == 30
    assert "sk-must-not-leak" not in response.text
    assert "admin-secret-value" not in response.text

    _wait_for_enrichment()
    response = client.get(
        "/api/token-usage?start_timestamp=1785340800&end_timestamp=1785427200"
        "&comparison_start_timestamp=1785254400&comparison_end_timestamp=1785340800"
    )
    body = response.json()
    row = body["data"]["summary"][0]
    assert body["completeness"] == "complete"
    assert row["actual_cost_usd"] == pytest.approx(0.25)
    assert row["average_duration_ms"] == 1250
    assert row["error_count"] == 1
    assert row["quota"] == 125000
    assert "sk-must-not-leak" not in response.text
    assert "admin-secret-value" not in response.text


def test_failed_key_enrichment_keeps_core_values_and_unknown_details(client, monkeypatch):
    def fake(self, method, path, params=None, body=None):
        if path.endswith("/snapshot-v2"):
            raise sub2.Sub2APIError("UPSTREAM_HTTP_ERROR", "failed")
        return _fake_request(self, method, path, params, body)

    monkeypatch.setattr(sub2.Sub2APIClient, "_request", fake)
    first = client.get("/api/token-usage?start_timestamp=1785340800&end_timestamp=1785427200")
    assert first.status_code == 200
    _wait_for_enrichment()
    body = client.get("/api/token-usage?start_timestamp=1785340800&end_timestamp=1785427200").json()
    row = body["data"]["summary"][0]
    assert body["completeness"] == "partial"
    assert row["request_count"] == 2
    assert row["total_tokens"] == 30
    assert row["actual_cost_usd"] is None
    assert row["average_duration_ms"] is None
    assert row["error_count"] == 1
    assert any(item.get("api_key_id") == 7 for item in body["warnings"])


def test_sub2api_error_route_accepts_canonical_key_id(client, monkeypatch):
    calls = []

    def fake(self, method, path, params=None, body=None):
        calls.append(params)
        return _fake_request(self, method, path, params, body)

    monkeypatch.setattr(sub2.Sub2APIClient, "_request", fake)
    response = client.get("/api/token-usage/errors?start_timestamp=1785340800&end_timestamp=1785427200&api_key_id=7")
    assert response.status_code == 200
    assert calls[0]["api_key_id"] == 7
    assert response.json()["data"]["items"][0]["api_key_id"] == 7


def test_sub2api_status_is_diagnostic_but_secret_free(client, monkeypatch):
    monkeypatch.setattr(sub2.Sub2APIClient, "_request", _fake_request)
    client.get("/api/token-usage?start_timestamp=1785340800&end_timestamp=1785427200")
    _wait_for_enrichment()
    response = client.get("/api/token-usage/status")
    assert response.status_code == 200
    body = response.json()
    assert body["upstream_version"] == "v0.1.166"
    assert body["auth_mode"] == "admin_key"
    assert body["capabilities"]["snapshot_v2"] is True
    assert "admin-secret-value" not in response.text


def test_sub2api_missing_credentials_does_not_fall_back_to_demo(client, monkeypatch):
    monkeypatch.delenv("TF_TOKEN_USAGE_SUB2API_ADMIN_KEY")
    response = client.get("/api/token-usage")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "NOT_CONFIGURED"


def test_sub2api_contract_mismatch_returns_502(client, monkeypatch):
    monkeypatch.setattr(sub2.Sub2APIClient, "_request", lambda *_args, **_kwargs: {})
    response = client.get("/api/token-usage")
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "CONTRACT_MISMATCH"


def test_client_sets_admin_header_and_validates_envelope(monkeypatch):
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"code": 0, "message": "success", "data": {"version": "v1"}}).encode()

    def fake_open(request, timeout):
        seen.update({"header": request.get_header("X-api-key"), "url": request.full_url, "timeout": timeout})
        return Response()

    monkeypatch.setattr(sub2.urllib.request, "urlopen", fake_open)
    cfg = sub2.config_from_env()
    assert sub2.Sub2APIClient(cfg).version() == "v1"
    assert seen["header"] == "admin-secret-value"
    assert seen["url"].endswith("/api/v1/admin/system/version")


def test_empty_snapshot_range_normalizes_missing_collections(monkeypatch):
    client = sub2.Sub2APIClient(sub2.config_from_env())
    monkeypatch.setattr(client, "_request", lambda *_args, **_kwargs: {
        "start_date": "2026-07-30",
        "end_date": "2026-07-30",
        "granularity": "hour",
    })
    snapshot = client.key_snapshot(7, 1785340800, 1785427200, "hour")
    assert snapshot["trend"] == []
    assert snapshot["models"] == []


def test_snapshot_still_rejects_missing_collections_without_range(monkeypatch):
    client = sub2.Sub2APIClient(sub2.config_from_env())
    monkeypatch.setattr(client, "_request", lambda *_args, **_kwargs: {})
    with pytest.raises(sub2.Sub2APIError, match="missing trend or models"):
        client.key_snapshot(7, 1785340800, 1785427200, "hour")


@pytest.mark.parametrize("token", ["session-token", "Bearer session-token"])
def test_client_uses_login_access_token_when_admin_key_is_absent(monkeypatch, token):
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"code": 0, "data": {"version": "v1"}}).encode()

    def fake_open(request, timeout):
        seen.update({
            "authorization": request.get_header("Authorization"),
            "admin_ui": request.get_header("X-admin-ui-request"),
            "admin_key": request.get_header("X-api-key"),
        })
        return Response()

    monkeypatch.delenv("TF_TOKEN_USAGE_SUB2API_ADMIN_KEY")
    monkeypatch.setenv("TF_TOKEN_USAGE_ACCESS_TOKEN", token)
    monkeypatch.setattr(sub2.urllib.request, "urlopen", fake_open)

    cfg = sub2.config_from_env()
    assert cfg.configured is True
    assert cfg.auth_mode == "access_token"
    assert sub2.Sub2APIClient(cfg).version() == "v1"
    assert seen == {
        "authorization": "Bearer session-token",
        "admin_ui": "1",
        "admin_key": None,
    }


def test_admin_key_takes_precedence_over_login_access_token(monkeypatch):
    cfg = sub2.config_from_env()
    assert cfg.admin_key == "admin-secret-value"
    assert cfg.auth_mode == "admin_key"


def test_dedicated_login_token_takes_precedence_over_legacy_variable(monkeypatch):
    monkeypatch.delenv("TF_TOKEN_USAGE_SUB2API_ADMIN_KEY")
    monkeypatch.setenv("TF_TOKEN_USAGE_SUB2API_ACCESS_TOKEN", "dedicated-token")
    monkeypatch.setenv("TF_TOKEN_USAGE_ACCESS_TOKEN", "legacy-token")
    cfg = sub2.config_from_env()
    assert cfg.access_token == "dedicated-token"
    assert sub2.status_payload(cfg)["auth_mode"] == "access_token"
    assert "dedicated-token" not in json.dumps(sub2.status_payload(cfg))


def test_cache_is_single_flight_and_reused(monkeypatch):
    calls = 0
    lock = threading.Lock()

    def loader():
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.03)
        return {"value": 1}

    results = []

    def run():
        results.append(sub2._cache_load(("same",), 60, loader))

    threads = [threading.Thread(target=run) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert calls == 1
    assert len(results) == 3
    assert sum(1 for _, cached, _ in results if cached) == 2


def test_stale_cache_survives_refresh_failure(monkeypatch):
    now = time.time()
    with sub2._CACHE_LOCK:
        sub2._CACHE[("stale",)] = sub2._CacheEntry(now - 10, {"value": 1})
    payload, cached, stale = sub2._cache_load(("stale",), 1, lambda: (_ for _ in ()).throw(RuntimeError("down")))
    assert payload == {"value": 1}
    assert cached is True
    assert stale is True


def test_invalid_comparison_range_is_rejected(client):
    one_side = client.get("/api/token-usage?comparison_start_timestamp=10")
    reversed_range = client.get("/api/token-usage?comparison_start_timestamp=20&comparison_end_timestamp=10")
    assert one_side.status_code == 400
    assert reversed_range.status_code == 400


def test_config_and_scalar_validation_helpers(monkeypatch):
    monkeypatch.setenv("TF_TOKEN_USAGE_SUB2API_USER_ID", "invalid")
    monkeypatch.setenv("TF_TOKEN_USAGE_MAX_CONCURRENCY", "invalid")
    cfg = sub2.config_from_env()
    assert cfg.user_id == 0
    assert cfg.max_concurrency == 4
    assert sub2._number([]) == 0
    assert sub2._timestamp(123.9, cfg) == 123
    assert sub2._timestamp("", cfg) == 0
    assert sub2._timestamp("not-a-time", cfg) == 0
    with pytest.raises(sub2.Sub2APIError, match="unknown timezone"):
        sub2._zone("Not/A-Timezone")


@pytest.mark.parametrize(
    ("status", "code", "attempts"),
    [(401, "AUTH_FAILED", 1), (404, "ENDPOINT_MISSING", 1), (500, "UPSTREAM_HTTP_ERROR", 2)],
)
def test_http_errors_are_classified_without_response_bodies(monkeypatch, status, code, attempts):
    calls = 0

    def fail(request, timeout):
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(request.full_url, status, "failed", {}, io.BytesIO(b"sk-never-print-this"))

    monkeypatch.setattr(sub2.urllib.request, "urlopen", fail)
    monkeypatch.setattr(sub2.time, "sleep", lambda _seconds: None)
    with pytest.raises(sub2.Sub2APIError) as caught:
        sub2.Sub2APIClient(sub2.config_from_env()).version()
    assert caught.value.code == code
    assert calls == attempts
    assert "sk-never-print-this" not in str(caught.value)


def test_network_failure_retries_once_and_redacts_secret(monkeypatch):
    calls = 0

    def fail(_request, timeout):
        nonlocal calls
        calls += 1
        raise OSError("socket failed for sk-secret-value-123")

    monkeypatch.setattr(sub2.urllib.request, "urlopen", fail)
    monkeypatch.setattr(sub2.time, "sleep", lambda _seconds: None)
    with pytest.raises(sub2.Sub2APIError) as caught:
        sub2.Sub2APIClient(sub2.config_from_env()).version()
    assert caught.value.code == "UPSTREAM_UNAVAILABLE"
    assert calls == 2
    assert "sk-secret-value-123" not in str(caught.value)


def test_network_failure_redacts_login_jwt(monkeypatch):
    jwt = "eyJabcdefghijk.eyJabcdefghijk.abcdefghijklmnop"
    monkeypatch.setattr(
        sub2.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError(f"failed for Bearer {jwt}")),
    )
    monkeypatch.setattr(sub2.time, "sleep", lambda _seconds: None)
    with pytest.raises(sub2.Sub2APIError) as caught:
        sub2.Sub2APIClient(sub2.config_from_env()).version()
    assert jwt not in str(caught.value)
    assert "[redacted]" in str(caught.value)


def test_client_endpoint_contracts_and_key_pagination(monkeypatch):
    pages = []

    def fake(self, method, path, params=None, body=None):
        if path.endswith("/api-keys"):
            pages.append(params["page"])
            return {
                "items": [{
                    "id": params["page"],
                    "name": f"key-{params['page']}",
                    "key": "sk-hidden-value",
                    "quota": 10,
                    "quota_used": 2,
                }],
                "pages": 2,
            }
        return {}

    monkeypatch.setattr(sub2.Sub2APIClient, "_request", fake)
    client = sub2.Sub2APIClient(sub2.config_from_env())
    keys = client.list_keys()
    assert pages == [1, 2]
    assert [item["id"] for item in keys] == [1, 2]
    assert all("key" not in item for item in keys)

    monkeypatch.setattr(sub2.Sub2APIClient, "_request", lambda *_args, **_kwargs: {})
    with pytest.raises(sub2.Sub2APIError):
        client.version()
    with pytest.raises(sub2.Sub2APIError):
        client.key_trend(1, 2, "day")
    with pytest.raises(sub2.Sub2APIError):
        client.key_snapshot(1, 1, 2, "day")
    with pytest.raises(sub2.Sub2APIError):
        client.key_stats(1, 1, 2)
    with pytest.raises(sub2.Sub2APIError):
        client.errors_page(1, 2, 1, 10)
    with pytest.raises(sub2.Sub2APIError):
        client.list_keys()


def test_snapshot_missing_required_metric_is_not_coerced_to_zero(monkeypatch):
    client = sub2.Sub2APIClient(sub2.config_from_env())
    monkeypatch.setattr(client, "_request", lambda *_args, **_kwargs: {
        "trend": [{
            "date": "2026-07-30",
            "requests": 1,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
        }],
        "models": [],
    })
    with pytest.raises(sub2.Sub2APIError, match="actual_cost"):
        client.key_snapshot(7, 1, 2, "day")


def test_large_error_volume_uses_bounded_per_key_totals(monkeypatch):
    cfg = sub2.config_from_env()
    client = sub2.Sub2APIClient(cfg)
    calls = []

    def errors_page(start, end, page, page_size, key_id=None):
        calls.append((page_size, key_id))
        if key_id is None:
            return {"items": [], "total": 10001, "pages": 21}
        return {"items": [], "total": key_id, "pages": 1}

    monkeypatch.setattr(client, "errors_page", errors_page)
    counts, rows = sub2._all_errors(client, 1, 2, [3, 4])
    assert counts == {3: 3, 4: 4}
    assert rows == []
    assert sorted(calls[1:]) == [(1, 3), (1, 4)]


def test_error_pagination_skips_invalid_rows(monkeypatch):
    client = sub2.Sub2APIClient(sub2.config_from_env())

    def errors_page(start, end, page, page_size, key_id=None):
        if page == 1:
            return {"items": [None], "total": 501, "pages": 2}
        return {"items": [{"id": 2, "api_key_id": 7, "created_at": 1}], "total": 501, "pages": 2}

    monkeypatch.setattr(client, "errors_page", errors_page)
    counts, rows = sub2._all_errors(client, 1, 2, [7])
    assert counts == {7: 1}
    assert rows[0]["api_key_id"] == 7


def test_usage_stale_fallback_and_unconfigured_errors(monkeypatch):
    cfg = sub2.config_from_env()
    start, end = 1, 86401
    key = (
        "usage", cfg.base_url, cfg.auth_mode, cfg.user_id, cfg.timezone_name,
        start, end, "day", None, None,
    )
    with sub2._CACHE_LOCK:
        sub2._CACHE[key] = sub2._CacheEntry(time.time() - 1000, {
            "schema_version": 2,
            "data": {"summary": [], "trend": [], "models": []},
            "comparison": None,
            "completeness": "complete",
            "warnings": [],
        })
    monkeypatch.setattr(sub2.Sub2APIClient, "version", lambda _self: (_ for _ in ()).throw(sub2.Sub2APIError("UPSTREAM_UNAVAILABLE", "down")))
    payload = sub2.get_usage(cfg, start, end, "day")
    assert payload["freshness"] == "stale"
    assert payload["completeness"] == "stale"
    assert payload["warnings"][-1]["code"] == "STALE_IF_ERROR"
    assert sub2.status_payload(cfg)["last_error_code"] == "UPSTREAM_UNAVAILABLE"

    unconfigured = sub2.Sub2APIConfig("", "", 0, "Asia/Shanghai", 1, 1)
    with pytest.raises(sub2.Sub2APIError) as caught:
        sub2.get_errors(unconfigured, 1, 2, None, 10)
    assert caught.value.code == "NOT_CONFIGURED"


def test_background_failure_is_recorded_without_replacing_core(monkeypatch):
    cfg = sub2.config_from_env()
    key = ("background",)
    with sub2._CACHE_LOCK:
        sub2._CACHE[key] = sub2._CacheEntry(time.time(), {"warnings": [{"code": "DETAILS_SYNCING"}]})
        sub2._ENRICHMENT_CONTEXT[key] = {"safe": True}
    monkeypatch.setattr(sub2, "_full_payload", lambda *_args: (_ for _ in ()).throw(sub2.Sub2APIError("CONTRACT_MISMATCH", "bad")))
    sub2._start_enrichment(key, cfg)
    _wait_for_enrichment()
    with sub2._CACHE_LOCK:
        assert sub2._CACHE[key].payload["warnings"] == [{"code": "CONTRACT_MISMATCH"}]
    assert sub2.status_payload(cfg)["last_error_code"] == "CONTRACT_MISMATCH"
    sub2._start_enrichment(("missing",), cfg)
