"""pytest 共享夹具:把 server/ 加入 import 路径,并提供每个测试独立的
内存级 SQLite + 可控开关的 TestClient(对齐 AGENTS.md 的 TestClient 自测约定)。"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def app_mod(tmp_path):
    from server import app
    # 每个测试一个独立 DB + 默认全关的开关(逐测试再按需打开)
    app.DB_PATH = str(tmp_path / "tf_test.db")
    app.INGEST_KEY = ""          # 不校验写密钥,测试免带 header
    app.ADMIN_KEY = ""
    app.ADMIN_MAX_ROWS = 200
    app.TRASH_DAYS = 30
    app.STATE_TTL_SECONDS = app._env_float("TF_STATE_TTL", "1.5")
    app.HEARTBEAT_BATCH_SECONDS = app._env_float("TF_HEARTBEAT_BATCH_SECONDS", "15")
    app.HEARTBEAT_MAX_SILENCE_SECONDS = app._env_float(
        "TF_HEARTBEAT_MAX_SILENCE_SECONDS", "14400",
    )
    with app._state_cache_lock:
        app._state_cache.update({"at": 0.0, "data": None, "computing": False})
    with app._heartbeat_pending_lock:
        app._heartbeat_pending.clear()
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


def set_ingest_clock(monkeypatch, *values):
    """按序列推进入库时间,并让读侧「现在」停在最近一次入库时间。

    只替换 ingest.now_utc 时,读侧的 90 天窗口/今天仍走真实时钟,写死日期的
    用例会随真实日期推移而过期;这里同时锁死 app.datetime(见 server/AGENTS.md
    「时间源」)。
    """
    from server import app
    import server.routes.ingest as ingest

    times = [datetime.fromisoformat(v).replace(tzinfo=timezone.utc) for v in values]
    seq = iter(times)
    clock = {"now": times[0]}

    def next_ingest_time():
        clock["now"] = next(seq)
        return clock["now"]

    class ClockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = clock["now"]
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(ingest, "now_utc", next_ingest_time)
    monkeypatch.setattr(app, "datetime", ClockDatetime)
