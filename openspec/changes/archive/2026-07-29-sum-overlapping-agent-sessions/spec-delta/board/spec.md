# board spec delta：并行 Agent session 工作量时长累加

## 规则变更

- Agent 运行时长 MUST 先按 `session_id` 从服务端 `recv/last_seen` 构造连续活跃段；相邻事件距最后确认
  心跳 `> STALE_SECONDS=180` 秒时，旧段仍停在最后确认心跳，后续存活事件从自身 `recv` 开新段，
  迟到终态不得回填断线期间。
- 每个 session 的连续活跃段 MUST 独立按 `Asia/Shanghai` 统计日切分，再按最终身份
  `(operator, agent||runtime)` 逐 session 累加。不同 session 的区间即使完全或部分重叠也不得取并集、
  去重或封顶；同一最终身份单统计日的运行时长 MAY 超过 86,400 秒。
- Thread 的可观测计时单元是事件协议中的 `session_id`。同一 session 内不可见的并行线程不得推测性
  加权；同一 session 的重复心跳不得按事件条数重复计时。
- `/api/state` 卡片的 `today_active/week_active/active_series/active_days`、`agent_overview`、
  `totals.today_active`，以及 `/api/agents` 的 summary/comparison/daily/ranking/agents 和
  `/api/agent/{key}` 详情 MUST 复用同一逐 session 累加日序列，不得分别计算、取并集或应用 24 小时上限。
- `active_agents`、Agent 总数和窗口活跃天数 MUST 继续按最终身份或统计日去重；并行 session 只增加
  时长，不增加 Agent 数量或同一日的活跃天数。
- 既有原始事件能表达的历史 session MUST 在读侧自动按新口径重算；不得为本变更批量改写历史事件。

## 保持不变

- 服务端 `recv` 权威时间、`ACTIVE_ST`、60 秒推荐心跳、180 秒 stale、pending batch 原子交接、
  `heartbeat_resume`、迟到终态和活动流规则不变。
- API 路由、JSON 字段、整数秒单位、SQLite schema、事件协议字段、shim 和最终身份卡片合并规则不变。
- `quality.avg_sec` 继续使用各 session 有效连续段总时长除以完成 runs，不使用身份级区间并集。

## 可验证行为

- 同一 `alice::builder` 的 session A 为 `01:00–03:00`、session B 为 `02:00–04:00`：
  身份单日时长为 14,400 秒，不是 10,800 秒；两个完成 run 的 `quality.avg_sec` 为 7,200 秒。
- 上述 14,400 秒在 `/api/state` 卡片、`agent_overview.daily`、`totals.today_active`、
  `/api/agents?w=today` 的 summary/daily/ranking/agents 和 `/api/agent/alice::builder` 中一致。
- 同一身份 12 个 session 各有 86,399 秒有效区间：单日时长为 `12 * 86_399`，且
  `active_agents=1`、窗口活跃天数为 1。
- 两个重叠 session 分别跨越上海午夜时，每个 session 先按午夜切分，相邻两日分别累加；
  today/7d/custom 窗口只消费各自选择的日槽。
- 同一 session 的纯心跳、长断档恢复和迟到终态仍只计已确认连续段，离线区间不因新累加口径回填。
