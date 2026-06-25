# 设计:refactor-server-app-by-domain

## 方案

### 1. 目标拓扑

```
server/
├── app.py                ~60   FastAPI 组装 + 中间件 + 路由 include + init_db()
│                               + 关键符号 re-export(给 tests/conftest.py 兼容)
├── config.py             ~60   从 env 读 DB_PATH / INGEST_KEY / ADMIN_KEY / TF_REQUIRE_TOKEN /
│                               READ_AUTH_OK / TRUST_PROXY / TF_HSTS / STATE_TTL_SECONDS /
│                               TRASH_DAYS / ADMIN_MAX_ROWS / ADMIN_RATE_* / WINDOW_DAYS /
│                               MAX_BODY / MAX_CONTENT / MAX_META / MAX_SKILL_NAME /
│                               PROFILE_KEYS / SENSITIVE_KEYS / SKILL_MODES /
│                               CATALOG_URL / CATALOG_TTL_SECONDS / CATALOG_*
│                               + 计算项 REPO_ROOT / FRONTEND_DIST / FRONTEND_INDEX /
│                               SHIMS_DIR / INSTALL_PATH / LLMS_PATH / ROBOTS_PATH / _MEDIA
├── db.py                 ~220  db() / init_db() / _ensure_skill_uses_schema /
│                               _maybe_prune / _maybe_prune_trash + 全局 _lock /
│                               共用工具 now_iso / _json / _sha / _clip
├── security.py           ~180  _CSP / _security_headers 中间件 / _key_eq / check_auth /
│                               check_admin + 限流器 _rate_lock/_rate_state/_rate_prune/
│                               _rate_retry_after/_rate_register_failure/_rate_register_success +
│                               _client_host / _req_is_https / _admin_actor / _audit / _audit_denied
├── identity.py           ~80   canon_operator / _norm_op / verify_operator + 内联依赖
├── catalog.py            ~150  _fetch_catalog / _parse_catalog_payload / _save_catalog_cache /
│                               _record_catalog_error / sync_catalog_once / _catalog_loop /
│                               _start_catalog_sync / _startup_catalog_sync /
│                               _load_catalog_cache / _catalog_context / _skill_source /
│                               _installed_skill_names / _catalog_list +
│                               模块状态 _catalog_lock/_catalog_state/_catalog_thread_started
├── shim.py               ~60   _shim_target / _build_shim_manifest / _SHIM_MANIFEST /
│                               _EXECUTABLE_SHIMS
├── profile.py            ~50   _skill_names / _skill_use_name / _skill_mode /
│                               load_profiles / load_shim_versions / reuse_map
└── routes/
    ├── __init__.py       0    空文件
    ├── ingest.py         ~150 router + enroll / ingest_event / delete_events(旧 DELETE)
    ├── admin.py          ~400 router + admin_inventory / admin_preview / admin_delete_data /
    │                          admin_trash / admin_restore / admin_export +
    │                          _validate_targets / _resolve_admin_targets / _preview_admin_resolution /
    │                          _purge / _restore_admin_batch / _admin_inventory +
    │                          _event_ids_for_sessions / _skill_keys_for_* / _session_ids_by_operator /
    │                          _session_ids_before_day / _expand_child_sessions / _fetch_*_rows /
    │                          _profile_keys_for_selector / _operators_from_rows /
    │                          _candidate_operator_norms / _first_day_changes / _identity_clears /
    │                          _delete_skill_rows / _delete_profile_rows / _insert_row /
    │                          _begin_admin_write / _recompute_derived / _active_sessions /
    │                          _active_sessions_all / _resolution_token / _rowdict / _marks /
    │                          _skill_key / _skill_key_s / _profile_key / _profile_key_s
    └── board.py          ~350 router + state / skills_stats / skill_detail / operator_detail /
    │                          agent_detail + _snapshot / metrics / leverage / skill_usage /
    │                          skills_overview / operator_detail_payload / skill_detail_payload /
    │                          _state_compute_or_cache + ACTIVE_ST / LIVE_ST / STALE_SECONDS /
    │                          CLOUD_RUNTIMES / _age / _parse / _iter_sessions / _day_cutoff +
    │                          _state_cache / _state_cache_lock
    └── onboarding.py     ~80  router + dashboard / _spa_index / spa_fallback /
                               install_sh / llms_txt / robots_txt / healthz /
                               shim_file / shim_manifest + _plain_file +
                               _SPA_BLOCKED_PREFIXES / _SPA_BLOCKED_PATHS
```

### 2. 关键技术点

#### 2.1 `server/app.py` 的「兼容 re-export」

`tests/conftest.py` 的开关:
```python
app.DB_PATH = ...
app.INGEST_KEY = ""
app.ADMIN_KEY = ""
app.ADMIN_MAX_ROWS = 200
app.TRASH_DAYS = 30
app.STATE_TTL_SECONDS = ...
app._state_cache_lock / app._state_cache
app._prune_state["n"] = 0
app.REQUIRE_TOKEN / app.READ_AUTH_OK / app.TRUST_PROXY
app._rate_lock / app._rate_state
app._catalog_thread_started / app._catalog_lock / app._catalog_state
app.init_db()
```

拆分后,这些符号实际定义在 `server/config.py`、`server/db.py`、`server/security.py`、`server/catalog.py`、
`server/routes/board.py` 内。`server/app.py` 末尾必须显式 re-export:

```python
# tests/conftest.py 兼容契约 — 不要改这一段(见 openspec/changes/archive/<id>/design.md §2.1)
from server.config import (DB_PATH, INGEST_KEY, ADMIN_KEY, ADMIN_MAX_ROWS,
                           TRASH_DAYS, STATE_TTL_SECONDS, REQUIRE_TOKEN,
                           READ_AUTH_OK, TRUST_PROXY)
from server.db import init_db, _prune_state, _lock
from server.security import _rate_lock, _rate_state
from server.catalog import (_catalog_lock, _catalog_state, _catalog_thread_started,
                            sync_catalog_once)
from server.routes.board import _state_cache, _state_cache_lock
```

**但**:Python 中 `from X import Y` 是绑定值,不是引用——后面 `app.DB_PATH = ...` 改的是 `server.app` 模块
的局部绑定,不会改 `server.config.DB_PATH`,模块内部使用 `config.DB_PATH` 时取到的还是旧值,导致测试失败。

**解法**:模块内部不要 `from server.config import DB_PATH` 后用裸名,而是 `from server import config`
后用 `config.DB_PATH`。Re-export 也改为 `import server.config as config; DB_PATH = config.DB_PATH` 不够,
要进一步在 `app.py` 装一个 `__getattr__` 模块代理:

```python
import server.config as _config
import server.db as _db
import server.security as _sec
import server.catalog as _cat
import server.routes.board as _board

_PROXIES = {
    "DB_PATH": (_config, "DB_PATH"),
    "INGEST_KEY": (_config, "INGEST_KEY"),
    # ... 全部 ~20 个符号
    "_state_cache": (_board, "_state_cache"),
    "_state_cache_lock": (_board, "_state_cache_lock"),
    "_rate_state": (_sec, "_rate_state"),
    # ...
    "init_db": (_db, "init_db"),
    "sync_catalog_once": (_cat, "sync_catalog_once"),
}

def __getattr__(name):
    if name in _PROXIES:
        mod, attr = _PROXIES[name]
        return getattr(mod, attr)
    raise AttributeError(name)

def __setattr__(name, value):  # 模块级 setattr 需绕一层
    if name in _PROXIES:
        mod, attr = _PROXIES[name]
        setattr(mod, attr, value)
    else:
        globals()[name] = value
```

**注意**:Python 模块没有 `__setattr__` 钩子;`app.DB_PATH = ...` 走的是 `module.__dict__[name] = value`
路径,**无法拦截**。

更稳的方案:**保留 `server/app.py` 作为「配置中心 + FastAPI 入口」**,把 `config.py` 内的可变常量
直接定义在 `server/app.py`,其他模块统一 `from server import app as _conf; _conf.DB_PATH` 来读。
这样 conftest 的 monkeypatch 直接生效。

具体 re-export 边界(更准确的拆分):

- **留在 `server/app.py` 顶层定义**(因为 conftest 直接赋值,且其他模块要在调用时实时读取):
  `DB_PATH`、`INGEST_KEY`、`ADMIN_KEY`、`ADMIN_MAX_ROWS`、`TRASH_DAYS`、`STATE_TTL_SECONDS`、
  `REQUIRE_TOKEN`、`READ_AUTH_OK`、`TRUST_PROXY`、`_lock`、`_state_cache`、`_state_cache_lock`、
  `_rate_lock`、`_rate_state`、`_prune_state`、`_catalog_lock`、`_catalog_state`、
  `_catalog_thread_started`、`init_db`、`sync_catalog_once`。
- 其他模块通过 `from server import app` 获取这些值(import 在函数体内或顶部均可,关键是**调用时读**)。
- 这意味着 `config.py` 实际只放**真常量**(PROFILE_KEYS / SENSITIVE_KEYS / MAX_BODY 等不被 conftest
  改的);可变开关留在 `app.py`。

实施时按这条更稳的边界来:**config.py 只放真常量,可变开关全留在 app.py**。
此时 `app.py` 行数会膨胀到 ~150 而非 60,但换来 conftest 完全不动 / 测试零修改的强保证。
本变更接受这个 trade-off。

#### 2.2 全局 `_lock`、`_state_cache` 等模块状态

- `_lock`(全局写锁)留在 `app.py`,所有写路径模块通过 `from server import app; with app._lock:` 抢锁。
- `_state_cache` / `_state_cache_lock` 同样留在 `app.py`,`routes/board.py` 的 `_state_compute_or_cache`
  从 `app` 读取。
- `_rate_state` / `_rate_lock` 同。
- `_catalog_state` / `_catalog_lock` / `_catalog_thread_started` 同。
- `_prune_state` 同。

这些都是「全局唯一进程内状态」,统一放 `app.py` 既符合「单一可变点」原则,也保留 conftest 兼容。

#### 2.3 路由注册

每个 `routes/<domain>.py` 定义一个 `router = APIRouter()`,装饰器全部改为 `@router.get/post/delete`。
`app.py` 在 FastAPI 实例化后 `app.include_router(ingest_router, ...)` 四次。
中间件 `_security_headers` 仍写在 `app.py`(它是全局的)。
`StaticFiles` mount(`/assets`)也留在 `app.py`。
`startup` event handler(`_startup_catalog_sync`)留在 `app.py`,内部 call `catalog.sync_catalog_once`。

#### 2.4 `init_db()` 与模块导入序

`init_db()` 当前在 `app.py` 末尾被同步调用。拆分后:
- `init_db` 函数体搬到 `db.py`(它依赖 schema、依赖 catalog/identity 表)。
- `app.py` 模块加载尾部仍调 `init_db()`,确保 `import server.app` 时 DB 初始化照旧。
- 所有 `routes/*` 都 `from server import db` 后用 `db.db()` 取连接。

#### 2.5 `_SHIM_MANIFEST` 初始化时机

`_SHIM_MANIFEST = _build_shim_manifest()` 当前在模块加载时执行,扫盘 `shims/`。
搬到 `shim.py` 后,模块加载即扫盘——保持现状(测试已能通过)。

### 3. 迁移顺序(单 PR 内 12 个小 commit)

每一步都跑 `pytest -q`,绿了才进下一步:

1. 创建 `server/config.py`,搬**真常量**(`PROFILE_KEYS`/`SENSITIVE_KEYS`/`MAX_*`/`SKILL_MODES`/
   `WINDOW_DAYS`/`CATALOG_*` 等)。可变开关仍留 app.py。
2. 创建 `server/db.py`,搬 `db()`/`init_db()`/`_ensure_skill_uses_schema`/`_maybe_prune`/
   `_maybe_prune_trash` + 共用工具 `now_iso`/`_json`/`_sha`/`_clip`。
3. 创建 `server/security.py`,搬 CSP / 中间件 / `check_auth` / `check_admin` / 限流器 / `_audit` 等;
   `_rate_lock` / `_rate_state` 仍在 app.py(模块状态),security.py 从 app 读。
4. 创建 `server/identity.py`,搬 `canon_operator` / `_norm_op` / `verify_operator`。
5. 创建 `server/catalog.py`,搬 catalog 整组;`_catalog_*` 模块状态留 app.py。
6. 创建 `server/shim.py`,搬 `_build_shim_manifest` / `_SHIM_MANIFEST` / `_EXECUTABLE_SHIMS`。
7. 创建 `server/profile.py`,搬 skill helpers + `load_profiles` / `load_shim_versions` / `reuse_map`。
8. 创建 `server/routes/__init__.py`(空)。
9. 创建 `server/routes/ingest.py`,搬 enroll/ingest/delete 三个端点 + 装 router。
10. 创建 `server/routes/admin.py`,搬 6 个 admin 端点 + 整个清理算子族。
11. 创建 `server/routes/board.py`,搬 5 个 board 端点 + `_snapshot`/`metrics`/`*_payload`;
    `_state_cache` 留 app.py。
12. 创建 `server/routes/onboarding.py`,搬 SPA / shim / install / healthz。
    最后 `app.py` 只剩:imports、FastAPI 实例、中间件、`include_router` × 4、startup hook、
    `init_db()` 调用、可变开关定义 + 模块状态。

每个 commit 信息形如 `refactor(server): extract catalog module (refactor-server-app-by-domain)`。

### 4. `tests/test_module_boundary.py`(新建,守门)

```python
"""拆分后的结构守门:防回归。"""
import importlib
import os

def test_app_py_under_100_lines():
    p = os.path.join(os.path.dirname(__file__), "..", "server", "app.py")
    n = sum(1 for _ in open(p))
    assert n <= 150, f"server/app.py {n} lines, expected <= 150"

def test_route_modules_import_independently():
    for mod in ("server.routes.ingest", "server.routes.admin",
                "server.routes.board", "server.routes.onboarding"):
        importlib.import_module(mod)

def test_app_reexports_conftest_contract():
    import server.app as app
    # conftest.py 直接访问的符号必须可读可写
    for name in ("DB_PATH", "INGEST_KEY", "ADMIN_KEY", "ADMIN_MAX_ROWS",
                 "TRASH_DAYS", "STATE_TTL_SECONDS", "REQUIRE_TOKEN",
                 "READ_AUTH_OK", "TRUST_PROXY", "_lock",
                 "_state_cache", "_state_cache_lock",
                 "_rate_lock", "_rate_state",
                 "_prune_state",
                 "_catalog_lock", "_catalog_state", "_catalog_thread_started",
                 "init_db", "sync_catalog_once"):
        assert hasattr(app, name), f"server.app.{name} missing — conftest will break"

def test_submodules_no_toplevel_app_import():
    """子模块只能在函数体内 from server import app,不能写在文件顶层(否则循环 import)。
    粗粒度字符串检查即可,不必 AST。"""
    import pathlib
    root = pathlib.Path(__file__).parent.parent / "server"
    for path in list(root.glob("*.py")) + list((root / "routes").glob("*.py")):
        if path.name == "app.py":
            continue
        toplevel = []
        for line in path.read_text().splitlines():
            stripped = line.lstrip()
            if stripped.startswith(("def ", "class ", "async def ")):
                break  # 进入函数/类体之后的 import 允许
            if "from server import app" in stripped or "import server.app" in stripped:
                toplevel.append(line)
        assert not toplevel, f"{path}: top-level app import will deadlock; defer to function body"
```

注意第一条阈值用 150 而非 100,理由见 §2.1——可变开关留在 app.py 后行数会膨胀到 ~150。
若实施后小于 100,把阈值调到 120 给后续余量。

### 5. `server/AGENTS.md`(新建目录级约定)

```markdown
# server/ 目录约定

本目录的代码按 openspec/specs/ 的业务域物理分文件。改动定位规则:

| 改 spec | 主要触碰文件 |
|---|---|
| admin/spec.md | routes/admin.py + 共用 db.py / security.py |
| board/spec.md | routes/board.py + profile.py + db.py |
| ingest/spec.md | routes/ingest.py + identity.py + db.py |
| onboarding/spec.md | routes/onboarding.py + shim.py |

跨域共享模块:config / db / security / identity / catalog / profile / shim。

**全局可变状态**(`_lock`、`_state_cache`、`_rate_state`、`_catalog_state`、`_prune_state`)
集中定义在 app.py,其他模块通过 `from server import app` 访问。这是为了让 tests/conftest.py
的 monkeypatch 路径保持单一,不要把它们分散到子模块。

修改后必须跑:
- `pytest -q` 全绿
- `python -m coverage run --source=server -m pytest && python -m coverage report` ≥ 95%
- `wc -l server/app.py` ≤ 150
- `wc -l server/*.py server/routes/*.py` 看总行数与各文件
```

## 权衡

- **按 spec 域 vs 三层架构**:选 spec 域。三层(routes/services/repositories)更「工程化」,但当前规模
  (1840 有效行)三层会产生很多 1-2 行的转发函数,加导航成本而非降。spec 域 1:1 对应事实源,直接读懂。
- **`app.py` 留可变开关 vs 全部搬走**:留下。Python 模块 `__getattr__/__setattr__` 不能完整代理给子模块,
  强行抽走会破坏 conftest 的 monkeypatch 契约,得不偿失。
- **是否同时引入 `Depends(get_db)` 模式**:不引入。本变更只搬位置,不改注入风格。引入会让 diff 既是
  搬运又是注入改造,review 失焦。
- **是否拆 `tests/`**:已经按域分文件了(Change A 进一步对齐),本次不动测试组织。

## 风险

1. **conftest.py 兼容性破坏**:漏 re-export 某个符号,导致 155 个测试一片红。
   - 缓解:`tests/test_module_boundary.py` 第三条用 hasattr 列表守门,实施时一次性补齐。
   - 缓解:每搬一个模块跑一次 pytest,红就立刻退回。
2. **循环引用**:`security.py` 用 `app._rate_state`,`app.py` 又 include 路由(路由 import security)。
   - 缓解:`app.py` 不 import `security`(中间件直接 `app.middleware("http")(_security_headers)`
     可以从 security 模块拿函数),所有 `from server import app` 都在函数体内做(延迟 import)。
3. **`init_db()` 调用时机变化**:拆分后若 `db.py` 被 `routes/admin.py` import 但 `init_db` 还没跑,
   首请求会撞空表。
   - 缓解:`app.py` 模块加载尾部继续调 `init_db()`,与现状一致。
4. **`_SHIM_MANIFEST` 的扫盘移到 `shim.py`,某些测试可能假设它在 `app` 命名空间**。
   - 缓解:`app.py` 加 `from server.shim import _SHIM_MANIFEST` re-export 兜底。
5. **PR diff 巨大,review 难**:2648 行的搬运 PR。
   - 缓解:12 个小 commit,每个 commit 只搬一个模块、commit message 写明搬了什么;
     PR 描述放 `git log --stat` 与 `wc -l server/**/*.py` 对照。

## 待决项

1. **是否引入 `pyproject.toml` 集中放 `[tool.pytest.ini_options]` / `[tool.coverage.*]`**——
   Change A 已有同款待决项,两 change 取齐即可。
2. **shim 顶层 import 时扫盘**(`_SHIM_MANIFEST = _build_shim_manifest()` 立即执行)——
   是否改成 lazy?本变更**不改**,保持现状,留给后续 change 视性能数据决定。
