"""catalog 解析 / 取 / 缓存的行为锁定测试。
对应 server/app.py 内的 _catalog_source / _parse_catalog_payload / _fetch_catalog /
_save_catalog_cache / _load_catalog_cache / _catalog_context。
由 add-server-app-test-baseline 引入。
"""
import json
import socket

import pytest
from contextlib import closing
from conftest import ev


# ---- _catalog_source ------------------------------------------------------
def test_catalog_source_normalizes_known_values(app_mod):
    assert app_mod._catalog_source("own") == "own"
    assert app_mod._catalog_source("META") == "meta"
    assert app_mod._catalog_source(" external ") == "external"


def test_catalog_source_falls_back_external_for_unknown_or_non_str(app_mod):
    assert app_mod._catalog_source("vendor") == "external"
    assert app_mod._catalog_source(None) == "external"
    assert app_mod._catalog_source(123) == "external"


# ---- _parse_catalog_payload ----------------------------------------------
def test_parse_payload_accepts_bytes_and_str(app_mod):
    payload = {"skills": [{"name": "a", "type": "own"}]}
    parsed_str = app_mod._parse_catalog_payload(json.dumps(payload))
    parsed_bytes = app_mod._parse_catalog_payload(json.dumps(payload).encode())
    assert parsed_str["skills"] == parsed_bytes["skills"]
    assert parsed_str["skills"][0]["type"] == "own"


def test_parse_payload_accepts_bare_list_top_level(app_mod):
    parsed = app_mod._parse_catalog_payload(json.dumps([{"name": "x", "type": "meta"}]))
    assert parsed["skills"][0]["name"] == "x"
    assert parsed["version"] is None


def test_parse_payload_drops_missing_name_and_dedupes(app_mod):
    payload = {"skills": [
        {"name": "k", "type": "own"},
        {"name": "k", "type": "meta"},          # 重名 → 去重
        {"type": "own"},                         # 缺 name → 丢弃
        "not-a-dict",                            # 非 dict → 丢弃
    ]}
    parsed = app_mod._parse_catalog_payload(json.dumps(payload))
    names = [s["name"] for s in parsed["skills"]]
    assert names == ["k"]
    assert parsed["skills"][0]["type"] == "own"  # 首条胜出


def test_parse_payload_unknown_type_falls_back_external(app_mod):
    payload = {"skills": [{"name": "x", "type": "vendor"}]}
    parsed = app_mod._parse_catalog_payload(json.dumps(payload))
    assert parsed["skills"][0]["type"] == "external"


def test_parse_payload_preserves_and_cleans_bilingual_display_names(app_mod):
    payload = {"skills": [{
        "name": "openspec-driven-development",
        "type": "own",
        "display_name": "  OpenSpec-Driven Development  ",
        "display_name_zh": " OpenSpec 驱动开发 ",
    }]}
    item = app_mod._parse_catalog_payload(payload)["skills"][0]
    assert item["display_name"] == "OpenSpec-Driven Development"
    assert item["display_name_zh"] == "OpenSpec 驱动开发"


def test_parse_payload_raises_when_skills_is_not_a_list(app_mod):
    with pytest.raises(ValueError):
        app_mod._parse_catalog_payload(json.dumps({"skills": "oops"}))


def test_parse_payload_preserves_version_and_generated_at(app_mod):
    payload = {"version": "v1", "generated_at": "2026-06-25", "skills": []}
    parsed = app_mod._parse_catalog_payload(json.dumps(payload))
    assert parsed["version"] == "v1"
    assert parsed["generated_at"] == "2026-06-25"


# ---- _fetch_catalog -------------------------------------------------------
class _FakeResp:
    def __init__(self, data): self._data = data
    def read(self, *_): return self._data
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_fetch_catalog_success(app_mod, monkeypatch):
    payload = json.dumps({"skills": [{"name": "n", "type": "own"}]}).encode()
    monkeypatch.setattr(app_mod.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResp(payload))
    parsed = app_mod._fetch_catalog()
    assert parsed["skills"][0]["name"] == "n"


def test_fetch_catalog_timeout_propagates(app_mod, monkeypatch):
    def _boom(*a, **k):
        raise socket.timeout("simulated")
    monkeypatch.setattr(app_mod.urllib.request, "urlopen", _boom)
    with pytest.raises(socket.timeout):
        app_mod._fetch_catalog()


def test_sync_catalog_once_records_error_on_failure(app_mod, monkeypatch):
    def _boom(*a, **k):
        raise socket.timeout("simulated")
    monkeypatch.setattr(app_mod.urllib.request, "urlopen", _boom)
    ok = app_mod.sync_catalog_once()
    assert ok is False
    assert app_mod._catalog_state.get("error")


# ---- _save_catalog_cache ↔ _load_catalog_cache ---------------------------
def test_save_and_load_cache_roundtrip(app_mod):
    catalog = {"version": "v2", "generated_at": "2026-06-25",
               "skills": [{"name": "y", "type": "own", "description": ""}]}
    with closing(app_mod.db()) as conn:
        app_mod._save_catalog_cache(conn, catalog)
        conn.commit()
    # 清空内存态,逼 _load 从 DB 读
    with app_mod._catalog_lock:
        app_mod._catalog_state.update({"items": None, "fetched_at": None, "error": None, "last_attempt": None})
    with closing(app_mod.db()) as conn:
        loaded = app_mod._load_catalog_cache(conn)
    assert loaded["available"] is True
    assert any(i["name"] == "y" for i in loaded["items"])


def test_load_cache_empty_db_returns_unavailable(app_mod):
    with closing(app_mod.db()) as conn:
        loaded = app_mod._load_catalog_cache(conn)
    assert loaded["available"] is False
    assert loaded["items"] == []


def test_catalog_context_returns_items_and_map(app_mod):
    catalog = {"version": "v", "skills": [{"name": "a", "type": "own"},
                                          {"name": "b", "type": "external"}]}
    with closing(app_mod.db()) as conn:
        app_mod._save_catalog_cache(conn, catalog)
        items, by_name, meta = app_mod._catalog_context(conn)
    assert {"a", "b"} <= {i["name"] for i in items}
    assert by_name["a"] == "own"
    assert by_name["b"] == "external"
    assert meta["available"] is True


def test_skill_name_map_catalog_wins_profile_and_falls_back_to_slug(app_mod):
    from server.catalog import _skill_name_map
    with closing(app_mod.db()) as conn:
        conn.execute("""INSERT INTO profiles(operator,ak,runtime,json,updated)
          VALUES(?,?,?,?,?)""", ("alice", "codex", "codex", json.dumps({
            "skills": {"local": [
                {"name": "alpha", "display_name": "Profile Alpha", "display_name_zh": "本机 Alpha"},
                {"name": "local-only", "display_name_zh": "本机专用"},
            ]},
        }), "2026-07-14T00:00:00+00:00"))
        conn.execute("""INSERT INTO skills_seen(name,first_day) VALUES(?,?)""", ("slug-only", "2026-07-14"))
        labels = _skill_name_map(conn, [{
            "name": "alpha", "type": "own",
            "display_name": "Catalog Alpha", "display_name_zh": "公司 Alpha",
        }])
    assert labels["alpha"] == {"display_name": "Catalog Alpha", "display_name_zh": "公司 Alpha"}
    assert labels["local-only"] == {"display_name": "本机专用", "display_name_zh": "本机专用"}
    assert labels["slug-only"] == {"display_name": "slug-only", "display_name_zh": "slug-only"}


# ---- skills 公司库口径(由 catalog 驱动) --------------------------------
def test_skills_funnel_uses_catalog(app_mod, client):
    catalog = {"version": "v", "skills": [
        {"name": "company-a", "type": "own"},
        {"name": "company-b", "type": "meta"},
        {"name": "外部-x", "type": "external"},
    ]}
    with closing(app_mod.db()) as conn:
        app_mod._save_catalog_cache(conn, catalog)
        conn.commit()
    ev(client, session_id="s1", current_step="run", skill="company-a")
    funnel = client.get("/api/skills?days=30").json()["funnel"]
    assert funnel["available"] is True
    names_catalog = {i["name"] for i in funnel["catalog"]}
    assert {"company-a", "company-b"} <= names_catalog
    assert "外部-x" not in names_catalog  # external 不算"公司库"
    names_used = {i["name"] for i in funnel["used_30d"]}
    assert "company-a" in names_used
