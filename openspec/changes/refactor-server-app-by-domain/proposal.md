# 变更提案:refactor-server-app-by-domain(按 spec 域拆分 server/app.py)

- 状态:Proposed
- 关联:`server/app.py`(2648 行)、`openspec/specs/{admin,board,ingest,onboarding}/spec.md`、
  `tests/conftest.py`(`import app` 入口契约)、`tests/test_*`(行为契约)
- 前置依赖:`add-server-app-test-baseline` 必须先归档完毕(`server/app.py` 行覆盖 ≥ 95%)
- 触发事件:2026-06-25 用户复审 server/app.py 时指出「2000+ 行单文件肯定不对」。
  对照 `openspec/specs/` 已有的 4 个域(admin / board / ingest / onboarding),发现 `server/app.py` 实际是
  4 个独立业务域的实现挤在一个文件里,**拆分边界天然存在**——只需让代码物理结构对齐已有的事实源结构。

## 背景 / 问题
`server/app.py` 已增长到 2648 行,横跨四个业务域:

| 域 | 现存代码块 |
|---|---|
| ingest | `/v1/enroll`、`/v1/events`(POST/DELETE)、身份归一化(`canon_operator`、`verify_operator`) |
| admin | `/api/admin/*` 6 个端点 + `_validate_targets`/`_resolve_admin_targets`/`_preview_*`/`_purge`/`_restore_admin_batch`/`_admin_inventory` |
| board | `/api/state` / `/api/skills` / `/api/skill` / `/api/operator` / `/api/agent` + `_snapshot`/`metrics`/`leverage`/`*_payload`/`_state_compute_or_cache` |
| onboarding | `/install.sh` / `/shims/{path}` / `/shims/manifest` / `/llms.txt` / `/robots.txt` / `/healthz` / `/` + SPA fallback + `_build_shim_manifest` |

加上跨域共享的:DB / 认证 / 限流 / catalog / 配置 / 共用工具。

具体问题:

1. **新人 / Agent 找代码靠 grep,而非靠 spec 域定位**——spec 已写「事实来源:server/app.py 的 X 函数」,
   但代码不分文件,读者要在 2648 行里搜函数名。
2. **改 admin 域时不可避免会触碰 board/ingest 域代码**(共用文件),review 难以判断改动边界。
3. **后续 CPU 优化的 change**(`/api/agent` 复用缓存、single-flight 等)需要在 board 域局部改,
   单文件让 PR diff 失焦,改 10 行也要在 2648 行里翻。
4. **导入开销**:任何引用 `server.app` 的工具(测试、shim、监控脚本)都拉满整个文件依赖。

## 目标
- 按 spec 域把 `server/app.py` 拆为 `server/<base>.py` + `server/routes/<domain>.py`,
  对应 `openspec/specs/<domain>/spec.md` 的「事实来源」物理结构。
- **行为完全零变更**——Change A 的 95% 测试覆盖率 + `tests/test_module_boundary.py` 守门。
- `server/app.py` ≤ 100 行(仅做实例化 + 中间件挂载 + 路由注册 + 关键符号 re-export)。
- `tests/conftest.py` 的 `import app; app.<symbol>` 兼容性 100% 保留,现有 155 + 新增测试零修改。
- 每个新文件顶部一行注释指明对应的 `openspec/specs/<domain>/spec.md`。

## 非目标
- 不做行为优化、不做 CPU 改进、不动 API 形状、不动 SQL、不动协议、不动 UI。
- 不调函数签名(除非纯粹必要的 import 路径调整)。
- 不引入新的依赖。
- 不重组 `tests/`(测试已按域分文件)。
- 不动 `shims/` / `frontend/` / `install.sh` / CI workflow。
- 不引入新的抽象层(routes / services / repositories 三层)——本变更是「平移到正确位置」,
  不是「重新设计架构」。

## 方案概述(详见 design.md)
按依赖从下到上,拆为 12 个文件:

```
server/
├── app.py            ~60   FastAPI 实例 + 中间件 + 路由挂载 + init_db() + 关键符号 re-export
├── config.py         ~60   ENV 读取 + 常量
├── db.py             ~220  连接 / schema / 迁移 / _maybe_prune / 全局 _lock / 共用工具 _json/now_iso/_sha
├── security.py       ~180  CSP / 中间件 / 鉴权 / 限流 / _client_host / _req_is_https / _audit
├── identity.py       ~80   canon_operator / verify_operator / operators 表
├── catalog.py        ~150  fetch/parse/save/load + _catalog_loop + _catalog_context
├── shim.py           ~60   _build_shim_manifest + _SHIM_MANIFEST
├── profile.py        ~50   _skill_names/_use_name/_mode + load_profiles/_shim_versions + reuse_map
└── routes/
    ├── ingest.py     ~150  POST /v1/enroll、POST /v1/events、DELETE /v1/events
    ├── admin.py      ~400  /api/admin/* + _validate_targets/_resolve/_preview/_purge/_restore/_inventory
    ├── board.py      ~350  /api/state/skills/skill/operator/agent + _snapshot/metrics/*_payload
    └── onboarding.py ~80   /install.sh、/shims/*、/llms.txt、/robots.txt、/healthz、SPA
```

迁移顺序(避免循环引用):`config → db → security/identity/profile/shim/catalog → routes/* → app`。
**一次搬一个文件,搬完跑 pytest,绿了才搬下一个**——PR 内约 12 个小 commit。

## 影响
- `server/app.py` 从 2648 行 → ≤ 100 行(仅组装)。
- 新增 11 个文件(7 个基础模块 + 4 个 routes/)。
- 新增目录级 `server/AGENTS.md`,指明每个文件的职责与对应 spec 域。
- 新增 `tests/test_module_boundary.py`(~50 行)守门:
  - `server/app.py` 行数 ≤ 100
  - 各 routes 文件能独立 import
  - 关键 re-export 在 `server.app` 命名空间下可访问
- **行为零变更**:155 + Change A 的 ~35 个新测试全绿,数字不变。
- 协议 / API 形状 / DB schema / 配置 / 部署完全不变。
- **spec-delta**:四个域各更新一行「事实来源」指针,指向新的模块路径。
