# 设计：fix-agent-active-duration-overcount

字符图见 `wireframes.md`，行为增量见 `spec-delta/{board,ingest}/spec.md`。

## 方案

### 1. 写侧保留断档边界

`POST /v1/events` 查询同一 `operator + runtime + agent||runtime + session_id` 最近事件时，同时读取该行 `last_seen`。若该行有尚未 flush 的批量心跳，以 pending map 中更新的时间作为最后确认心跳。

当新事件与最近事件状态、步骤相同：

- 间隔 `<= STALE_SECONDS`：保持现有纯心跳路径，批量或即时更新最近行 `last_seen`。
- 间隔 `> STALE_SECONDS`：删除该行 pending 心跳并插入一条新的事件行，以当前服务端 `recv` 同时作为新连续段的起点与 `last_seen`。响应使用 `logged=true`，使写侧 dirty 标记和 SSE 更新沿用真实插入路径。

状态或步骤变化仍插入新行；断档识别主要用于保住“同状态、同步骤恢复”这一当前会丢失的边界。
恢复边界行使用内部来源 `heartbeat_resume`：最新卡片与 metrics 读取它，活动流继续只读取
`source=heartbeat`，避免把同状态恢复伪装成一次状态变化。

### 2. session 连续段

board 域把每个 session 的事件按 `id` 顺序解释为连续活跃段：

- `ACTIVE_ST` 事件开始或延续当前段；该行 `last_seen` 是该段最后确认的存活时间。
- 下一事件距当前段最后确认心跳不超过 180 秒时，存活状态可连续；终态使用自身 `recv` 关闭当前段。
- 下一事件距当前段最后确认心跳超过 180 秒时，先在最后确认心跳关闭旧段。若下一事件仍为存活态，则从该事件 `recv` 开新段；若是迟到终态，只计质量结果，不产生或回填离线区间。
- session 最后仍为存活态时，段只延伸到最后确认心跳，不延伸到查询当前时间。

历史中状态或步骤变化已经留下新行，因此读侧可自动识别其断档；历史同状态、同步骤且已覆盖 `last_seen` 的断档边界不可逆丢失，本次不猜测、不批量改写。

### 3. 最终身份区间并集

每个 session 产出的区间先用于保留既有 session 质量指标；所有区间同时汇入最终身份 key `operator + agent||runtime`：

1. 按起点、终点排序。
2. 重叠或首尾相接的区间合并为一个区间。
3. 合并后的区间按 `Asia/Shanghai` 午夜切分，累加到 90 天 `active_days`。

因此同一 Agent 的并行 session 不再重复计时，单 Agent 单日自然不超过 86,400 秒。不同 operator 或不同 `agent||runtime` 身份保持隔离，不跨身份合并。

`_snapshot` 继续把同一 `active_days/today/week` 装入最终身份卡片；`/api/state.agent_overview`、`/api/agents` 的 summary/comparison/daily/ranking/agents 以及 `/agent/:key` 详情无需另算时长，从而复用同一口径。

### 4. 文案与线框

`agentLastSeen` 的中文从“最近活跃”改为“距上次活跃”，英文从 “Last active” 改为 “Time since last active”。值仍由 `ago(last_seen)` 计算，不改字段或交互。

## 单元测试

- 同一 Agent 两个完全重叠、部分重叠、相接 session：身份日时长为区间并集，排行、趋势、八卡和明细相等，单日不超过 86,400 秒。
- 同状态、同步骤在 180 秒内恢复：仍是纯心跳且不新增事件行。
- 同状态、同步骤在 180 秒后恢复：新增事件行并保留旧 `last_seen`；pending batch 中的最后确认心跳参与阈值判断。
- 历史不同步骤事件在长断档后恢复：读侧拆成两个连续段。
- 长断档后的迟到 `done/error`：只关闭当前连续段，不把旧段末尾到终态时间补回。
- 连续段跨上海午夜：按两日切分；跨自定义/7 日窗口只计窗口内日。
- 未来窗口继续返回未来零槽且 comparison unavailable。
- 线上异常形态回归：多个长时间重叠 session 的单 Agent 单日总时长小于等于 24 小时。
- 前端 i18n 测试锁定中英文“距上次活跃”语义。

## AI / 运行验证

- 用 TestClient 构造重叠、断档恢复和迟到终态事件，检查 `/api/state`、`/api/agents?w=today|7d|custom` 与 `/api/agent/{key}` 同一身份时长。
- 构造覆盖上海午夜的区间，核对 `active_days` 相邻两格与 Agents `daily`。
- 打开 `/agents` 桌面和手机布局，确认末列/摘要标签为“距上次活跃”，值仍为相对时间且没有布局溢出。
- 运行服务端 `py_compile`、全量 pytest 与覆盖率门槛；运行前端 unit 和生产 build。

## 权衡

- 不新增专门的 interval 表：现有事件行已经能表达状态变化和新的恢复边界，读侧重算可立即修复可恢复的历史数据，也避免迁移与双写一致性风险。
- 不在心跳断档后自动补 180 秒宽限：已确认口径是停在最后一次心跳，额外宽限会继续虚增且无法证明 Agent 实际运行。
- 不按 session 简单封顶或按日 `min(sum, 86400)`：硬截断会隐藏重叠位置并让窗口、趋势与明细无法共享真实区间；身份级并集才是可解释口径。
- 质量 `avg_sec` 继续保持“每次 run 的连续活跃时间”语义；身份总运行时长使用区间并集，两者不混为同一指标。

## 风险

- 旧数据中已被同状态心跳覆盖的断档无法恢复；实现只修复仍有证据的历史并阻止继续丢边界，不做推测性回填。
- pending batch 与 DB `last_seen` 可能不同步；断档判断必须在同一锁保护下读取 pending 最新值。
- 区间并集若误跨身份会少计；测试必须覆盖同名不同 operator 和不同 Agent identity。
- 读侧排序与时区切分改动影响所有活跃派生指标；以 `/api/state` 和 `/api/agents` 的端到端契约测试锁定共同事实源。

## 方案反思

- 方案同时修写侧证据丢失和读侧重复/断档聚合，避免只在前端或单一 API 打补丁。
- 最终身份并集发生在 session 连续段生成之后，既保留 session 终态质量，又保证 Agent 墙钟时长不重复。
- 迟到终态和恢复态使用同一“距最后确认心跳是否超过 180 秒”判断，没有为不同状态建立互相矛盾的例外。
- UI 只改语义不改数据字段，风险与线上误读问题相称。

## 实现后反思

- 写侧严格按方案使用 DB `last_seen` 与 pending map 中较新的时间判断连续性；长断档恢复前先把 pending 末点固化到旧行，再以 `heartbeat_resume` 插入新段，避免边界二次丢失。
- `heartbeat_resume` 被最新卡片和 metrics 读取，但 feed 仍只读 `source=heartbeat`，没有破坏“活动流只展示真实状态变化”的既有硬约束。
- 读侧以 `_session_active_intervals` 统一处理存活态、终态、长断档和迟到终态，再以 `_merge_intervals` 对最终身份的所有 session 取墙钟并集；上海日切分仍只有 `metrics.add` 一处。
- `/api/state`、`agent_overview`、`totals.today_active`、`/api/agents` 全部区块和 `/api/agent` 继续消费 `_snapshot` 注入的同一 `active_days`，没有新增第二套聚合。
- 质量 `avg_sec` 仍按各 run 的连续活跃段累计，身份墙钟总时长才取并集，符合两个指标原有不同语义。
- 历史事件不改写；状态/步骤变化留下的断档与重叠 session 会在读侧自动纠正，已经被覆盖的同状态旧断档不作猜测。
- 中英文文案、桌面表头和手机 `data-label` 均已更新；1440×900 与 375×812 浏览器验证无根横滚或列溢出。

## 验证结果

- `python -m py_compile server/*.py server/routes/*.py`：通过。
- `python -m coverage run -m pytest`：379 passed。
- `python -m coverage report --include='server/**/*.py'`：整体 97%，`server/routes/board.py` 95%，`server/routes/ingest.py` 96%。
- `npm --prefix frontend run test:unit`：77 passed。
- `npm --prefix frontend run build`：通过；仅保留既有单 chunk 超过 500kB 的 Vite warning。
- 本地 TestClient/浏览器：重叠、断档、pending、迟到终态、上海跨日、未来窗口、单日上限、统一 API 消费和响应式文案均通过。
