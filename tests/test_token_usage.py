import json
import urllib.error

import pytest

from server.routes import token_usage as tu


@pytest.fixture(autouse=True)
def clear_token_usage_cache(monkeypatch):
    for name in (
        "TF_TOKEN_USAGE_PROVIDER",
        "TF_TOKEN_USAGE_BASE_URL",
        "TF_TOKEN_USAGE_PATH",
        "TF_TOKEN_USAGE_LOG_PATH",
        "TF_TOKEN_USAGE_ACCESS_TOKEN",
        "TF_TOKEN_USAGE_COOKIE",
        "TF_TOKEN_USAGE_USER_ID",
        "TF_TOKEN_USAGE_TIMEOUT",
        "TF_TOKEN_USAGE_CACHE_TTL",
        "TF_TOKEN_USAGE_DEMO",
        "TF_TOKEN_USAGE_SUB2API_ADMIN_KEY",
        "TF_TOKEN_USAGE_SUB2API_USER_ID",
        "TF_TOKEN_USAGE_TIMEZONE",
        "TF_TOKEN_USAGE_MAX_CONCURRENCY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TF_TOKEN_USAGE_PROVIDER", "legacy_newapi")
    with tu._UPSTREAM_CACHE_LOCK:
        tu._UPSTREAM_CACHE.clear()
    with tu._ERROR_CACHE_LOCK:
        tu._ERROR_CACHE.clear()


def test_token_usage_demo_fallback_when_unconfigured(client):
    body = client.get("/api/token-usage?days=3").json()

    assert body["ok"] is True
    assert body["source"] == "demo"
    assert body["configured"] is False
    assert "credentials" in body["warning"]
    assert body["range"]["days"] == 3
    assert body["data"]["summary"]
    assert body["data"]["trend"]
    assert body["data"]["models"]


def test_token_usage_explicit_range_validation(client):
    bad_order = client.get("/api/token-usage?start_timestamp=20&end_timestamp=10")
    assert bad_order.status_code == 400
    assert "before" in bad_order.json()["detail"]

    too_large = client.get("/api/token-usage?start_timestamp=1&end_timestamp=20000000")
    assert too_large.status_code == 400
    assert "too large" in too_large.json()["detail"]


def test_relative_range_is_stable_within_the_same_minute(monkeypatch):
    from server.routes import token_usage

    monkeypatch.setattr(token_usage.time, "time", lambda: 1785381241.9)
    first = token_usage._range(1)
    monkeypatch.setattr(token_usage.time, "time", lambda: 1785381258.1)
    second = token_usage._range(1)
    assert first == second
    assert first[1] % 60 == 0


def test_token_usage_upstream_success_and_cache(client, monkeypatch):
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                "success": True,
                "data": {
                    "summary": [{"token_id": 1, "token_name": "key-a", "quota": 10}],
                    "trend": [
                        {"token_id": 1, "token_name": "key-a", "created_at": 1000, "count": 1, "error_count": 0, "quota": 10, "token_used": 100},
                        {"token_id": 1, "token_name": "key-a", "created_at": 1300, "count": 2, "error_count": 1, "quota": 20, "token_used": 200},
                    ],
                    "models": [{"token_id": 1, "model_name": "gpt", "quota": 30}],
                },
            }).encode()

    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        return FakeResponse()

    monkeypatch.setenv("TF_TOKEN_USAGE_BASE_URL", "https://example.test/")
    monkeypatch.setenv("TF_TOKEN_USAGE_PATH", "/usage")
    monkeypatch.setenv("TF_TOKEN_USAGE_ACCESS_TOKEN", "Bearer token")
    monkeypatch.setenv("TF_TOKEN_USAGE_COOKIE", "sid=abc")
    monkeypatch.setenv("TF_TOKEN_USAGE_USER_ID", "42")
    monkeypatch.setenv("TF_TOKEN_USAGE_TIMEOUT", "3")
    monkeypatch.setattr(tu.urllib.request, "urlopen", fake_urlopen)

    url = "/api/token-usage?start_timestamp=1000&end_timestamp=2000&time_granularity=four_hour&timezone_offset_minutes=0"
    first = client.get(url).json()
    second = client.get(url).json()

    assert len(calls) == 1
    req, timeout = calls[0]
    assert timeout == 3
    assert req.full_url.startswith("https://example.test/usage?")
    assert req.headers["Authorization"] == "Bearer token"
    assert req.headers["Cookie"] == "sid=abc"
    assert req.headers["New-api-user"] == "42"
    assert first["source"] == "upstream"
    assert first["configured"] is True
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["data"] == first["data"]
    assert first["data"]["trend"][0]["count"] == 3
    assert first["data"]["trend"][0]["error_count"] == 1
    assert first["data"]["trend"][0]["quota"] == 30


def test_token_usage_error_logs_success_and_cache(client, monkeypatch):
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                "success": True,
                "data": {
                    "page": 1,
                    "page_size": 30,
                    "total": 1,
                    "items": [{
                        "id": 99,
                        "created_at": 1784649700,
                        "type": 5,
                        "token_id": 15,
                        "token_name": "key-a",
                        "username": "admin",
                        "user_id": 1,
                        "group": "Dapp",
                        "model_name": "gpt-5.5",
                        "content": "upstream timeout",
                        "use_time": 31,
                        "is_stream": True,
                        "channel": 7,
                        "channel_name": "openai",
                        "request_id": "req-local",
                        "upstream_request_id": "req-up",
                        "other": json.dumps({
                            "status_code": 504,
                            "error_type": "upstream_error",
                            "error_code": "timeout",
                            "request_path": "/v1/responses",
                        }),
                    }],
                },
            }).encode()

    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        return FakeResponse()

    monkeypatch.setenv("TF_TOKEN_USAGE_BASE_URL", "https://example.test")
    monkeypatch.setenv("TF_TOKEN_USAGE_LOG_PATH", "/api/log/")
    monkeypatch.setenv("TF_TOKEN_USAGE_ACCESS_TOKEN", "Bearer token")
    monkeypatch.setenv("TF_TOKEN_USAGE_USER_ID", "42")
    monkeypatch.setattr(tu.urllib.request, "urlopen", fake_urlopen)

    url = "/api/token-usage/errors?start_timestamp=1784649600&end_timestamp=1784736000&token_id=15&token_name=key-a"
    first = client.get(url).json()
    second = client.get(url).json()

    assert len(calls) == 1
    req, _timeout = calls[0]
    assert req.full_url.startswith("https://example.test/api/log/?")
    assert "type=5" in req.full_url
    assert "token_name=key-a" in req.full_url
    assert req.headers["Authorization"] == "Bearer token"
    assert req.headers["New-api-user"] == "42"
    assert first["source"] == "upstream"
    assert first["cached"] is False
    assert second["cached"] is True
    row = first["data"]["items"][0]
    assert row["content"] == "upstream timeout"
    assert row["status_code"] == 504
    assert row["error_code"] == "timeout"
    assert first["data"]["summary"][0]["count"] == 1


def test_token_usage_upstream_failure_without_demo_returns_502(client, monkeypatch):
    monkeypatch.setenv("TF_TOKEN_USAGE_DEMO", "0")
    response = client.get("/api/token-usage")

    assert response.status_code == 502
    assert "credentials" in response.json()["detail"]


def test_token_usage_upstream_errors_are_reported(monkeypatch):
    class FakeHTTPError(urllib.error.HTTPError):
        def read(self):
            return b"bad gateway body"

    def fail_http(_req, timeout=None):
        raise FakeHTTPError("https://example.test", 502, "bad", {}, None)

    cfg = {
        "base_url": "https://example.test",
        "path": "/usage",
        "access_token": "Bearer token",
        "cookie": "",
        "user_id": "42",
        "timeout": 1,
    }
    monkeypatch.setattr(tu.urllib.request, "urlopen", fail_http)
    with pytest.raises(RuntimeError, match="upstream returned 502"):
        tu._query_upstream(cfg, 1, 2, "day", 0)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"success": false, "message": "denied"}'

    monkeypatch.setattr(tu.urllib.request, "urlopen", lambda _req, timeout=None: FakeResponse())
    with pytest.raises(RuntimeError, match="denied"):
        tu._query_upstream(cfg, 1, 2, "day", 0)


def test_token_usage_granularity_helpers():
    assert tu._env_bool("TF_TOKEN_USAGE_NO_SUCH_ENV", True) is True
    assert tu._upstream_granularity("four_hour") == "hour"
    assert tu._upstream_granularity("week") == "day"
    assert tu._bucket_start(1764554400, "four_hour", 480) % (4 * 3600) == 0

    rows = [
        {"token_id": 1, "token_name": "a", "username": "u", "user_id": 1, "created_at": 1764554400, "count": 2, "error_count": 1, "quota": 30, "token_used": 300},
        {"token_id": 1, "token_name": "a", "username": "u", "user_id": 1, "created_at": 1764558000, "count": 3, "error_count": 0, "quota": 20, "token_used": 200},
        {"token_id": 2, "token_name": "b", "username": "v", "user_id": 2, "created_at": 1764558000, "count": 1, "error_count": 0, "quota": 50, "token_used": 500},
    ]
    assert tu._aggregate_trend(rows, "day", 480) == rows

    grouped = tu._aggregate_trend(rows, "four_hour", 480)
    assert len(grouped) == 2
    first = next(row for row in grouped if row["token_id"] == 1)
    assert first["count"] == 5
    assert first["error_count"] == 1
    assert first["quota"] == 50
    assert first["token_used"] == 500


def test_legacy_helper_edge_cases(monkeypatch):
    cfg = {
        "base_url": "https://example.test",
        "log_path": "/logs",
        "access_token": "token",
        "cookie": "",
        "user_id": "1",
        "timeout": 1,
    }
    monkeypatch.setattr(tu.urllib.request, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(RuntimeError, match="offline"):
        tu._read_json_url("https://example.test", cfg)

    timestamp = 1764554400
    assert tu._bucket_start(timestamp, "day", 480) == timestamp
    assert tu._bucket_start(timestamp, "week", 480) <= timestamp
    assert tu._bucket_start(timestamp, "month", 480) <= timestamp
    assert tu._safe_json_map({"a": 1}) == {"a": 1}
    assert tu._safe_json_map("") == {}
    assert tu._safe_json_map("not-json") == {}
    assert tu._safe_int([]) == 0
    assert tu._error_reason_key({"content": "x" * 100}).endswith("...")
    assert len(tu._demo_error_logs(1, 100, "", None)["items"]) == 3


def test_legacy_error_query_filters_and_contract_edges(monkeypatch):
    cfg = {
        "base_url": "https://example.test",
        "log_path": "/logs",
        "access_token": "token",
        "cookie": "",
        "user_id": "1",
        "timeout": 1,
    }
    with pytest.raises(RuntimeError, match="credentials"):
        tu._query_error_logs({**cfg, "access_token": "", "user_id": ""}, 1, 2, "", None, "", "", 10)

    monkeypatch.setattr(tu, "_read_json_url", lambda *_args: {"success": False, "message": "denied"})
    with pytest.raises(RuntimeError, match="denied"):
        tu._query_error_logs(cfg, 1, 2, "name", 7, "model", "group", 10)

    seen = {}

    def read(url, _cfg):
        seen["url"] = url
        return {"success": True, "data": {"items": "invalid", "total": 8}}

    monkeypatch.setattr(tu, "_read_json_url", read)
    empty = tu._query_error_logs(cfg, 1, 2, "", None, "model", "group", 10)
    assert empty["items"] == []
    assert empty["total"] == 8
    assert "model_name=model" in seen["url"]
    assert "group=group" in seen["url"]

    monkeypatch.setattr(tu, "_read_json_url", lambda *_args: {
        "success": True,
        "data": {"items": [{"token_id": 7}, {"token_id": 8}], "total": 2},
    })
    filtered = tu._query_error_logs(cfg, 1, 2, "", 7, "", "", 10)
    assert filtered["total"] == 1
    assert filtered["items"][0]["token_id"] == 7


def test_provider_route_error_branches(client, monkeypatch):
    monkeypatch.setenv("TF_TOKEN_USAGE_PROVIDER", "unsupported")
    assert client.get("/api/token-usage").status_code == 500
    assert client.get("/api/token-usage/errors").status_code == 500

    monkeypatch.setenv("TF_TOKEN_USAGE_PROVIDER", "sub2api")
    monkeypatch.setenv("TF_TOKEN_USAGE_SUB2API_ADMIN_KEY", "admin-secret-value")
    monkeypatch.setattr(tu.sub2api, "get_usage", lambda *_args: (_ for _ in ()).throw(RuntimeError("unexpected")))
    response = client.get("/api/token-usage")
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "UPSTREAM_FAILED"

    monkeypatch.setattr(
        tu.sub2api,
        "get_errors",
        lambda *_args: (_ for _ in ()).throw(tu.sub2api.Sub2APIError("AUTH_FAILED", "denied")),
    )
    response = client.get("/api/token-usage/errors")
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "AUTH_FAILED"


def test_legacy_error_demo_and_status(client, monkeypatch):
    monkeypatch.setenv("TF_TOKEN_USAGE_PROVIDER", "legacy_newapi")
    body = client.get("/api/token-usage/errors?token_id=7&token_name=demo").json()
    assert body["source"] == "demo"
    assert body["warning"]
    assert body["data"]["items"][0]["token_id"] == 7
    status = client.get("/api/token-usage/status").json()
    assert status["provider"] == "legacy_newapi"
    assert status["capabilities"]["legacy_newapi"] is True
