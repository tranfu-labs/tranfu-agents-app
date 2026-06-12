# 系统模块地图(module-map)

> 用途:界定每个模块的**职责边界、入口、上游、下游、禁止依赖**,防止改动越界。
> 一句话架构:**采集(shim)→ 协议(TATP)→ 服务端(collector+计算)→ 看板(前端)**,单容器 + 单文件前端,SQLite 落地。

## 数据流总览
```
agent 机器                         中心服务器(单容器)              浏览器
┌───────────────┐  POST /v1/events ┌───────────────────────┐  GET /  ┌──────────────┐
│ shim:         │ ───────────────▶ │ server/app.py          │ ──────▶ │ dashboard/   │
│ tf_report /   │  X-TF-Key=TF_KEY │  ingest → SQLite        │ /api/state │ index.html │
│ tf_hook / ... │                  │  compute → snapshot     │ ◀────── │ (轮询2s)     │
│ tf_profile    │ ◀─ /install.sh,/shims/<f> ── 分发自身 ──────│         └──────────────┘
└───────────────┘                  └───────────────────────┘
```

## 模块

### M1 — 服务端 collector (`server/app.py`)
- **职责**:接收事件、去重落库、按身份计算活跃/质量/复用/leverage、聚合 Skill 使用排行、
  提供看板与 API、分发安装脚本与 shim。
- **入口(路由)**:`POST /v1/events`、`GET /api/state`、`GET /api/agent/{key}`、`GET /healthz`、
  `GET /`(看板)、`GET /install.sh`、`GET /shims/{path}`。
- **上游**:shim 发来的事件(不可信输入,需鉴权 + 校验)。
- **下游**:SQLite(`$TF_DB`,含 `events`/`profiles`/`skills_seen`/`skill_uses`);
  浏览器(只读快照);使用者机器(取 install/shim)。
- **禁止依赖**:外部数据库/缓存/消息队列;任何 token/成本计算;读取使用者敏感内容(除非事件显式带 opt-in 字段)。

### M2 — 看板前端 (`dashboard/index.html`)
- **职责**:轮询 `/api/state` 渲染 Pods 看板 / Skills 排行 / Agents 列表 / 治理详情;
  暗亮主题、中英、手机适配。
- **入口**:由 M1 在 `/` 提供;数据来自 `/api/state`(同源相对路径)。
- **上游**:M1 的 `/api/state`(取不到时退回内置演示数据,显示"未连接服务端")。
- **下游**:无(纯展示);`/api/agent/{key}` 可选,默认用 `/api/state` 里合并好的 session 数据。
- **禁止依赖**:浏览器本地存储(localStorage 等);外部构建步骤;后端端口写死(必须走相对路径)。

### M3 — 采集 shim (`shims/`)
- **职责**:在使用者机器上把状态/档案上报给 M1。
  - `tf_profile.py` 自动探测 profile(版本/终端/位置/IM/MCP/技能/集成);
  - `tf_report.py` 组装并 POST 事件(可带 `--profile`;可选 `--skill` 上报本会话使用过的 Skill 名);
  - `tf_client.sh` + `wrapper/tf-run` bash 封装(started 带 profile,心跳,done/error);
  - `tf_hook.py` Claude Code / Codex 钩子分发器(读 stdin 事件→状态/Skill 使用→调 tf_report;
    Codex 在轮次/会话结束时拉起 `tf_rollout_scan.py`);
  - `tf_rollout_scan.py` Codex 专属:解析本机 rollout 会话文件,提取"读了已装 SKILL.md"的 Skill 名上报(ADR-0016);
  - `tf_hooks.py` Claude Code / Codex hooks JSON 幂等安装、卸载、恢复管理器;
  - `mcp/server.py` MCP reporter(桌面/黑盒,首次上报附 profile);
  - `tf_client.py` python 客户端。
- **入口**:使用者运行(tf-run / 钩子 / MCP 工具),或 `install.sh` 安装后由各 agent 触发。
- **上游**:使用者本机环境(探测来源)。
- **下游**:M1 的 `/v1/events`。
- **禁止依赖**:第三方库(只用标准库);抛错/阻塞宿主 agent;默认上报敏感内容。
  Skill 使用统计只允许上报 Skill 名,不得上报参数、prompt、代码或输出。

### M4 — 安装与分发 (`install.sh` + M1 的 `/install.sh`、`/shims/{path}`)
- **职责**:一键把 shim 装到 `~/.tranfu`、写 shell rc(身份/密钥)、装完自动注册一次。
- **入口**:`curl -fsSL $SERVER/install.sh | bash -s -- --server .. --key .. --operator .. --runtime .. --agent .. --role ..`。
- **上游**:管理员提供的 server/key。
- **下游**:从 `$SERVER/shims/*` 取 shim 文件;装完调 `tf_report.py --status started --profile` 注册。
- **禁止依赖**:GitHub 公网可见性(改为从看板域名分发,见 ADR-0007),以支持私有库。

### M5 — 协议与文档 (`PROTOCOL.md`、`*.md`、`SKILL.md`、`openspec/`、`docs/`)
- **职责**:事件协议(TATP)、接入/部署/运维说明、给 agent 读的自助安装、规格与决策记录。
- **禁止依赖**:与实现脱节——改字段/端口/链接/行为时必须同步本目录与 `openspec/specs`。

## 全局禁止依赖矩阵
| 模块 | 不得依赖 |
|---|---|
| M1 服务端 | 外部 DB/MQ;token 成本;主动读使用者敏感内容 |
| M2 前端 | 浏览器存储;构建步骤;后端端口/绝对地址 |
| M3 shim | 第三方库;抛错阻塞;默认上报内容/记忆 |
| M4 安装 | 仓库必须公开 |
| 全部 | 把密钥写进仓库/文档正文 |
