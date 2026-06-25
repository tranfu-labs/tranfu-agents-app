# 任务:refactor-server-app-by-domain

> 前置:`add-server-app-test-baseline` 必须已归档,`server/app.py` 行覆盖 ≥ 95%。

## 准备
- [ ] 确认 `add-server-app-test-baseline` 已归档(`openspec/changes/archive/<date>-add-server-app-test-baseline/`)。
- [ ] 从 main 拉新分支 `refactor/server-app-by-domain`。
- [ ] 跑一次基线 `pytest -q` 确认 100% 绿;记录测试数与耗时。
- [ ] 跑一次基线 `coverage report --include='server/app.py'` 确认 ≥ 95%。

## 模块抽取(每步搬完跑 `pytest -q`,绿了才进下一步)

> **关键边界**:可变开关(DB_PATH/INGEST_KEY/ADMIN_KEY 等)与全局可变状态(`_lock`/`_state_cache`/
> `_rate_state`/`_catalog_state`/`_prune_state`)必须**留在 `server/app.py`**,见 design.md §2.1。
> 子模块通过 `from server import app` 在调用时实时读。

- [ ] **C1** 新建 `server/config.py`,从 `app.py` 搬**真常量**:
      `PROFILE_KEYS` / `SENSITIVE_KEYS` / `MAX_BODY` / `MAX_CONTENT` / `MAX_META` / `MAX_SKILL_NAME` /
      `WINDOW_DAYS` / `SKILL_MODES` / `_WEAK_ADMIN_KEYS` / `CATALOG_URL` / `CATALOG_TTL_SECONDS` /
      `CATALOG_FETCH_TIMEOUT` / `CATALOG_COMPANY_TYPES` / `CATALOG_SOURCE_UNKNOWN` /
      `_EXECUTABLE_SHIMS` / `_MEDIA` / `_RATE_MAX_ENTRIES` /
      路径常量 `REPO_ROOT` / `FRONTEND_DIST` / `FRONTEND_INDEX` / `SHIMS_DIR` / `INSTALL_PATH` /
      `LLMS_PATH` / `ROBOTS_PATH`。
      app.py 内引用改为 `from server.config import ...`。
- [ ] **C2** 新建 `server/db.py`,搬 `db()` / `init_db()` / `_ensure_skill_uses_schema` /
      `_maybe_prune` / `_maybe_prune_trash` + 共用工具 `now_iso` / `_json` / `_sha` / `_clip`。
      `app.py` 末尾仍保留 `init_db()` 调用。
- [ ] **C3** 新建 `server/security.py`,搬 `_CSP` / `_security_headers` 中间件函数 / `_key_eq` /
      `check_auth` / `check_admin` + 限流器辅助(`_rate_prune` / `_rate_retry_after` /
      `_rate_register_failure` / `_rate_register_success`)+ `_client_host` / `_req_is_https` /
      `_admin_actor` / `_audit` / `_audit_denied`。`_rate_lock` / `_rate_state` 仍留 app.py,
      security 模块通过 `from server import app` 引用。
- [ ] **C4** 新建 `server/identity.py`,搬 `canon_operator` / `_norm_op` / `verify_operator`。
- [ ] **C5** 新建 `server/catalog.py`,搬 `_fetch_catalog` / `_parse_catalog_payload` /
      `_save_catalog_cache` / `_record_catalog_error` / `sync_catalog_once` / `_catalog_loop` /
      `_start_catalog_sync` / `_startup_catalog_sync` / `_load_catalog_cache` / `_catalog_context` /
      `_skill_source` / `_installed_skill_names` / `_catalog_list`。
      `_catalog_lock` / `_catalog_state` / `_catalog_thread_started` 留 app.py。
- [ ] **C6** 新建 `server/shim.py`,搬 `_shim_target` / `_build_shim_manifest` / `_SHIM_MANIFEST`。
      app.py 保留 `from server.shim import _SHIM_MANIFEST` re-export 兜底(test_module_boundary 守门)。
- [ ] **C7** 新建 `server/profile.py`,搬 `_skill_names` / `_skill_use_name` / `_skill_mode` /
      `load_profiles` / `load_shim_versions` / `reuse_map`。
- [ ] **C8** 新建 `server/routes/__init__.py`(空文件,标识包)。
- [ ] **C9** 新建 `server/routes/ingest.py`,搬 `enroll` / `ingest_event` / `delete_events`(旧 DELETE)。
      装饰器全部改为 `@router.post/delete`,文件顶部 `router = APIRouter()`。
- [ ] **C10** 新建 `server/routes/admin.py`,搬 6 个 admin 端点 + 整个清理算子族(见 design.md §1)。
- [ ] **C11** 新建 `server/routes/board.py`,搬 5 个 board 端点 + `_snapshot` / `metrics` /
      `leverage` / `skill_usage` / `skills_overview` / `operator_detail_payload` /
      `skill_detail_payload` / `_state_compute_or_cache` + 常量 `ACTIVE_ST` / `LIVE_ST` /
      `STALE_SECONDS` / `CLOUD_RUNTIMES` + 工具 `_age` / `_parse` / `_iter_sessions` / `_day_cutoff`。
      `_state_cache` / `_state_cache_lock` 留 app.py。
- [ ] **C12** 新建 `server/routes/onboarding.py`,搬 SPA / shim / install / healthz +
      `_plain_file` + `_SPA_BLOCKED_PREFIXES` / `_SPA_BLOCKED_PATHS`。
- [ ] **C13** `server/app.py` 最终化:仅剩
      ① import 子模块;② 可变开关 + 模块状态定义;③ FastAPI 实例化;④ 中间件;
      ⑤ StaticFiles mount;⑥ `include_router` × 4;⑦ startup hook;⑧ 末尾 `init_db()` 调用。
      期望行数 ≤ 150。

## 守门测试
- [ ] 新建 `tests/test_module_boundary.py`(见 design.md §4):
      `test_app_py_under_100_lines`(阈值 150)、`test_route_modules_import_independently`、
      `test_app_reexports_conftest_contract`、`test_submodules_no_toplevel_app_import`
      (后者守门:子模块顶层不得 `from server import app`,只能函数体内延迟 import,防循环)。

## 文档
- [ ] 新建 `server/AGENTS.md`(见 design.md §5),说明文件 ↔ spec 域映射、修改后必跑命令。
- [ ] 更新仓库根 `AGENTS.md` 的「目录结构」节,把 `server/app.py` 一行展开为子模块列表。

## 验收
- [ ] `pytest -q` 全绿,测试数与基线一致(155 + Change A 的 ~35 + 本变更的 4 守门 ≈ 194)。
- [ ] `wc -l server/app.py` ≤ 150。
- [ ] `wc -l server/*.py server/routes/*.py` 总行数 ≤ 2200(比 2648 略减,因去除重复 boilerplate)。
- [ ] `python -m coverage run --source=server -m pytest && python -m coverage report` 仍 ≥ 95%。
- [ ] `grep -E '^def ' server/app.py` 只剩组装/启动类(`_security_headers` 与 startup hook 函数)。

## AI 验证流程
- [ ] 本地 `uvicorn server.app:app --port 8788` 启动无 ImportError。
- [ ] `curl -s localhost:8788/healthz` → `ok`。
- [ ] `curl -s localhost:8788/api/state | jq 'keys'` 与基线一致(`["feed","leverage","now","sessions","shim","skills","totals"]`)。
- [ ] `curl -s localhost:8788/shims/manifest | jq '.version'` 非空。
- [ ] 让另一个 agent 抽 PR diff 的 2-3 个 commit 看,确认每个 commit 只做「搬运 + import 调整」,
      没有改业务逻辑。

## 文档与归档
- [ ] 实施完毕、验收通过后,按 `openspec/changes/AGENTS.md` 的「归档」节执行:
      ① 本目录移入 `archive/<YYYY-MM-DD>-refactor-server-app-by-domain/`;
      ② `spec-delta/admin/spec.md`、`spec-delta/board/spec.md`、`spec-delta/ingest/spec.md`、
         `spec-delta/onboarding/spec.md` 各自合并进 `openspec/specs/<domain>/spec.md`
         (更新「事实来源」段落的模块路径);
      ③ 本变更**无 wireframes.md**,跳过线框图回流。
- [ ] `git commit -m "refactor(server): split app.py by spec domain (refactor-server-app-by-domain)"`
      作为 PR 的整合提交;有 remote 时**问用户**是否 push,不擅自推。
