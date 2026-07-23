# 系统模块地图(module-map)

> 用途:界定每个模块的**职责边界、入口、上游、下游、禁止依赖**,防止改动越界。
> 一句话架构:**采集(shim)→ 协议(TATP)→ 服务端(collector+计算)→ 看板(前端)**,单运行容器 + Docker 内前端构建,SQLite 落地。

## 数据流总览
```
agent 机器                         中心服务器(单容器)                 浏览器
┌───────────────┐  POST /v1/events ┌──────────────────────────┐  GET /  ┌──────────────┐
│ shim:         │ ───────────────▶ │ server/app.py             │ ──────▶ │ React SPA    │
│ tf_report /   │  X-TF-Key=TF_KEY │  ingest → SQLite           │ /api/state │ dist/assets │
│ tf_hook / ... │                  │  compute → snapshot        │ ◀────── │ (轮询)       │
│ tf_profile    │ ◀─ /install.sh,/shims/manifest,<f> ─ 分发自身 ─│            └──────────────┘
└───────────────┘                  └──────────────────────────┘
```

## 模块

### M1 — 服务端 collector (`server/app.py`)
- **职责**:接收事件、去重落库、按身份计算活跃/质量/复用/leverage、聚合 Agents 运营 overview 与 Skill 使用/公司库采纳统计(读侧返回 `Asia/Shanghai` `today` 作为图表时间轴右端;
  活跃时长先按 session 以 180 秒断档拆连续段,再按最终 `operator + agent||runtime` 身份取区间并集并按上海日切分)、
  提供看板 SPA 与 API、分发安装脚本与 shim;`/api/state` 与 `/api/state/stream` 快照必须经进程内 TTL 缓存和 single-flight 复用,
  `/api/agents` 从同一最终身份卡片快照输出指定时间窗的 Agents summary/comparison/daily/ranking/agents/signals,
  `/api/skills` 与 `/api/skills/evidence` 可用 ETag / `If-None-Match` 做同 URL revalidate 但不得未经业务确认引入跳过服务端校验的 TTL;
  Skill 读模型保留 slug identity,并从 catalog/profile 统一附加 `display_name/display_name_zh` 与批量名称映射,
  `/assets/*` 指纹化静态资源长期缓存,SPA HTML 保持 revalidate,
  连续段内纯心跳 `last_seen` 默认按 `TF_HEARTBEAT_BATCH_SECONDS=15` 秒进程内批量写入;
  最后确认心跳取 SQLite/pending 较新值,同一事件 pending 入队单调不减,任何新行插入前固化旧行 pending,
  flush 与 ingest 在全局写锁内原子交接且失败保留 pending,后台循环在单轮异常后继续按间隔重试;
  同状态/同步骤超过 180 秒后恢复必须落新行并保留旧段末点,
  `/healthz` 必须是 async 轻量响应且不得依赖 DB/聚合读路径。
- **入口(路由)**:`POST /v1/events`、`GET /api/state`、`GET /api/state/stream`、`GET /api/agents`、`GET /api/skills`、`GET /api/skills/evidence`、`GET /api/skill/{name}`、
  `GET /api/operator/{name}`、`GET /api/agent/{key}`、`GET /api/admin/inventory`、`POST /api/admin/preview`、
  `DELETE /api/admin/data`、`GET /api/admin/trash`、`POST /api/admin/restore`、`GET /api/admin/export`、`GET /healthz`、`GET /` 与 SPA 深链(看板)、
  `GET /assets/*`、`GET /install.sh`、`GET /shims/manifest`、`GET /shims/{path}`。
- **上游**:shim 发来的事件(不可信输入,需鉴权 + 校验)。
- **下游**:SQLite(`$TF_DB`,含 `events`/`profiles`/`skills_seen`/`skill_uses`/`admin_trash`/`admin_audit`);
  浏览器(只读快照、Agents 指定窗口统计与 Skills 聚合);使用者机器(取 install/shim)。
- **禁止依赖**:外部数据库/缓存/消息队列;任何 token/成本计算;读取使用者敏感内容(除非事件显式带 opt-in 字段);
  新增删除路径不得绕过 `_purge` 的级联、回收站与审计。

### M2 — 看板前端 (`frontend/`)
- **职责**:优先通过 `/api/state/stream` SSE(失败时回退 `/api/state` adaptive polling)渲染 Pods 看板 / 治理详情;Agents 运营列表独立请求 `/api/agents`,先渲染 skeleton,再消费服务端指定窗口统计,固定按 Agent 统计运行时长,展示单日 Agent 环形分布或多日按 Agent 分段的堆叠趋势、排行及含操作员的明细表;低频读取
  `/api/skills`、`/api/skills/evidence`、`/api/skill/{name}` 与 `/api/operator/{name}` 渲染 SKILLS 总览 / 新增发布 Skill 列表 / 记录页 / clue 详情 / Skill 详情 / Operator 详情;SKILLS 总览图表按服务端返回的
  `window.start..window.end` 铺满所选 `w/days` 窗口,详情页按 30 天日级时间轴,并负责柱子锚定的 hover/click 明细浮窗与视口避让;
  SKILLS 总览使用证据导向 dashboard 结构(控制条/过去 W 变化/问题线索/主分析区:排行+趋势图|待处理线索/Donut/明细抽屉/下沉漏斗),视角切换收进控制条,
  首屏聚合数字必须能下钻到 `/skills/evidence`、`/skills/new` 或同页名单记录;待处理线索三类下钻到 `/skills/clues/:kind`;记录页、新增发布页和 clue 页继承当前时间窗并展示下一步动作、分组、原始记录或名单;
  Skill 明细整行打开抽屉并由抽屉按钮跳详情,抽屉展示 W/环比/装机、14/30/90 趋势、runtime、使用操作员 Top 与装备未使用差集;按人主榜和操作员详情 Skill 排行整行跳转,
  最近记录按浏览器本地时区展示 `first_seen`(本地今天内相对时间,昨天显示`昨天 HH:mm`,近 7 天显示星期+时刻,
  今年更早显示`MM-DD HH:mm`,跨年显示`YYYY-MM-DD HH:mm`,hover 显示完整本地绝对时间+时区;
  缺失 `first_seen` 时按服务端统计 `day` 显示今天/昨天/星期/MM-DD/YYYY-MM-DD,hover 保留原始日期)且不呈现可点态;
  `/admin` 里的具体 ISO 时间戳也按浏览器本地绝对时间显示,date-only 统计字段保持服务端 `Asia/Shanghai` 日期语义;旧 `lens` search param 保留 no-op,
  未收录使用占比由过去 W 变化、问题线索与待处理线索呈现;
  `/token-usage` 独立读取 `/api/token-usage`，以 `w/wstart/wend/g/kind/model/risk/topn/q/hz/sort/dir` 保存全部可见筛选与排序，变化使用 replace，临时 KEY 抽屉/忽略状态不持久化；
  暗亮三态主题(`system`/`light`/`dark`,仅主题模式可用 `tf-theme-mode` localStorage 窄例外持久化)、中英、手机适配;path 深链与 SKILLS/Token Usage search params。
  `/agents`、`/skills`、`/skills/new`、`/skills/evidence`、`/skills/clues/:kind`、`/token-usage`、`/skill/:name` 与 `/operator/:name` 不得等待全局 `/api/state` 首包后才挂载;这些路由先渲染自身 loading/skeleton 并请求各自 API。
  SKILLS GET 请求按完整 URL 做 in-flight 去重与 ETag revalidate;返回页或刷新可先展示同 URL 已校验 payload 作为过渡态,但后台仍必须向服务端校验。
- **入口**:源码在 `frontend/`;Docker/CI 运行 `npm run build` 生成 `frontend/dist`,由 M1 在 `/`、
  `/agents`、`/agent/:key`、`/skills`、`/skills/new`、`/skills/evidence`、`/skills/clues/:kind`、`/token-usage`、`/skill/:name`、`/operator/:name`、`/admin` 及其它非 API 深链提供;数据来自
  `/api/state`、`/api/agents`、`/api/skills`、`/api/skills/evidence`、`/api/token-usage`、`/api/skill/{name}`、`/api/operator/{name}`、`/api/admin/*`(同源相对路径)。
- **上游**:M1 的 `/api/state/stream`、`/api/state`、`/api/agents`、`/api/skills`、`/api/skills/evidence`、`/api/skill/{name}`、`/api/operator/{name}`;状态流与 `/api/state` 取不到时退回内置演示数据,
  SKILLS 接口取不到时显示错误/空态；`/api/token-usage` 只读外部分发平台数据，不进入 Agent 遥测数据模型。
- **下游**:无(纯展示);`/api/agent/{key}` 可选,默认用 `/api/state` 里合并好的 session 数据。
- **禁止依赖**:浏览器本地存储(例外:主题模式仅可用 `tf-theme-mode` localStorage 保存 `system|light|dark`;`/admin` 仅可用 sessionStorage 暂存本会话管理钥匙);
  独立前端运行服务或运行期 node 依赖;后端端口写死(必须走相对路径)。

### M3 — 采集 shim (`shims/`)
- **职责**:在使用者机器上把状态/档案上报给 M1。
  - `tf_profile.py` 自动探测 profile(版本/终端/位置/IM/MCP/技能/集成),Skill 项从本机 `SKILL.md`
    best-effort 读取 `display_name/display_name_zh`;
  - `tf_selfupdate.py` 在会话开始后台检查 `/shims/manifest`,经 staging + sha256 + py_compile 后原子更新本地 shim,
    并在版本一致但文件缺失/哈希不符时补齐目标文件;
  - `tf_report.py` 组装并 POST 事件(可带 `--profile`;可选 `--skill` 上报本会话使用过的 Skill 名;
    OpenClaw 插件可带 `skill_mode=equipped` 上报装备态);
  - `tf_client.sh` + `wrapper/tf-run` bash 封装(started 带 profile,心跳,done/error);
  - `tf_hook.py` Claude Code / Codex / Hermes 钩子分发器(读 stdin 事件→状态/Skill 使用→调 tf_report;
    Claude Code 识别 `Skill` 工具调用,并在 `Stop` / `SessionEnd` 按位置守门扫描 transcript 里的真实斜杠 skill,
    过滤 Claude Code 内置 UI 命令;Hermes 识别 `skill_view`;
    Codex 在轮次/会话结束时拉起 `tf_rollout_scan.py`;
    Hermes 链路另落 `~/.tranfu/logs/hermes-hook.ndjson` 常态结构化诊断日志,双文件 5MB rotate,
    `TF_HOOK_DEBUG=0` 关闭,见 ADR-0022);
  - `tf_rollout_scan.py` Codex 专属:解析本机 rollout 会话文件,兼容旧 `function_call` 与 Desktop
    `custom_tool_call exec` 两种命令容器,仅从静态 shell `cmd` 提取"读了已装 SKILL.md"的 Skill 名上报(ADR-0016);
  - `openclaw/` OpenClaw 原生 JS 插件:在进程内 `llm_input` 只解析 prompt 注入块里的 Skill 名,
    `session_end` 以 `skill_mode=equipped` 排队后台上报装备态,hook 不等待网络;只出站到 M1,不依赖 Python shim,
    不得记录 prompt 正文;
  - `tf_hooks.py` Claude Code / Codex hooks JSON 幂等安装、卸载、恢复管理器;
  - `tf_codex_hook_guard.py` Codex 用户 Hook 信任健康守护:通过 app-server `hooks/list` 读取真实 hash/信任状态,
    仅对完整唯一的已信任 group 纯换序做备份+原子重排+写后复查,新 hash 只去重通知用户打开 `/hooks`;
    macOS managed LaunchAgent 监听 `~/.codex/hooks.json` 并每 300 秒兜底检查(ADR-0024);
  - `mcp/server.py` MCP reporter(桌面/黑盒,首次上报附 profile);
  - `tf_client.py` python 客户端。
- **入口**:使用者运行(tf-run / 钩子 / MCP 工具),或 `install.sh` 安装后由各 agent 触发。
- **上游**:使用者本机环境(探测来源)。
- **下游**:M1 的 `/v1/events`。
- **禁止依赖**:Python shim 不得依赖第三方库;所有 shim/plugin 不得抛错/阻塞宿主 agent;不得默认上报敏感内容。
  Skill 使用统计只允许上报 Skill 名与 `skill_mode`,不得上报参数、prompt、代码或输出。

### M4 — 安装与分发 (`install.sh` + M1 的 `/install.sh`、`/shims/manifest`、`/shims/{path}`)
- **职责**:一键把 shim 装到 `~/.tranfu`、写 shell rc(身份/密钥)、装完自动注册一次。
  Codex Hook 安装/卸载同时幂等安装/卸载健康守护 LaunchAgent;自更新器在远端节流判断前补齐守护。
- **入口**:`curl -fsSL $SERVER/install.sh | bash -s -- --server .. --key .. --operator .. --runtime .. --agent .. --role ..`。
- **上游**:管理员提供的 server/key。
- **下游**:按 `$SERVER/shims/manifest` 全量取 shim 文件;装完调 `tf_report.py --status started --profile` 注册。
- **禁止依赖**:GitHub 公网可见性(改为从看板域名分发,见 ADR-0007),以支持私有库。

### M5 — 协议与文档 (`PROTOCOL.md`、`*.md`、`SKILL.md`、`openspec/`、`docs/`)
- **职责**:事件协议(TATP)、接入/部署/运维说明、给 agent 读的自助安装、规格与决策记录。
- **禁止依赖**:与实现脱节——改字段/端口/链接/行为时必须同步本目录与 `openspec/specs`。

## 全局禁止依赖矩阵
| 模块 | 不得依赖 |
|---|---|
| M1 服务端 | 外部 DB/MQ;token 成本;主动读使用者敏感内容 |
| M2 前端 | 浏览器持久存储(例外:主题模式 `tf-theme-mode` localStorage;`/admin` sessionStorage 暂存管理钥匙);独立前端服务/运行期 node;后端端口/绝对地址 |
| M3 shim | 第三方库;抛错阻塞;默认上报内容/记忆 |
| M4 安装 | 仓库必须公开 |
| 全部 | 把密钥写进仓库/文档正文 |
