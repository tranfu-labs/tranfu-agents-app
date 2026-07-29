# 设计：sum-overlapping-agent-sessions

行为增量见 `spec-delta/board/spec.md`。本变更不修改页面信息架构，因此不新增线框图。

## 方案

### 1. 计时分层与术语

继续把运行时长分成两个独立阶段：

1. **session 连续段**：`_session_active_intervals(rows)` 以服务端 `recv/last_seen` 为时间证据，
   按 `STALE_SECONDS=180` 切断未确认的离线区间。存活态只延伸到最后确认心跳，恢复事件从自身
   `recv` 开新段，迟到 `done/error/idle` 不回填断线期间。
2. **身份工作量日序列**：每个 session 的有效连续段分别按 `Asia/Shanghai` 午夜切分，再把同一
   最终身份 `operator + agent||runtime` 下所有 session 的日秒数相加。

第二阶段不再对跨 session 区间做 `_merge_intervals`。两个 session 各自运行两小时，即使其中一小时
重叠，身份工作量仍为四小时。重叠只在不同 `session_id` 之间有意重复计量；同一 session 内的重复
心跳仍由写侧去重和连续段构造折叠，不会按心跳条数重复计量。

这里的 Thread 是采集协议可观测到的独立 `session_id`。本变更不新增 `thread_id` 字段，也不推测
同一个 session 内部不可见的并行子线程。

### 2. 聚合实现

`metrics(conn)` 遍历 `_iter_sessions(conn)` 时：

- 继续为每个 session 调用 `_session_active_intervals(rows)`。
- 继续把 session 区间总秒数累加到质量块的 `q["active"]`，因此 `quality.avg_sec` 的既有
  “各 run 有效活跃时间 / 完成 runs”语义不变。
- 对每个有效 `(start, end)` 直接调用唯一的上海日切分函数 `add(key, start, end)`。
- 删除身份级 `intervals_by_identity` 汇总和 `_merge_intervals`，避免代码仍暗含墙钟并集口径。

SQLite 事件、历史数据和缓存结构不变。部署后第一次重算 state snapshot 即按新规则解释保留的
90 天事件，不需要数据迁移或批量回填。

### 3. 消费者与派生指标

`_snapshot` 仍把 `metrics()` 产生的同一 `active_days[90]` 注入最终身份卡片，以下消费者不得另算：

- `/api/state.sessions[].today_active/week_active/active_series/active_days`
- `/api/state.agent_overview` 与 `totals.today_active`
- `/api/agents` 的 `summary/comparison/daily/ranking/agents/signals`
- `/api/agent/{key}` 详情
- `/`、`/agents`、`/agent/:key` 对上述字段的展示和前端 fallback 聚合

派生规则：

- `active_seconds`、`today_active`、`week_active` 和平均运行时长允许超过对应窗口的墙钟长度。
- `active_agents` 仍是窗口内时长大于零的最终身份数；不会按 session 数增加。
- `window_active_days` 仍是时长大于零的统计日数量；同一天十个并行 session 仍只贡献一个活跃日。
- 排行顺序、趋势分段和 tooltip 继续使用秒数相加，不引入 86,400 秒截断。
- API 字段类型与单位仍是整数秒，不增加并发数、成本或 token 字段。

### 4. ADR 与事实源

ADR-0013 是 Accepted，不能追溯改写其历史决策。新增 ADR-0025，完整重申以下保留规则并替换其
身份并集部分：

- 服务端 `recv` 是时长权威时间。
- `running/started/waiting/blocked` 为存活态。
- 推荐 60 秒心跳、180 秒 stale，断档与迟到终态规则不变。
- 最终身份时长改为逐 session 相加，允许超过 24 小时。

方案阶段 ADR-0025 保持 Proposed。实现验证通过并归档 change 时，把 ADR-0025 标为 Accepted，
ADR-0013 标为 Superseded，并同步 ADR 索引与所有当前事实源。

## 测试与验收依据

### 服务端自动化

- 两个同身份 session 分别为 `01:00–03:00` 和 `02:00–04:00`：
  - 身份时长为 `4 * 3600`，不是区间并集 `3 * 3600`。
  - `quality.avg_sec` 在两个完成 run 下为 `2 * 3600`。
  - `/api/state` 卡片、`agent_overview.daily`、`totals.today_active`、`/api/agents?w=today`
    的 summary/daily/ranking/agents 和 `/api/agent/{key}` 全部返回同一 `4 * 3600`。
- 同一身份 12 个 session 各覆盖上海统计日 86,399 秒：
  - 单日时长精确等于 `12 * 86_399`，明确大于 86,400，不得封顶或取并集。
  - `active_agents == 1`、`window_active_days == 1`。
- 同一 session 的连续纯心跳、pending flush、状态变化前固化末点：
  - 仍只按首尾确认时间计一次，不因心跳条数重复增加。
- pending 与并行累加组合回归：
  - 同一 `alice::builder` 下 session A 在 `00:00` 开始，`00:02` 纯心跳进入 pending；
    session B 在 `00:01–00:04` 运行，并在 A 的 pending 尚未 flush 时写入 `done` 状态变化；
    A 随后在 `00:10` 写入迟到 `done`。
  - B 的即时状态写入后，A 的 pending 末点仍为 `00:02`；A 写终态时先把该末点固化到旧行，
    不得丢失或回退，且 `00:02–00:10` 仍不计入。
  - A 有效区间为 120 秒，B 有效区间为 180 秒；两者重叠 60 秒但最终身份时长必须为
    `120 + 180 = 300` 秒，不得得到并集 240 秒。事件末点与 `/api/agents` 最终时长须在同一测试中断言。
- 旧 pending、乱序心跳与并行累加组合回归：
  - session A 已有 `00:00` 起点时，先后入队 `00:02` 与更旧的 `00:01:30` pending，
    再接收 `00:03` 的同状态重复心跳；pending 与最终 SQLite `last_seen` 必须单调推进到 `00:03`，
    A 始终只有一个事件行和一个 `00:00–00:03` 连续段。
  - flush 后再次注入早于 SQLite 的 `00:02:30` 旧 pending 并 flush，SQLite `last_seen` 仍保持
    `00:03`，不得回退、切出恢复行或产生额外区间。
  - 同身份 session B 同时运行 `00:01–00:04`；A、B 各 180 秒，最终身份时长必须为
    `180 + 180 = 360` 秒，`active_agents == 1`。该断言证明并行 session 可叠加没有放松
    单 session 的心跳去重与单调性。
- 同一 session 的长断档恢复和迟到终态：
  - 旧段停在最后确认心跳，新存活段从恢复 `recv` 开始，离线区间仍为零。
- 两个重叠 session 跨上海午夜：
  - 每个 session 先正确切到相邻统计日，再逐日相加；today/7d/custom 只消费所选日槽。
- 同名不同 operator 或不同 `agent||runtime`：
  - 身份卡片和 `active_agents` 保持隔离，汇总时长只在 summary 层自然相加。
- 未来窗口、comparison 可用性、零时长排行排除等既有行为不变。

### 前端自动化

- `dur()` 对大于 86,400 秒的值输出累计小时数而非按天取模或截断。
- Agents 排行、趋势、tooltip、八卡和明细继续直接消费服务端秒数；现有组件测试不得引入 24 小时上限。

### 真实运行验收

在本地测试数据库固定统计日并写入同一 `alice::builder` 的两个重叠完成 session
`01:00–03:00`、`02:00–04:00`：

1. 打开 `/agents?w=today`，可断言：
   - “总运行时长”和平均运行时长显示 `4h`；
   - `alice::builder` 排行与明细窗口时长均显示 `4h`；
   - 单日环形图中心及 tooltip 总时长显示 `4h`，活跃 Agent 仍为 `1`。
2. 打开 `/agent/alice%3A%3Abuilder`，可断言今日时长显示 `4h`。
3. 打开 `/`，可断言同一 Agent 卡片今日时长显示 `4h`。
4. 把夹具扩为 12 个近全天重叠 session 后刷新 `/agents?w=today`，可断言该 Agent 时长明显超过
   `24h`，页面无截断、数值溢出或根横向滚动。

## 权衡

- 选择逐 session 累加，因为目标指标是并行工作量代理，而不是“这个身份占用了多少墙钟时间”。
  代价是该时长不能再解释为自然日在线时长，也不能用于推导利用率百分比。
- 不新增“墙钟时长”和“工作量时长”双字段：当前产品只要求改变既有 Agent 运行时长口径；双指标会扩大
  API、UI 和解释成本。若未来需要利用率，应另案新增明确命名的墙钟指标。
- 不按并发峰值或心跳次数加权：不同 session 的确认区间已有可审计证据，心跳次数受发送频率影响，
  不能代表工作量。
- 不新增 interval 表或数据迁移：原始事件足以按新规则重算，继续保留单一事实源。
- 不修改 ingest：写侧已经按 `session_id` 隔离去重并准确保留连续段边界，本次只改变读侧跨 session 聚合。

## 风险与回滚

- **语义误读**：单日大于 24 小时可能被误认为数据异常。通过 spec、ADR、协议和部署文档明确这是
  并行 session 工作量之和。
- **重复 session_id**：同一真实线程若被错误上报为多个 session，会重复计量；这是输入身份质量问题，
  本变更不做不可验证的跨 session 猜测去重。
- **不可见线程**：同一 session 内部的并行线程无法从现有协议识别，因此不会额外计量；文档明确
  可观测粒度是 `session_id`。
- **消费者遗漏**：若某个 API 或前端 fallback 自行封顶，会产生口径分叉；端到端断言覆盖全部既有时长消费者。
- **回滚**：代码层可恢复身份级 `_merge_intervals`；事件 schema 与历史数据未变，回滚不需数据处理。

## 方案反思

- 方案只反转跨 session 聚合，不撤销刚修复的心跳准确性和断档边界，避免把“允许并行累加”误做成
  “允许离线虚增”。
- 以 `session_id` 明确 Thread 的可观测边界，既符合现有协议，也暴露了同 session 内并行不可见的限制。
- 所有展示继续消费一份 `active_days`，没有为八卡、排行或详情创建第二套计算。
- 新 ADR 取代而非静默改写 Accepted 决策，保留从墙钟口径切换到工作量口径的原因和代价。

## 实现后反思

- `metrics()` 只删除身份级 `_merge_intervals`，每个 `_session_active_intervals()` 结果直接进入唯一的
  上海日分桶；心跳、pending、断档恢复、迟到终态和写侧代码均未改变。
- 质量 `avg_sec` 继续累计每个 session 的有效连续段；最终身份卡片和全部 API 消费同一
  `active_days`，没有出现第二套聚合或字段变更。
- pending × 并行组合回归锁定 300 秒，旧 pending/乱序心跳 × 并行组合回归锁定 360 秒；
  两者同时证明跨 session 可叠加、单 session 仍去重且最后确认时间单调不减。
- 12 个近全天 session 的自动化回归得到 `12 * 86_399` 秒；真实页面另以 26h 单 Agent 验证
  累计小时显示、排行、明细和无根横向溢出。
- QUICKSTART、USAGE、shim、schema、协议字段和线框均无需修改；事实源只替换原有“身份并集/每日上限”
  陈述，没有顺手整理。

## 验证结果

- `python -m py_compile server/*.py server/routes/*.py`：通过。
- `python -m pytest -q`：408 passed。
- `python -m coverage run -m pytest -q`：408 passed；
  `python -m coverage report --include='server/**/*.py'`：整体 96%，`board.py` 96%，`ingest.py` 96%。
- `npm --prefix frontend run test:unit`：88 passed。
- `npm --prefix frontend run build`：通过；仅保留既有单 chunk 超过 500 kB 的 Vite warning。
- 真实浏览器 `/agents?w=today`：4h 八卡、排行、环形图、tooltip 与明细一致，活跃 Agent 为 1；
  `/agent/alice::builder` 显示“今日 4h · 本周 4h”；`/` 卡片显示“今日 4h”。
- 大于 24 小时页面夹具：heavy 单 Agent 显示 26h / 1 天，总计 30h；
  页面根 `scrollWidth == clientWidth == 1891`。
