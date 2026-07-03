"""tranfu-skills 公司库 catalog 同步与缓存(由 refactor-server-app-by-domain 引入)。

后台 daemon 线程定时拉 catalog;落 catalog_cache 表 + 内存 _catalog_state 双缓存。
admin/board 域通过 _catalog_context / _skill_source 读取「这个 skill 是不是公司库的」。

模块状态(_catalog_state / _catalog_lock / _catalog_thread_started)留在 server/app.py
以兼容 conftest 的 monkeypatch;本模块函数体内 from server import app 延迟读。
"""
import json
import os
import threading
import time
import urllib.request
from contextlib import closing

from server.config import (
    CATALOG_URL, CATALOG_TTL_SECONDS, CATALOG_FETCH_TIMEOUT,
    CATALOG_SOURCE_UNKNOWN,
)
from server.db import db, now_iso

# 注:_skill_use_name / _skill_names 来自 server.profile;它在 import 顺序上晚于本模块,
# 所以函数体内延迟 import,避免 catalog<->profile 顶层互导。


def _catalog_source(value):
    value = (value or "external").strip().lower() if isinstance(value, str) else "external"
    return value if value in ("own", "meta", "external") else "external"


def _parse_catalog_payload(raw):
    from server.profile import _skill_use_name
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw) if isinstance(raw, str) else raw
    skills = data.get("skills") if isinstance(data, dict) else data
    if not isinstance(skills, list):
        raise ValueError("catalog skills must be a list")
    out, seen = [], set()
    for item in skills:
        if not isinstance(item, dict):
            continue
        name = _skill_use_name(item.get("name"))
        if not name or name in seen:
            continue
        seen.add(name)
        parsed = {
            "name": name,
            "type": _catalog_source(item.get("type")),
            "description": item.get("description") or "",
        }
        for key in ("version", "author", "updated_at", "published_at", "path", "sha"):
            value = item.get(key)
            if value is not None:
                parsed[key] = value
        out.append(parsed)
    return {
        "version": data.get("version") if isinstance(data, dict) else None,
        "generated_at": data.get("generated_at") if isinstance(data, dict) else None,
        "skills": out,
    }


def _fetch_catalog():
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "TRANFU-AGENTS/1.0"})
    with urllib.request.urlopen(req, timeout=CATALOG_FETCH_TIMEOUT) as resp:
        return _parse_catalog_payload(resp.read(768 * 1024))


def _save_catalog_cache(conn, catalog, fetched_at=None):
    from server import app
    fetched_at = fetched_at or now_iso()
    conn.execute("""INSERT INTO catalog_cache(id,json,fetched_at) VALUES(1,?,?)
      ON CONFLICT(id) DO UPDATE SET json=excluded.json,fetched_at=excluded.fetched_at""",
      (json.dumps(catalog, ensure_ascii=False), fetched_at))
    with app._catalog_lock:
        app._catalog_state.update({
            "items": catalog.get("skills") or [],
            "fetched_at": fetched_at,
            "error": None,
            "last_attempt": fetched_at,
        })


def _record_catalog_error(exc):
    from server import app
    msg = str(exc)[:240] if exc else "catalog fetch failed"
    with app._catalog_lock:
        app._catalog_state.update({"error": msg, "last_attempt": now_iso()})


def sync_catalog_once():
    """Fetch the catalog once. Failure is recorded but never raised."""
    from server import app
    try:
        # 通过 app 命名空间间接调用,保留 monkeypatch(app_mod, "_fetch_catalog", ...) 语义
        catalog = app._fetch_catalog()
    except Exception as exc:
        _record_catalog_error(exc)
        return False
    with app._lock, closing(db()) as conn:
        _save_catalog_cache(conn, catalog)
        conn.commit()
    return True


def _catalog_loop():  # pragma: no cover  — 后台 daemon 线程主循环,conftest 已禁线程启动
    while True:
        sync_catalog_once()
        time.sleep(max(60, CATALOG_TTL_SECONDS))


def _start_catalog_sync():  # pragma: no cover  — 后台线程启动,conftest 已抢先标 started
    from server import app
    if os.environ.get("TF_SKILLS_CATALOG_SYNC", "1") == "0":
        return
    with app._catalog_lock:
        if app._catalog_thread_started:
            return
        app._catalog_thread_started = True
    threading.Thread(target=_catalog_loop, name="tf-skills-catalog", daemon=True).start()


def _startup_catalog_sync():  # pragma: no cover  — startup 回调,见上
    _start_catalog_sync()


def _load_catalog_cache(conn):
    from server import app
    with app._catalog_lock:
        state = dict(app._catalog_state)
    if state.get("items") is not None:
        items = state.get("items") or []
        return {
            "items": items,
            "fetched_at": state.get("fetched_at"),
            "stale": bool(state.get("error")),
            "available": bool(items),
            "error": state.get("error"),
            "last_attempt": state.get("last_attempt"),
        }
    row = conn.execute("SELECT json,fetched_at FROM catalog_cache WHERE id=1").fetchone()
    if not row:
        return {
            "items": [],
            "fetched_at": None,
            "stale": True,
            "available": False,
            "error": state.get("error"),
            "last_attempt": state.get("last_attempt"),
        }
    try:
        data = json.loads(row["json"])
        items = data.get("skills") or []
    except Exception as exc:  # pragma: no cover  — DB cache JSON 损坏兜底
        items = []
        state["error"] = str(exc)[:240]
    return {
        "items": items,
        "fetched_at": row["fetched_at"],
        "stale": bool(state.get("error")),
        "available": bool(items),
        "error": state.get("error"),
        "last_attempt": state.get("last_attempt"),
    }


def _catalog_context(conn):
    cache = _load_catalog_cache(conn)
    by_name = {i["name"]: i["type"] for i in cache["items"] if i.get("name")}
    catalog = {
        "available": cache["available"],
        "fetched_at": cache["fetched_at"],
        "stale": cache["stale"],
        "error": cache["error"],
        "last_attempt": cache["last_attempt"],
        "count": len(cache["items"]),
    }
    return cache["items"], by_name, catalog


def _skill_source(name, catalog_by_name):
    return catalog_by_name.get(name) or CATALOG_SOURCE_UNKNOWN


def _installed_skill_names(conn):
    from server.profile import _skill_names, _skill_use_name
    names = set()
    for r in conn.execute("SELECT json FROM profiles"):
        try:
            p = json.loads(r["json"])
        except Exception:  # pragma: no cover  — profile JSON 损坏兜底
            continue
        for nm in _skill_names(p.get("skills")):
            clean = _skill_use_name(nm)
            if clean:
                names.add(clean)
    return names


def _catalog_list(names, catalog_by_name):
    return [{"name": n, "source": catalog_by_name[n]} for n in sorted(names)]
