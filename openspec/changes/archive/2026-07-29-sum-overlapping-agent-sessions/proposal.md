# 提案：sum-overlapping-agent-sessions

## 背景

当前 Agent 运行时长先按每个 session 的服务端心跳构造连续活跃段，再把同一最终身份
`operator + agent||runtime` 下所有 session 的重叠区间取并集。因此，同一 Agent 同时运行两个
Thread/Session 时，重叠的一小时只记一小时，指标表达的是墙钟占用时间，不能体现并行工作量。

目标是保留现有底层计时准确性：服务端 `recv` 仍是权威时间，纯心跳仍只推进最后确认时间，
超过 180 秒的断档仍切段，迟到终态仍不得回填离线时间；但最终身份聚合改为逐 session 累加。
同一 Agent 的多个并行 Thread/Session 即使时间重叠，也分别贡献时长，因此单 Agent 单日允许超过
86,400 秒。

## 提案

- 把 `session_id` 视为可观测并行工作的计时单元：每个 session 独立构造连续活跃段并按
  `Asia/Shanghai` 日边界切分，同一最终身份的各 session 日时长直接求和，不再取区间并集。
- 保留心跳去重、pending batch、180 秒断档恢复、迟到终态、服务端权威时间和历史事件读取规则，
  不改写历史数据。
- `/api/state`、`agent_overview`、`totals.today_active`、`/api/agents` 全部统计区块和
  `/api/agent/{key}` 继续复用同一身份日序列；`active_seconds`、`today_active` 等现有字段结构不变，
  但明确表示可叠加的 Agent 工作量时长，允许单身份单日超过 24 小时。
- `active_agents`、Agent 总数和活跃天数仍按最终身份去重，不因并行 session 数量翻倍；排行、
  趋势、八卡总时长、平均运行时长和明细窗口时长使用新的可叠加秒数。
- 用新 ADR 取代 ADR-0013 中“身份墙钟区间并集”的决策，同时重申其余服务端时间、存活态和断档规则。

## 影响

- 服务端 board 域：`server/routes/board.py` 的 session 连续段到身份日序列聚合。
- 服务端与前端测试：重叠 session、单日超过 24 小时、跨上海日边界和所有时长消费者的一致性。
- 对外语义：现有时长字段从“身份墙钟时长”改为“身份下各 session 可叠加的工作量时长”；
  JSON 字段、路由、SQLite schema、事件协议字段和 shim 均不变。
- 事实源：board spec、ADR、`AGENTS.md`、`server/AGENTS.md`、模块地图、`PROTOCOL.md` 和部署说明。
- 前端布局、交互、URL、线框和文案结构不变；现有时长格式化支持超过 24 小时的小时数。
