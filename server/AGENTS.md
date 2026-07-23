# server/ 目录约定

本目录的代码按 `openspec/specs/` 的业务域物理分文件。改动定位规则:

| 改 spec | 主要触碰文件 |
|---|---|
| admin/spec.md | routes/admin.py + 共用 db.py / security.py |
| board/spec.md | routes/board.py + profile.py + catalog.py + db.py |
| ingest/spec.md | routes/ingest.py + identity.py + db.py |
| onboarding/spec.md | routes/onboarding.py + shim.py + (path constants in app.py) |

## 跨域共享模块

- `config.py`:不可变常量(`PROFILE_KEYS` / `MAX_*` / `WINDOW_DAYS` / `SKILL_MODES` /
  `ACTIVE_ST` / `STALE_SECONDS` / `REPO_ROOT` / `FRONTEND_DIST` / `SHIMS_DIR` / catalog 默认 URL 等)
  + `_env_int` / `_env_float`。
- `db.py`:连接 / schema / 迁移 / `_maybe_prune` / `_audit` + 共用工具
  (`now_iso` / `now_utc` / `stats_now` / `stats_today` / `stats_day` / `stats_day_for` /
  `_sha` / `_json` / `_clip` / `_age` / `_parse` / `_day_cutoff`)。`skill_uses` 上的 SKILLS overview
  组合索引也在这里幂等创建。
- `security.py`:CSP / 安全响应头中间件 / 鉴权 / 限流 / `_audit_denied`。
- `identity.py`:`canon_operator` / `verify_operator` / `_norm_op`。
- `profile.py`:skill 名规范化 + `load_profiles` / `load_shim_versions` / `reuse_map`。
- `catalog.py`:tranfu-skills catalog 同步与缓存,并集中解析 catalog/profile 的
  `display_name/display_name_zh`;公司库字段优先,profile 补缺,输出双语可用回退值。
- `shim.py`:`/shims` 内容版本与文件清单(模块加载即扫盘)。

## 全局可变状态(集中在 server/app.py)

下列符号是「单一可变点」,所有子模块通过 `from server import app` 在**函数体内**延迟读取
(顶层延迟会与 `app.include_router(...)` 产生循环 import):

- 可变开关:`DB_PATH`、`INGEST_KEY`、`ADMIN_KEY`、`ADMIN_MAX_ROWS`、`TRASH_DAYS`、
  `STATE_TTL_SECONDS`、`HEARTBEAT_BATCH_SECONDS`、`REQUIRE_TOKEN`、`READ_AUTH_OK`、`TRUST_PROXY`、`HSTS_FORCE`、
  `ADMIN_RATE_*`、`ADMIN_LOCK_*`。
- 路径常量(测试 monkeypatch 目标):`FRONTEND_INDEX`、`INSTALL_PATH`、`LLMS_PATH`、`ROBOTS_PATH`。
- 全局锁与缓存:`_lock`、`_catalog_lock`、`_catalog_state`、`_catalog_thread_started`。

`_state_cache` / `_state_cache_lock`(/api/state 与 SSE 状态流缓存)、心跳 batch pending map 与 `_rate_lock` / `_rate_state`(限流器内存态)
分别由 `routes/board.py`、`routes/ingest.py` 与 `security.py` 持有;`server/app.py` 末尾 `from … import …` 把它们
re-export 到 `app` 命名空间,使 `tests/conftest.py` 的 `app._state_cache.update(...)` 与
`app._rate_state.clear()` 在同一对象上生效。

## 路由模块约定

- 每个 `routes/<domain>.py` 顶部定义 `router = APIRouter()`,所有端点用 `@router.get/post/delete`。
- `server/app.py` 末尾 `include_router` 四次注册全部路由。
- 子模块顶部**不得**写 `from server import app` 或 `import server.app`——会触发循环。
  当需要读 `app.X`(可变开关 / 全局状态)时,把 `from server import app` 放在调用它的函数体内。
- `/api/skills` overview 的重聚合逻辑必须留在 `routes/board.py` 内,优先用 SQLite 组合索引和 SQL
  预聚合减少 Python 侧处理行数;缓存只能作为 SQL/索引达标失败后的有界短 TTL 第二层。
- 含 Skill 的读侧对象必须同时返回 slug 与 `display_name/display_name_zh`;多 Skill payload 另返回
  `skill_names`。展示字段不得替代 slug 参与 SQL、URL、选择器、删除或 source 归因。
- `/api/state` 的 `agent_overview` 必须在最终身份卡片之后聚合,遵守 `operator + agent||runtime` 合并口径;
  其 90 天日序列、Runtime/操作员分组与 summary 必须复用同一 state snapshot。`/api/agents` 同样必须从该最终快照身份卡片生成指定窗口统计,
  不得复制身份/profile/质量计算;`ranking[]`、`agents[]` 与每日 identity 分段都必须显式返回 `operator`。
- 活跃时长必须由 `routes/board.py` 先按 session 以 `STALE_SECONDS` 拆连续段,再按最终身份对区间取并集并按上海日切分;
  `/api/state`、`/api/agents` 与 Agent 详情不得另算。`routes/ingest.py` 对同状态/同步骤的长断档恢复必须落新行,
  且任何新事件行插入前都要把 pending batch 的最后确认心跳固化为旧段末点。SQLite 与 pending 同时存在时取较新值;
  同一事件 pending 入队必须单调不减;ingest/flush 同时需要锁时固定按
  `app._lock → _heartbeat_pending_lock` 获取,SQLite commit 成功后才清 pending,后台 flush 单轮异常后继续重试。
- `tests/test_module_boundary.py` 守门:
  - `server/app.py` 行数 ≤ 220。
  - `routes/*.py` 可独立 import。
  - `app` 命名空间下的 conftest 兼容符号全部可访问。
  - 子模块顶层不出现 `from server import app`。

## 时间源(monkeypatch 友好)

`server/app.py` 顶部 `from datetime import datetime, timezone, timedelta` 让
`tests/test_skills_stats_page.py` 等能 `monkeypatch.setattr(app_mod, "datetime", FixedDatetime)`
锁死「现在时间」。子模块内部如需读「当前 UTC instant」或「当前统计日」,**不要**直接
`datetime.now(...)`(那会用子模块自己的 datetime 绑定,不受 monkeypatch 影响);改用
`db.py` 的 `now_utc()` / `now_iso()` / `stats_now()` / `stats_today()` / `stats_day()` /
`_day_cutoff(...)`(它们内部都走 `app.datetime` 间接读)。默认统计日口径为 `Asia/Shanghai`;
具体时间戳仍保存 UTC instant。

## 修改后必跑

- `python -m pytest -q` 全绿(预期 252+)。
- `python -m coverage run -m pytest && python -m coverage report --include='server/**/*.py'`
  各文件行覆盖 ≥ 95%(`.coveragerc` 守门)。
- `wc -l server/app.py` ≤ 220。
- `wc -l server/*.py server/routes/*.py` 看总行数与各文件,确认未失控膨胀。
