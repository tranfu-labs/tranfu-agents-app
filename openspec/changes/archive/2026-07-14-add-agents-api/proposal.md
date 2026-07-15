# 提案：add-agents-api

## 背景

`/agents` 当前没有独立读接口。React 页面先等待全局 `/api/state` 或 `/api/state/stream`，再从每张身份卡片的 90 天 `active_days` 在浏览器内解析 `w/wstart/wend`、累计运行时长并生成排行、趋势、KPI 与明细。这使外部消费者无法直接按指定时间窗取得 Agent 运行时长排行，也让 Agents 页面首屏被包含 feed、Skills 等无关数据的全局快照阻塞。

用户已确认需要独立的 `GET /api/agents`：预设窗口通过 `w` 指定，自定义窗口使用 Unix 秒级 `wstart/wend`，最多 90 天；接口至少提供排行榜与统计数据，Agents 页面也改为消费该接口并在加载期间显示 skeleton。

## 提案

- 新增 `GET /api/agents`，支持 `w=today|this_week|last_week|7d|14d|30d|90d|custom`、`wstart/wend`、`q/status/signal/sort`。
- 自定义时间按 `Asia/Shanghai` 统计日解释，最大 90 天；参数缺失、非法时间戳、顺序错误、超出 90 天或起点早于服务端 90 天保留序列时返回 `400`。终点可延伸到未来，未来日期按当前时点返回 0，但该窗口标记为不完整且不展示环比。
- 返回 `today/window/summary/comparison/daily/ranking/agents/signals/shim`。外部消费者可只读 `ranking`，页面用同一 payload 渲染 KPI、问题线索、趋势、排行和明细。
- 排行与明细继续遵守 `operator + agent||runtime` 身份合并，窗口时长按 `active_days` 汇总；排行按 `active_seconds` 降序并排除零时长 Agent。`ranking[]` 与 `agents[]` 都显式返回 `operator`、`agent`、`runtime` 和稳定 `key`，方便其它消费者组装 `${agent} - ${operator}` 等展示信息。
- `/agents` 底部 Agent 明细表新增“操作员”列，帮助页面内直接识别同名 Agent；运行终端仍不显示，操作员仍不作为筛选条件。
- `/agents` 从全局 `StateRoute` 解耦，独立请求 `/api/agents`；首次加载或切换 query 时显示与页面信息架构对应的 skeleton，失败显示可重试错误态且不得在新 URL 下继续展示旧 payload。custom 尚未填完时保留真实控制条，只将数据区置为 skeleton。
- 保留 `/api/state.agent_overview`、SSE 和 `/api/agent/{key}` 兼容，不改变采集协议、SQLite schema 或身份规则。

## 影响

- 服务端：`server/routes/board.py` 新增 Agents payload、参数校验和路由；复用现有快照身份卡片，不新增数据库或缓存依赖。
- 前端：`frontend/src/lib/api.ts`、`types.ts`、`App.tsx`、`views/Agents.tsx`、Agent 明细组件与 Agents 样式改为独立 loading/data/error 生命周期，并在底部表格增加操作员列。
- 测试：新增服务端接口契约/边界测试与前端 query/loading/payload 测试，并跑全量服务端覆盖率、前端单测与生产构建。
- 事实源：更新 board spec、模块地图、根/服务端 AGENTS 约定和 Agents wireframe 的加载态。
