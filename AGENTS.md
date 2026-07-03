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
- `/api/state` 与 `/api/state/stream` 是看板状态读路径,服务端必须做进程内 TTL 缓存(默认 `TF_STATE_TTL=1.5` 秒)与 single-flight 重算保护;前端优先 SSE,失败才回退 adaptive polling。
  纯心跳 `last_seen` 默认按 `TF_HEARTBEAT_BATCH_SECONDS=15` 秒批量写入 SQLite,状态/步骤变化、skill、profile、shim 版本变化仍即时落库;
  响应 `now` 表示"上次服务端计算时间",不是每次请求的当前时间。`/healthz` 必须是 async 轻量 handler,
  固定返回 `ok`,不得打开 DB 或触发 IO,避免被 `/api/state` 聚合压力拖慢。
- `/api/skills` 是低频但重聚合读路径,必须优先通过 SQLite 组合索引与 SQL 预聚合优化,避免把 raw
  `skill_uses` 全历史逐行交给 Python 处理;不得优先用缓存掩盖聚合根因。只有 SQL/索引优化后仍无法达标时,
  才允许引入有界短 TTL 缓存(默认 5 秒,键按 `days/w/wstart/wend/rt/src/scope` 归一化)。
  `/api/skills` 与 `/api/skills/evidence` 可用 ETag / `If-None-Match` 做同 URL / 同参数 revalidate,但未经业务确认不得加会跳过服务端校验的 5-15 秒 TTL 或前端内存缓存。
- **shim 只用 Python 标准库,且绝不抛错**——上报/更新失败必须静默,不能影响使用者的 agent 运行。
- `shim_version` 是事件**顶层可选字段**(不再是 profile 子字段),`tf_report.py` 每次心跳兜底自动注入;
  服务端按身份 sticky(独立表 `agent_shim_versions`),profile 全量替换不得清掉它;前端三态判定
  `current` / `outdated` / `unknown`(字段缺失 = unknown,**不能**误判为 outdated)。
- Skill 统计口径:事件可选 `skill`(仅 Skill 名)+ 可选 `skill_mode ∈ {used,equipped}`;服务端写 `skill_uses`(一行=会话×Skill×mode,`(session_id, skill, mode)` 幂等,长期保留)。端点:`/api/state.skills`(兼容排行)、`/api/skills?days={7|30|90}`(旧兼容总览)、`/api/skills?w={today|this_week|last_week|7d|14d|30d|90d|custom}`(新版总览,skill/operator 两套 used-only 聚合,含 `Asia/Shanghai` `today`;按人聚合可用 `rt/src` 继承观察范围;`scope=new` 进入当前窗口历史首次 used 的可行动名单)、`/api/skills/evidence?kind=...`(当前窗口证据页 payload,used-only,支持 total/untracked/coverage/operators/avg_per_session/idle/unused_ratio/zero_install/top3/runtime/source)、`/api/skill/{name}`(used/equipped 分列,含 `Asia/Shanghai` `today`)、`/api/operator/{name}`(按人 used-only,空 operator 与 equipped 不计入)。`/api/state.leverage.assets` 与顶部 `N Skill 资产` 使用 used-only distinct skill;`skills_week` 与顶部 `+N 7天新发现` 使用当前 7 天窗口内历史首次 used skill;installed/profile-only/equipped-only 不计入 nav 数字。`skills_seen` 只保留为内部发现/安装痕迹,不得作为 nav 展示事实源。默认上报,本机 `TF_REPORT_SKILLS=0` 关闭;不得上报 Skill 参数/prompt/代码/输出。
  Claude Code 斜杠 skill 只从 transcript 中 `type=user` 且 `message.content` 起头斜杠命令三件套里的 `<command-name>` 标记采集,并过滤 `/clear`、`/usage` 等 Claude Code 内置 UI 命令;fixture、tool_result、assistant 文本中的同名标记不得采集。
- 前端 React + TypeScript SPA;生产产物由 Docker/CI 构建,**仓库不提交 `frontend/dist`**。深浅主题为三态 `system` / `light` / `dark`,用 `:root[data-theme]` CSS 变量驱动并设置 `color-scheme`;仅主题模式可用 localStorage key `tf-theme-mode` 保存 `system|light|dark`,其它前端状态仍不得持久化(见 ADR-0023)。品牌红 `--brand`(占位 `#ec1c2b`;实际值已挖出三档红 `#bd0d1c`/`#f42631`/`#ff2f37`,见 `frontend/public/favicon.svg`,CSS 占位是否切换走单独决策);logo 为内联红色 symbol。SKILLS 总览是证据导向 dashboard:控制条(含视角切换、时间窗、搜索、runtime、来源、Top N、隐藏 0 使用,不含环比开关) → 当前时间窗变化(标题从时间窗 i18n label 派生,每格 icon 进证据、短结论、不铺长 skill 名单,previous-window delta 默认开启) → 问题线索/按人使用线索(只显示事实值+证据 icon,不显示`看名单/看证据`等动作文案,不露具体 skill 例子,不做 KPI 评分;证据 icon 默认浅灰,hover/focus 才高亮) → 主分析区(排行 Bar/操作员排行 + 每日趋势图,按窗口长度切布局) → 待处理线索治理行(每类独立区块) → 来源/runtime Donut → 明细表 + Skill 抽屉 → 下沉公司库漏斗;`/skills` 首屏核心文案和时间窗口 label 必须随中英文切换,桌面/平板搜索字段 label+input 保持同一行,KPI 核心数值与证据 icon 保持同一行。`/skills`、`/skills/evidence`、`/skill/:name` 与 `/operator/:name` 不得被全局 `/api/state` 首包阻塞,应先渲染自身 loading/skeleton 并并行请求 SKILLS API;刷新或返回页面可先展示同 URL 已校验旧 payload 作为过渡态,但后台仍必须向服务端 revalidate。桌面 `7d`/`14d` 及以下短窗口下排行和每日趋势左右并列,`30d` 及以上长窗口下二者上下堆叠。手机 `/skills` 控制条默认折叠为一行摘要,首屏先露问题线索和待处理线索,不先铺完整筛选表单;`/skills` 无窗口参数时前端默认 `w=7d`,图表轴使用服务端返回的 `window.start..window.end`,只有窗口右端等于 `today` 才标记"今日进行中";短窗口趋势图填满自身面板可视宽度且限制柱体最大宽度,长窗口在 `.chart-box` 内部横滚并默认显示最新日期。旧 `lens` 参数保留 no-op;未收录使用占比由当前时间窗变化、问题线索、待处理线索共同呈现,口径为当前 `w/days` 窗口内 `source=非公司库` 且 `mode=used` 的会话×skill 记录数 / 当前窗口全部 `mode=used` 记录数,`external` 与 `equipped` 不计入。`/skills/evidence` 继承当前窗口和筛选,用紧凑上下文摘要展示原始 used 记录或名单型证据;有 records 的 kind 第一屏先露 records 表,名单型 kind 第一屏先露名单表,`Top skills / Top operators` 只作辅助分组,冲突 source 筛选由后端返回 `ignored_filters`。按人视角操作员排行继承当前 `w/days` 与 `runtime/source`,不继承 skill 搜索词、Skill Top N、隐藏 0 使用或选中 skill;主排序使用当前窗口 `sessions_window`。SKILLS 统计域专用断点为桌面 `>1080px`、平板 `601px-1080px`、手机 `≤600px`,平板/手机主内容单列且页面根不得横向滚动,手机排行/最近记录/证据记录用摘要行。Skill 总览明细行整行可点打开抽屉且键盘可达,抽屉内显式按钮跳详情,并展示当前时间窗触发、上期变化、活跃者、装机数、14/30/90 趋势、runtime、使用操作员 Top、装备但未使用差集与最近 5 次;按人主榜与操作员详情 Skill 排行整行跳详情;最近记录表和无下钻目标的证据记录不可点。时间列按浏览器本地时区展示 `first_seen`(本地今天内相对时间,昨天显示`昨天 HH:mm`,近 7 天显示星期+时刻,今年更早显示`MM-DD HH:mm`,跨年显示`YYYY-MM-DD HH:mm`,hover 显示完整本地绝对时间+时区;缺失 `first_seen` 时按 `Asia/Shanghai` 统计 `day` 显示今天/昨天/星期/MM-DD/YYYY-MM-DD,hover 保留原始日期)。
- 网站 head 图标 / social-preview(`favicon`、`apple-touch-icon`、PWA `manifest`、`og:image`、`twitter:image`、JSON-LD `publisher.logo`)一律用 `frontend/public/` 本地资源 + 部署域名绝对 URL(以 `<link rel="canonical">` 为准),**禁止直接引品牌主站 `https://tranfu.com/brand/...` 远端 URL**;图标位只能用 symbol 1:1 衍生资源(横向 lockup 4.2:1 缩到小尺寸会被裁切,JSON-LD `publisher.logo` 也用 symbol 1:1 因 Google 推荐 ≤3:1)。浏览器 favicon 候选使用官网同款版本化 `.ico`/PNG,不要把透明 `favicon.svg` 作为 `rel="icon"` 候选;`favicon.svg` 仅保留给 JSON-LD logo 等 1:1 symbol 场景。品牌资源源 <https://tranfu.com/brand/preview.html>。PWA `manifest.json` 的 `theme_color` 必须与静态默认 `<meta name="theme-color">` 一致;页面运行时可按实际主题更新当前文档 meta,不动态改写 manifest。
- 具体时间戳(`recv`/`last_seen`/`first_seen`)统一保存 **UTC instant**;默认日级统计窗口统一 `Asia/Shanghai`(活跃时长按上海日/周;90 天窗口;SKILLS `day`/`today`/`first_day`/`last_day` 均为上海统计日)。前端展示具体 ISO 时刻时按浏览器本地时区格式化,date-only 统计字段保持服务端统计日语义。
- **安全响应头 / CSP**:所有响应经 `server/security.py` 的 `_security_headers` 中间件注入 `nosniff` / `X-Frame-Options: DENY` / `Referrer-Policy` / 锁定本源的 CSP(`_CSP`),HTTPS 部署另发 HSTS;同一中间件负责 `/assets/*` 长缓存与 SPA HTML `no-cache`。前端**新接任何外部域名**(脚本、`fetch`/WebSocket、字体、图片、iframe)时,必须把该来源加进 `_CSP` 的对应指令(脚本→`script-src`、请求→`connect-src`、字体→`font-src`、图片→`img-src`),否则浏览器会静默拦截。能放同源就别引外部源;CSP 越窄越好。
- **管理接口认证**:管理钥匙与写侧 `TF_KEY` 均用常量时间比较(`_key_eq`);`/api/admin/*`、`/api/admin/export`、兼容 `DELETE /v1/events`、`/v1/enroll` 经 IP 限流 + 指数退避(`TF_ADMIN_RATE_*`/`TF_ADMIN_LOCK_*`,反代须开 `TF_TRUST_PROXY`);整库导出走 `POST` 且需 `confirm=EXPORT`。
- 不追踪 token / 成本(已彻底移除);写凭证只有 `TF_KEY`,请求头 `X-TF-Key`。
- 仓库 owner/库名统一 `tranfu-labs/tranfu-agents-app`;raw/clone/install 链接都指它。

## 修改前检查
1. 读 `docs/architecture/module-map.md` 确认模块边界与**禁止依赖**。
2. 读相关 `openspec/specs/<domain>/spec.md` 确认不违反业务规则;要改规则走 `openspec/changes/`。
3. 读 `docs/adr/` 看是否触碰已决约束(无 token 追踪、单容器、按身份合并卡片等)。

## 修改后检查
1. 服务端:`python -m py_compile server/*.py server/routes/*.py`;关键路径用 TestClient 自测(`/v1/events` 去重、`/api/state` 结构与卡片合并、`/api/skills`、`/api/skill/{name}`、`/api/operator/{name}` 聚合口径、`/install.sh`、`/shims/manifest` 与 `/shims/<f>` 可取、目录穿越被拒)。契约测试在 `tests/`(`pytest tests/`),CI(`.github/workflows/ci.yml`)在 PR 自动跑;改协议行为时同步加/改用例。**覆盖率门槛**(由 `add-server-app-test-baseline` 引入,`refactor-server-app-by-domain` 拓宽到 `server/**/*.py`):`python -m coverage run -m pytest && python -m coverage report --include='server/**/*.py'` —— 整体行覆盖必须 ≥ 95%,豁免行用 `# pragma: no cover` 标记(`.coveragerc` 见仓库根)。子模块边界守门见 `tests/test_module_boundary.py`,详细约定见 `server/AGENTS.md`。
2. 前端:`npm --prefix frontend run test:unit`;`npm --prefix frontend run build`;深/浅/系统主题与手机窄屏(≤600px)各看一眼。
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
默认生成 `docs/wireframes/`(字符图线框,对齐页面信息架构与版式)。本项目**有界面**(`frontend/` SPA),按 `docs/wireframes/AGENTS.md` 维护:每个真实路由在 `docs/wireframes/pages/` 对应一页(现覆盖 `/`·`/agents`·`/agent/:key`·`/skills`·`/skills/evidence`·`/skill/:name`·`/operator/:name`),页面流转记在 `docs/wireframes/flow.md`;新增/改路由时同步增改对应页与流转图。(若项目转为无界面的工具/库/CLI/SDK,则删除整个 `docs/wireframes/` 目录与本节。)
