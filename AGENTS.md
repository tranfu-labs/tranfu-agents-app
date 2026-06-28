# AGENTS.md — TRANFU//AGENTS 项目操作手册(给 AI / 协作者)

TRANFU//AGENTS 是**自托管、厂商中立的团队 AI Agent 可观测看板**:每个 agent 上报极简状态事件到中心 collector,看板实时展示「谁在跑、用哪个 agent、当前哪一步、状态、活跃时长」与每个 agent 的治理详情(版本/终端/IM/MCP/技能),并提供独立 SKILLS 统计页(按 skill / 按人双视角)。MIT 许可。

> 改动前先读:本文件 + `docs/architecture/module-map.md`(模块边界/禁止依赖)+ `docs/adr/`(已定约束)。
> 业务规则事实来源是 `openspec/specs/<domain>/spec.md`;做需求/变更先在 `openspec/changes/<change-id>/` 写 proposal/design/tasks 再实现。

## 项目结构(根目录)
- `server/` — FastAPI collector + 看板服务端(单进程,既收事件又发页面与 API)。按 `openspec/specs/` 域分文件:`app.py`(组装入口 + 可变开关 + re-export)、`config.py`、`db.py`、`security.py`、`identity.py`、`profile.py`、`catalog.py`、`shim.py` + `routes/{ingest,admin,board,onboarding}.py`。详见 `server/AGENTS.md`。
- `Dockerfile`、`compose.yml`、`.env.example`、`server/requirements.txt` — 部署。
- `.github/workflows/ci.yml` — PR/main 跑编译 + pytest;`.github/workflows/deploy.yml` — push main 跑 pytest 卡口后构建并推 `ghcr.io/tranfu-labs/tranfu-agents-app:latest` + `:<sha>`(回滚用 sha tag);Coolify 本阶段仍用 `compose.yml` build 部署,GHCR 镜像备用。
- `frontend/` — React + TypeScript 看板 SPA(Vite 构建);FastAPI 在 `/` 与 SPA 深链提供 `frontend/dist`。
- `shims/` — 各客户端上报工具:`tf_profile.py`(探测)、`tf_report.py`(统一发射)、`tf_client.sh`/`wrapper/tf-run`(bash 封装)、`tf_hook.py`(Claude Code / Codex / Hermes 钩子分发;Hermes 链路另落 `~/.tranfu/logs/hermes-hook.ndjson` 常态诊断日志,见 ADR-0022)、`tf_selfupdate.py`(manifest 自更新)、`tf_client.py`(python 客户端)、`claude-code/`(hooks.settings.json + README)、`mcp/`(MCP reporter server.py)。
- `install.sh` — 一键安装:按 `$SERVER/shims/manifest` 全量拉客户端到 `~/.tranfu`,写 shell rc,装完自动注册一次。
- 文档:`README`、`QUICKSTART`(队友 5 分钟接入)、`USAGE`(自然语言接入)、`DEPLOY`(部署)、`UPDATE`(更新现有部署)、`DEV-SETUP`(开发从零部署)、`PROTOCOL`(TATP 事件协议)、`SKILL.md`(给 agent 读的自助安装)、`llms.txt`/`robots.txt`。

## 常用命令
```bash
# 本地起服务端(看板 + API)
pip install -r server/requirements.txt
TF_KEY=devkey python -m uvicorn server.app:app --host 0.0.0.0 --port 8788

# 本地开发前端(另开终端;Vite 代理 /api、/v1、/shims 到 8788)
cd frontend && npm install && npm run dev

# 前端生产构建
npm --prefix frontend run build

# Coolify 部署:用根目录 compose.yml(Docker 多阶段构建 frontend 并复制 dist);给 server service 配 Domain: https://你的域名:8788

# 本地裸 Python 健康/接口自检
curl http://localhost:8788/healthz                      # ok
curl http://localhost:8788/api/state | head             # JSON
curl 'http://localhost:8788/api/skills?days=30' | head  # SKILLS 总览 JSON
curl http://localhost:8788/api/operator/alice | head    # 单操作员 SKILLS 详情(需已有数据)
curl http://localhost:8788/shims/manifest | head        # shim 版本清单

# 发一条测试事件
curl -s -XPOST http://localhost:8788/v1/events -H 'content-type: application/json' \
  -H 'X-TF-Key: devkey' -d '{"operator":"t","runtime":"claude-code","session_id":"s1","status":"running","task":"x","current_step":"y"}'
```

## 编码规范 / 约定
- **服务端只用标准库 + FastAPI/uvicorn**;数据库是单文件 SQLite(`$TF_DB`,默认 `tf.db`),不引入外部 DB/中间件。
- `/api/state` 是高频轮询读路径,服务端必须做进程内 TTL 缓存(默认 `TF_STATE_TTL=1.5` 秒);
  响应 `now` 表示"上次服务端计算时间",不是每次请求的当前时间。`/healthz` 必须是 async 轻量 handler,
  固定返回 `ok`,不得打开 DB 或触发 IO,避免被 `/api/state` 聚合压力拖慢。
- **shim 只用 Python 标准库,且绝不抛错**——上报/更新失败必须静默,不能影响使用者的 agent 运行。
- `shim_version` 是事件**顶层可选字段**(不再是 profile 子字段),`tf_report.py` 每次心跳兜底自动注入;
  服务端按身份 sticky(独立表 `agent_shim_versions`),profile 全量替换不得清掉它;前端三态判定
  `current` / `outdated` / `unknown`(字段缺失 = unknown,**不能**误判为 outdated)。
- Skill 统计口径:事件可选 `skill`(仅 Skill 名)+ 可选 `skill_mode ∈ {used,equipped}`;服务端写 `skill_uses`(一行=会话×Skill×mode,`(session_id, skill, mode)` 幂等,长期保留)。端点:`/api/state.skills`(兼容排行)、`/api/skills?days={7|30|90}`(总览,skill/operator 两套 used-only 聚合,含 UTC `today`)、`/api/skill/{name}`(used/equipped 分列,含 UTC `today`)、`/api/operator/{name}`(按人 used-only,空 operator 与 equipped 不计入)。默认上报,本机 `TF_REPORT_SKILLS=0` 关闭;不得上报 Skill 参数/prompt/代码/输出。
- 前端 React + TypeScript SPA;生产产物由 Docker/CI 构建,**仓库不提交 `frontend/dist`**。暗/亮双主题用 CSS 变量 + `body.light` 覆盖;品牌红 `--brand`(占位 `#ec1c2b`;实际值已挖出三档红 `#bd0d1c`/`#f42631`/`#ff2f37`,见 `frontend/public/favicon.svg`,CSS 占位是否切换走单独决策);logo 为内联红色 symbol。SKILLS 总览视角切换用独立 `frame` 卡片(左「视角」、右 `cnt` 说明,内容行 32px 分段按钮,选中态 `--brand`);筛选条留在 SKILLS 统计卡;可下钻表格整行可点且键盘可达,最近记录表不可点、时间列显示 `first_seen` 到秒(缺失回退 UTC 日期)。
- SKILLS 使用排行在按 Skill 视角内有管理者筛选 Lens:`all` / `untracked`;`untracked` 只切换排行表为"未收录使用占比"列表,不影响每日趋势图、全局过滤条或公司库漏斗。口径为当前 `days` 窗口内 `source=非公司库` 且 `mode=used` 的会话×skill 记录数 / 当前窗口全部 `mode=used` 记录数;`external` 与 `equipped` 不计入未收录。
- 网站 head 图标 / social-preview(`favicon`、`apple-touch-icon`、PWA `manifest`、`og:image`、`twitter:image`、JSON-LD `publisher.logo`)一律用 `frontend/public/` 本地资源 + 部署域名绝对 URL(以 `<link rel="canonical">` 为准),**禁止直接引品牌主站 `https://tranfu.com/brand/...` 远端 URL**;图标位只能用 symbol 1:1 衍生资源(横向 lockup 4.2:1 缩到小尺寸会被裁切,JSON-LD `publisher.logo` 也用 symbol 1:1 因 Google 推荐 ≤3:1)。品牌资源源 <https://tranfu.com/brand/preview.html>。PWA `manifest.json` 的 `theme_color` 必须与 `<meta name="theme-color">` 一致。
- 时间统一 **UTC**(活跃时长按 UTC 日/周;90 天窗口)。
- **安全响应头 / CSP**:所有响应经 `server/security.py` 的 `_security_headers` 中间件注入 `nosniff` / `X-Frame-Options: DENY` / `Referrer-Policy` / 锁定本源的 CSP(`_CSP`),HTTPS 部署另发 HSTS。前端**新接任何外部域名**(脚本、`fetch`/WebSocket、字体、图片、iframe)时,必须把该来源加进 `_CSP` 的对应指令(脚本→`script-src`、请求→`connect-src`、字体→`font-src`、图片→`img-src`),否则浏览器会静默拦截。能放同源就别引外部源;CSP 越窄越好。
- **管理接口认证**:管理钥匙与写侧 `TF_KEY` 均用常量时间比较(`_key_eq`);`/api/admin/*`、`/api/admin/export`、兼容 `DELETE /v1/events`、`/v1/enroll` 经 IP 限流 + 指数退避(`TF_ADMIN_RATE_*`/`TF_ADMIN_LOCK_*`,反代须开 `TF_TRUST_PROXY`);整库导出走 `POST` 且需 `confirm=EXPORT`。
- 不追踪 token / 成本(已彻底移除);写凭证只有 `TF_KEY`,请求头 `X-TF-Key`。
- 仓库 owner/库名统一 `tranfu-labs/tranfu-agents-app`;raw/clone/install 链接都指它。

## 修改前检查
1. 读 `docs/architecture/module-map.md` 确认模块边界与**禁止依赖**。
2. 读相关 `openspec/specs/<domain>/spec.md` 确认不违反业务规则;要改规则走 `openspec/changes/`。
3. 读 `docs/adr/` 看是否触碰已决约束(无 token 追踪、单容器、按身份合并卡片等)。

## 修改后检查
1. 服务端:`python -m py_compile server/*.py server/routes/*.py`;关键路径用 TestClient 自测(`/v1/events` 去重、`/api/state` 结构与卡片合并、`/api/skills`、`/api/skill/{name}`、`/api/operator/{name}` 聚合口径、`/install.sh`、`/shims/manifest` 与 `/shims/<f>` 可取、目录穿越被拒)。契约测试在 `tests/`(`pytest tests/`),CI(`.github/workflows/ci.yml`)在 PR 自动跑;改协议行为时同步加/改用例。**覆盖率门槛**(由 `add-server-app-test-baseline` 引入,`refactor-server-app-by-domain` 拓宽到 `server/**/*.py`):`python -m coverage run -m pytest && python -m coverage report --include='server/**/*.py'` —— 整体行覆盖必须 ≥ 95%,豁免行用 `# pragma: no cover` 标记(`.coveragerc` 见仓库根)。子模块边界守门见 `tests/test_module_boundary.py`,详细约定见 `server/AGENTS.md`。
2. 前端:`npm --prefix frontend run build`;暗/亮主题与手机窄屏(≤600px)各看一眼。
3. shim:对 fake 环境跑 `tf_profile.py` / `tf_report.py --print` 验证 payload;`bash -n` 校验 sh。
4. 文档:涉及端口/链接/字段时同步 `DEPLOY/UPDATE/QUICKSTART/USAGE/PROTOCOL`、`docs/architecture/module-map.md` 与本文件;若影响 agent 自助安装,同步 `SKILL.md`。

## 禁止事项(硬约束)
- ❌ 不得加入 token/费用统计,或把"成本"概念带回数据模型/协议/UI。
- ❌ 不得让 shim 在探测/上报失败时抛错或阻塞使用者 agent;不得默认上报 prompt/代码/输出/记忆(均为 opt-in)。
- ❌ 不得在 Claude Code 钩子里依赖 `$CLAUDE_SESSION_ID` 等环境变量取上下文——必须从 stdin 的事件 JSON 解析(见 ADR-0009)。
- ❌ 不得为看板引入外部数据库/消息队列/独立前端运行服务或运行期 node 依赖(保持单运行容器;前端只允许 Docker/CI 构建产物)。
- ❌ 不得把密钥写进仓库或文档正文(`TF_KEY` 仅存部署机 `.env` / 使用者 shell rc)。
- ❌ 不得绕过"按身份(operator + agent||runtime)合并卡片"的模型去按 session 散开展示。

## 线框图
默认生成 `docs/wireframes/`(字符图线框,对齐页面信息架构与版式)。本项目**有界面**(`frontend/` SPA),按 `docs/wireframes/AGENTS.md` 维护:每个真实路由在 `docs/wireframes/pages/` 对应一页(现覆盖 `/`·`/agents`·`/agent/:key`·`/skills`·`/skill/:name`·`/operator/:name`),页面流转记在 `docs/wireframes/flow.md`;新增/改路由时同步增改对应页与流转图。(若项目转为无界面的工具/库/CLI/SDK,则删除整个 `docs/wireframes/` 目录与本节。)
