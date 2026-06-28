import json
import urllib.error

import pytest

from server.routes import token_usage as tu


@pytest.fixture(autouse=True)
def clear_token_usage_cache(monkeypatch):
    for name in (
        "TF_TOKEN_USAGE_BASE_URL",
        "TF_TOKEN_USAGE_PATH",
        "TF_TOKEN_USAGE_ACCESS_TOKEN",
        "TF_TOKEN_USAGE_COOKIE",
        "TF_TOKEN_USAGE_USER_ID",
        "TF_TOKEN_USAGE_TIMEOUT",
        "TF_TOKEN_USAGE_CACHE_TTL",
        "TF_TOKEN_USAGE_DEMO",
    ):
        monkeypatch.delenv(name, raising=False)
    with tu._UPSTREAM_CACHE_LOCK:
        tu._UPSTREAM_CACHE.clear()


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
    assert second["data"] == first["data"]
    assert first["data"]["trend"][0]["count"] == 3
    assert first["data"]["trend"][0]["error_count"] == 1
    assert first["data"]["trend"][0]["quota"] == 30


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
