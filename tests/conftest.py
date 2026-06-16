"""pytest 共享夹具:把 server/ 加入 import 路径,并提供每个测试独立的
内存级 SQLite + 可控开关的 TestClient(对齐 AGENTS.md 的 TestClient 自测约定)。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))


@pytest.fixture
def app_mod(tmp_path):
    import app
    # 每个测试一个独立 DB + 默认全关的开关(逐测试再按需打开)
    app.DB_PATH = str(tmp_path / "tf_test.db")
    app.INGEST_KEY = ""          # 不校验写密钥,测试免带 header
    app.ADMIN_KEY = ""
    app.ADMIN_MAX_ROWS = 200
    app.TRASH_DAYS = 30
    app._prune_state["n"] = 0
    app.REQUIRE_TOKEN = False
    app.READ_AUTH_OK = False
    app.TRUST_PROXY = False
    # 限流器是进程内全局状态(非每测试),显式清空避免跨测试污染/误触封锁
    with app._rate_lock:
        app._rate_state.clear()
    # 单测显式调用 sync_catalog_once() 时再测试 catalog；避免 TestClient
    # startup 在后台打真实网络,也避免跨测试污染内存缓存。
    app._catalog_thread_started = True
    with app._catalog_lock:
        app._catalog_state.update({"items": None, "fetched_at": None, "error": None, "last_attempt": None})
    app.init_db()
    return app


@pytest.fixture
def client(app_mod):
    from fastapi.testclient import TestClient
    return TestClient(app_mod.app)


def ev(client, **over):
    """发一个最小合法事件,允许覆盖/追加字段与 headers。"""
    headers = over.pop("headers", {})
    payload = {"v": "0.1", "operator": "alice", "runtime": "codex",
               "session_id": "s1", "status": "running"}
    payload.update(over)
    payload = {k: v for k, v in payload.items() if v is not None}
    return client.post("/v1/events", json=payload, headers=headers)
