# board spec delta：Agent 运行时长连续段与身份并集

## 规则增量

- Agent 运行时长 MUST 先按 session 从原始事件构造连续活跃段，再按最终身份 `operator + agent||runtime` 对全部 session 区间取并集，最后按 `Asia/Shanghai` 统计日切分。不得直接相加同一身份的重叠 session。
- 连续段只延伸到最后一次已确认心跳；相邻事件距当前段最后确认心跳 `> STALE_SECONDS=180` 秒时 MUST 在最后确认心跳关闭旧段。后续存活事件从自身服务端 `recv` 开新段。
- 长断档后的迟到 `done/error/idle` 只关闭当前连续段；若没有当前段，只记录终态/质量，不得回填断线期间。
- 同一最终身份单统计日的 `active_seconds` MUST 小于等于 86,400 秒；同名但不同身份不得合并。
- `/api/state` 卡片的 `today_active/week_active/active_series/active_days`、`agent_overview`、`totals.today_active`，以及 `/api/agents` 的 summary/comparison/daily/ranking/agents 和 `/agent/:key` 详情 MUST 复用同一身份并集日序列，不得分别计算另一套时长。
- 既有原始事件能表达的历史重叠与断档 MUST 在读侧自动恢复；不得为本修复批量改写历史事件或推测已经丢失的断档。

## 前端增量

- Agents 明细最右列展示 `ago(last_seen)` 语义时，标题 MUST 明确为“距上次活跃 / Time since last active”，不得使用容易被理解为运行时长的模糊文案。

## 可验证行为增量

- 同一 Agent 两个部分重叠 session 的 `active_days`、Agents 日趋势、排行、八卡总时长和明细窗口时长等于区间并集，不等于 session 时长之和。
- 连续段跨上海午夜时按日边界切开；跨窗口查询只消费共同 `active_days` 中所选统计日。
- 未来窗口保持零值日期槽并标记 current comparison 不可用，且不得改变已经发生日的身份并集时长。
