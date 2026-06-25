"""
TRANFU//AGENTS — collector server. Implements TATP v0.1 (see ../PROTOCOL.md).

Ingest:
  POST /v1/enroll        admin (X-TF-Key) issues a per-operator token (one-time)
  POST /v1/events        JSON heartbeat (all agents via shim / MCP reporter)
                         May carry OPTIONAL profile fields (models, config, mcp,
                         skills, integrations, about, tips, cf, instructions,
                         memory). instructions+memory are sensitive -> opt-in and
                         gated by read-side auth (see PROTOCOL.md §5).
  DELETE /v1/events      legacy admin (X-TF-Admin-Key) cleanup — drop events by session_ids or
                         by identity (operator[/agent/runtime]); optional profile
                         clear. For pruning test/junk sessions off the board.

Read:
  GET  /api/state        snapshot the dashboard polls (sessions + profile +
                         computed quality + leverage + 90d activity)
  GET  /api/skills       SKILLS overview (skill and operator aggregates)
  GET  /api/skill/{name} single skill detail
  GET  /api/operator/{name}
                         single operator skill-usage detail
  GET  /api/agent/{key}  single agent detail (key = "operator::agentOrRuntime")
  GET  /api/admin/inventory
  POST /api/admin/preview
  DELETE /api/admin/data
  GET  /api/admin/trash
  POST /api/admin/restore
                         admin cleanup (X-TF-Admin-Key)
  POST /api/admin/export consistent SQLite snapshot download (X-TF-Admin-Key);
                         whole-DB export, requires body {"confirm":"EXPORT"}
  GET  /                 the dashboard
  GET  /healthz

Storage is SQLite (WAL) at $TF_DB, default ./tf.db. No external services.
"""
import os, sys, json, sqlite3, time, threading, hashlib, hmac, secrets, urllib.request, uuid
from datetime import datetime, timezone, timedelta
from contextlib import closing
from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

# 不变常量 + 工具函数集中在 server.config(由 refactor-server-app-by-domain 引入)。
from server.config import (
    _env_int, _env_float,
    _MEDIA, _EXECUTABLE_SHIMS, _WEAK_ADMIN_KEYS, _RATE_MAX_ENTRIES,
    PROFILE_KEYS, SENSITIVE_KEYS,
    MAX_BODY, MAX_CONTENT, MAX_META, MAX_SKILL_NAME, WINDOW_DAYS, SKILL_MODES,
    CATALOG_URL, CATALOG_TTL_SECONDS, CATALOG_FETCH_TIMEOUT,
    CATALOG_COMPANY_TYPES, CATALOG_SOURCE_UNKNOWN,
)

# ---- 可变开关(测试通过 monkeypatch 改;留在本文件)----
DB_PATH = os.environ.get("TF_DB", "tf.db")
INGEST_KEY = os.environ.get("TF_KEY", "")          # "" = no auth (dev only)
ADMIN_KEY = os.environ.get("TF_ADMIN_KEY", "")     # "" = admin endpoints disabled
# per-operator attribution: when on, every event MUST carry a valid X-TF-Token
# whose bound operator matches the body's `operator` (TATP v0.1 §4).
REQUIRE_TOKEN = os.environ.get("TF_REQUIRE_TOKEN", "0") == "1"
# read-side auth gate for content capture (TATP v0.1 §5). Sensitive fields are
# stored ONLY when read access is protected: either the app read-key is set, or
# the operator asserts an edge gate (Cloudflare Access / Caddy) via TF_READ_AUTH=1.
READ_AUTH_OK = bool(os.environ.get("TF_READ_KEY")) or os.environ.get("TF_READ_AUTH", "0") == "1"

# ---- 路径常量(测试 monkeypatch FRONTEND_INDEX/INSTALL_PATH/LLMS_PATH/ROBOTS_PATH;留在本文件)----
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIST = os.path.join(REPO_ROOT, "frontend", "dist")
FRONTEND_INDEX = os.path.join(FRONTEND_DIST, "index.html")
SHIMS_DIR = os.path.join(REPO_ROOT, "shims")
INSTALL_PATH = os.path.join(REPO_ROOT, "install.sh")
LLMS_PATH = os.path.join(REPO_ROOT, "llms.txt")
ROBOTS_PATH = os.path.join(REPO_ROOT, "robots.txt")

# 启动自检:管理钥匙若过短或为常见示例值,在线猜测成本极低 —— 打印告警(不阻断)。
if ADMIN_KEY and (len(ADMIN_KEY) < 16 or ADMIN_KEY.lower() in _WEAK_ADMIN_KEYS):  # pragma: no cover
    print("[tranfu] WARNING: TF_ADMIN_KEY 偏弱(过短或为常见示例值),管理接口可被在线"
          "猜测;请用 `openssl rand -hex 32` 生成强随机值。", file=sys.stderr)

app = FastAPI(title="TRANFU//AGENTS")

# CSP / 中间件 / 鉴权 / 限流 / 审计 全部搬到 server.security。
from server.security import (
    _CSP, _security_headers,
    _key_eq, check_auth, check_admin,
    _client_host, _req_is_https,
    _rate_lock, _rate_state, _rate_prune, _rate_retry_after,
    _rate_register_failure, _rate_register_success,
    _admin_actor, _audit_denied,
)

# 注册全局中间件(middleware 装饰器等价为下面这一行)。
app.middleware("http")(_security_headers)

app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets"), check_dir=False), name="assets")
_lock = threading.Lock()
_catalog_lock = threading.Lock()
# _state_cache / _state_cache_lock 搬到 server.routes.board;
# re-export 见末尾(必须在 board.py import 之后,因此推迟)。


STATE_TTL_SECONDS = _env_float("TF_STATE_TTL", "1.5")
TRASH_DAYS = _env_int("TF_TRASH_DAYS", 30)
ADMIN_MAX_ROWS = _env_int("TF_ADMIN_MAX_ROWS", 200)

# 反代场景:仅当声明前置可信反代时,才信任 X-Forwarded-For 提取真实客户端 IP。
# 默认关 —— XFF 可被请求方随意伪造,误信会让攻击者绕过按 IP 的限流。
TRUST_PROXY = os.environ.get("TF_TRUST_PROXY", "0") == "1"
# 管理接口防爆破限流(进程内,单 worker 前提;见 design.md「权衡」)。
ADMIN_RATE_MAX = _env_int("TF_ADMIN_RATE_MAX", 5)        # 窗口内允许的验钥失败次数
ADMIN_RATE_WINDOW = _env_int("TF_ADMIN_RATE_WINDOW", 60)  # 滑窗长度(秒)
ADMIN_LOCK_BASE = _env_int("TF_ADMIN_LOCK_BASE", 30)     # 首次封锁时长(秒),其后翻倍
ADMIN_LOCK_MAX = _env_int("TF_ADMIN_LOCK_MAX", 3600)     # 封锁时长封顶(秒)
# 生产 HTTPS 部署才发 HSTS:显式 TF_HSTS=1,或经可信反代识别到 https。
HSTS_FORCE = os.environ.get("TF_HSTS", "0") == "1"
_catalog_state = {"items": None, "fetched_at": None, "error": None, "last_attempt": None}
_catalog_thread_started = False


# Shim 清单生成 搬到 server.shim。
from server.shim import _shim_target, _build_shim_manifest


# DB schema / 迁移 / 共用工具(now_iso/_sha/_json/_clip/db/init_db)与保留策略
# (_maybe_prune/_maybe_prune_trash)+ _audit 全部搬到 server.db。
from server.db import (
    now_iso, _sha, _json, _clip,
    db, init_db, _ensure_skill_uses_schema,
    _audit, _maybe_prune, _maybe_prune_trash, _prune_state,
)


# 身份归一化与令牌校验 搬到 server.identity。
from server.identity import canon_operator, verify_operator, _norm_op


# Skill 名规范化 + profile 加载 + 复用计算 搬到 server.profile。
from server.profile import (
    _skill_names, _skill_use_name, _skill_mode,
    load_profiles, load_shim_versions, reuse_map,
)


# _SHIM_MANIFEST 已由 server.shim 顶层固化(与原行为一致);此 import 同时让 app
# 命名空间下仍可访问该名(onboarding 路由读它)。
# 占位:导入语句见文件顶部 from server.shim import _shim_target, _build_shim_manifest;
# _SHIM_MANIFEST 通过下面这一行 re-export。
from server.shim import _SHIM_MANIFEST  # noqa: E402,F401


# Catalog 整组搬到 server.catalog。
from server.catalog import (
    _catalog_source, _parse_catalog_payload, _fetch_catalog,
    _save_catalog_cache, _record_catalog_error, sync_catalog_once,
    _catalog_loop, _start_catalog_sync, _startup_catalog_sync,
    _load_catalog_cache, _catalog_context, _skill_source,
    _installed_skill_names, _catalog_list,
)

# startup hook 注册;实际逻辑由 catalog 模块持有。
app.add_event_handler("startup", _startup_catalog_sync)


# 路由按 spec 域分包注册(由 refactor-server-app-by-domain 引入)。
from server.routes import ingest as _ingest_routes  # noqa: E402
from server.routes import admin as _admin_routes  # noqa: E402
from server.routes import board as _board_routes  # noqa: E402
from server.routes import onboarding as _onboarding_routes  # noqa: E402
app.include_router(_ingest_routes.router)
app.include_router(_admin_routes.router)
app.include_router(_board_routes.router)
app.include_router(_onboarding_routes.router)

# onboarding 命名空间 re-export(tests/test_onboarding.py 通过 _spa_index / spa_fallback 等读)。
from server.routes.onboarding import (  # noqa: E402,F401
    _spa_index, _plain_file, _SPA_BLOCKED_PREFIXES, _SPA_BLOCKED_PATHS,
    healthz, dashboard, install_sh, llms_txt, robots_txt,
    shim_manifest, shim_file, spa_fallback,
)

# conftest 兼容 re-export(必须在 board import 之后,使 app._state_cache_lock 与 board 内部同一对象)。
from server.routes.board import (  # noqa: E402,F401
    _state_cache, _state_cache_lock,
    _snapshot, _state_compute_or_cache, metrics, leverage, skill_usage,
    skills_overview, operator_detail_payload, skill_detail_payload,
    state, skills_stats, skill_detail, operator_detail, agent_detail,
)

# _day_cutoff 搬到 server.db(admin 与 board 共享)。
from server.db import _day_cutoff  # noqa: E402,F401




init_db()

if __name__ == "__main__":  # pragma: no cover  — 生产由 uvicorn CLI 拉起
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8788")))
