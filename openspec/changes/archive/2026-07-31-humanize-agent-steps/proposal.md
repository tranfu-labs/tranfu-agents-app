# 提案：humanize-agent-steps

## 背景

看板当前把 hook 上报的 `current_step` 原样展示，例如 `tool: WebSearch`、
`tool: Read`、`turn end`。这对熟悉实现的人可读，对普通使用者不直观；同时 Codex / Claude
在 Stop 或 SessionEnd 后补采 Skill 时，会用 `status=done`、`current_step=skill: <name>`
写一条既有事件。该扫描事件可能成为身份卡的最新行，导致卡片步骤被 Skill 补采痕迹盖住。

本轮目标是第一档“展示层归一”：让人能直接看懂 Agent 正在做什么，同时保持既有事件协议、
shim 安装模板、数据库 schema、质量和活跃时长口径不变。

## 提案

1. 在前端新增一个纯函数步骤展示层，按生产库 `events.current_step` 真实出现过的 runtime 和工具键
   转换为中英文人话：例如 Claude Code 的 `tool: WebSearch` 显示为“正在联网搜索”，Codex 的
   实际键 `tool: webrun` 也显示为“正在联网搜索”，但不擅自改写 canonical 工具名。
   MCP 工具按 `mcp__<server>__<tool>` 结构化展示，保留服务器原始连字符/下划线。
2. 在 `/api/state` 的身份卡组装中，Skill 扫描标记不再作为当前步骤来源；若最新行是扫描行，
   从同一 identity + session 取最近一条非扫描事件的步骤。Skill 使用记录本身仍照常落库、统计和去重。
3. 统一在 Pods 卡片、活动流、Agent 详情和 Agents 明细表使用该展示层：生命周期标记
   `session start`、`turn end`、`session end` 不进入步骤行，状态文案负责表达启动/完成/空闲；
   已知工具显示人话，未知工具保留原始 `tool:` / `tool done:` 文本。

## 非目标

- 不修改 `shims/`、hook 安装模板、`tf_report.py`、TATP 字段或 `PROTOCOL.md` 的上报协议。
- 不上报或展示文件路径、命令、URL、参数、prompt、代码、输出等工具对象内容。
- `Bash` 本轮只做人话化“正在执行命令”，不拆解或上报命令正文；命令级白名单另立 shim 变更。
- 不区分失败、受阻、等待人工等第三档终态语义。
- 不修改 `/api/state` 的活跃时长、质量统计、feed 数量、Skill 统计或数据库 schema。

## 影响

- `frontend/`：新增可测试的步骤展示纯模块，并接入四个现有展示入口。
- `server/routes/board.py`：只调整 `_snapshot` 的当前步骤来源选择，不改变事件写入和聚合。
- `openspec/specs/board`：新增步骤来源和展示规则的 spec delta。
- `docs/wireframes/`、`docs/architecture/module-map.md`、`AGENTS.md`：同步“步骤显示为人话、未知回退原文”的展示约束。
- 测试：服务端补扫描行覆盖，前端补映射、未知 runtime、生命周期和多入口契约测试；实现后另做真实浏览器验收。
