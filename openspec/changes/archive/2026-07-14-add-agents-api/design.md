# 设计：add-agents-api

字符图见 `wireframes.md`，行为增量见 `spec-delta/board/spec.md`。

## 方案

### 1. 独立 Agents payload

在 board 域新增 `agents_overview_payload`，输入已经按 `operator + agent||runtime` 合并的身份卡片和查询参数，输出：

- `today`：服务端 `Asia/Shanghai` 统计日。
- `window`：规范化的 key、起止日、日序列和上一同长窗口。
- `summary`：筛选集合的 Agent 总数、在线数、窗口活跃 Agent、窗口总时长、平均时长、累计质量、Shim 与待处理数量。
- `comparison`：当前/上一窗口统计与完整性标记。
- `daily`：当前窗口逐日总时长、活跃 Agent 数以及按 Agent identity 分段的时长。
- `ranking`：仅正时长 Agent，固定按 `active_seconds DESC, key ASC` 排序并带 `rank`；每项显式返回 `operator/agent/runtime`。
- `agents`：全部筛选后身份卡片及其窗口 `active_seconds/active_days`，按 `sort` 排序，供响应式明细表消费。
- `signals` 与 `shim`：问题线索数量和当前 shim 版本。

接口的身份 key 使用现有 `operator::agentOrRuntime`，既能稳定下钻 `/agent/:key`，也避免同名 Agent 跨身份合并。`ranking[]` 和 `agents[]` 均保留 `operator`、`agent` 与 `runtime`，供其它消费者自行组装展示名；Agent card 继续包含现有页面展示所需的任务、步骤、质量、Skills、MCP、Shim 与最近活跃字段。

底部 Agent 明细表新增独立“操作员”列，直接显示 `agents[].operator`。该字段只用于识别和组装信息，不重新引入操作员筛选；运行终端列继续不显示。桌面完整显示，平板跟随表格盒内横滚，手机摘要在 Agent identity 区下方显示操作员。

### 2. 时间窗与过滤

服务端实现与当前前端一致的预设窗口：`today/this_week/last_week/7d/14d/30d/90d`。`custom` 的 `wstart/wend` 是 Unix 秒，使用 `datetime.fromtimestamp(..., tz=Asia/Shanghai)` 映射统计日；两端都必填，起日不得晚于止日，含首尾最多 90 天，且起点不得早于当前 90 天 `active_days` 保留序列。终点可以延伸到未来，未来日期按当前时点输出 0。

`q/status/signal` 在服务端过滤 Agent 集合；搜索只匹配 Agent 名、任务、当前步骤和 model。问题线索复刻当前页面规则：异常/阻塞、Shim outdated/unknown、最近 14 天无活跃、至少 3 runs 且成功率低于 80%。`sort` 支持现有 `window_time/window_days/recent/success/errors/name`，旧 `today/week` 兼容映射。custom 起点不得早于保留期，终点允许延伸到未来，未来日期按当前时点输出 0，从而支持调用方给出的未来上界。

查询参数非法时明确返回 `400`，不静默降级到今天，避免 API 消费者误读统计窗口。默认 `w=today`、`status=all`、`sort=window_time`。

### 3. 快照复用边界

第一版复用 `_snapshot(conn)` 已有身份卡片，确保 profile、sticky shim、质量、活跃时长和身份合并口径与 `/api/state` 完全一致；Agents payload 只从快照的 `sessions/shim` 生成，不读取浏览器计算结果。保留 `/api/state.agent_overview` 供旧消费者兼容。

若后续性能数据显示 `_snapshot` 中 Skills 聚合成为独立接口瓶颈，再单独抽取共享的 Agent card builder；本次不在没有性能证据时扩大重构面。

### 4. 前端独立加载

新增 `useAgentsOverview(query)`，完整 URL 变化即发起 `/api/agents?...`，旧请求用 `AbortController` 取消。`AgentsRoute` 不再由 `StateRoute` 包裹，先挂载自身 loading 组件；成功后把 payload 交给 `Agents`，失败显示可重试错误态。

`Agents` 保留 URL 控件和展示组件，但排行、明细、趋势、KPI、signal 计数直接消费服务端字段，不再从全局 `StatePayload.sessions` 重算。页面 query 规范化仍使用 replace，接口请求只发送规范参数。

`w=custom` 的 URL 允许用户分两次填写起止时间。任一端缺失时前端暂不发请求，并显示待填写的中性加载态；两端齐全后才请求严格的 custom API。直接调用 API 时缺少任一端仍返回 `400`。

加载 skeleton 保留桌面/平板/手机现有区块顺序与大致高度，不制造布局跳变；它是同路由的 transient state，不新增页面或流转节点。

## 测试

### 单元测试

- `GET /api/agents` 默认今天，返回完整契约且排行/明细来自合并后的身份卡片。
- `w=7d/14d/30d/90d/this_week/last_week` 的起止日、日数和累计时长正确。
- `w=custom` 按上海统计日解析 Unix 秒；缺参数、倒序、91 天、起点早于可用 90 天序列均为 `400`；未来终点返回零值日期槽。
- 同一身份多 session 只保留一个 Agent；同名不同 identity 不合并。
- `ranking[]` 与 `agents[]` 均包含 `operator/agent/runtime/key`，外部消费者无需解析 key 即可组装 Agent + Operator 展示名。
- Agent 明细表显示 `operator`，但控制条仍没有操作员筛选，搜索仍不匹配 operator/runtime。
- ranking 排除零时长、按时长降序且平手按 key；agents 按六种 sort 正确。
- `q/status/signal` 与页面规则一致，响应 summary/daily/ranking/agents 使用同一可见集合。
- 前端 query 构造、独立 loading/error/data 生命周期、skeleton 和 AgentsRoute 不依赖 `StateRoute`。

### AI / 运行验证

- 直接 curl `/api/agents?w=7d` 与 custom 示例，核对 `window`、`ranking` 和时长单位。
- 打开 `/agents`，网络中可见独立 `/api/agents` 请求；人为延迟时立即出现 skeleton，数据到达后无明显布局跳变。
- 切换 today/7d/custom、搜索、状态、signal 与 sort，URL 和请求 query 同步，页面各区块口径一致。
- 1440、768、375 三档核对 skeleton 与真实页面顺序，无页面根横向滚动；浅色/深色/system 下 shimmer 可读且不过度闪烁。
- 跑服务端 pytest/覆盖率、前端 unit/build。

## 权衡

- 选择一个完整 `/api/agents` payload，而不是只返回排行：页面独立加载需要 KPI、趋势、问题线索和明细共享同一服务端窗口，否则仍会依赖 `/api/state`。
- 第一版复用 `_snapshot` 而不复制 SQL：一致性优先，避免两套身份/profile/质量计算逐渐漂移；代价是仍会执行快照中的其它聚合，后续用真实性能数据决定是否抽取。
- 保留客户端 URL 模型但把业务统计移到服务端：URL 仍由 React 控制，所有可复用统计事实由 API 输出。

## 风险

- Python 与旧 TypeScript 窗口/信号规则可能漂移；实现后让页面只消费服务端结果，并以接口契约测试锁定口径。
- query 连续输入可能产生竞态；请求 hook 必须取消旧请求，只接受当前 URL 的响应。
- 复用 `_snapshot` 可能让独立接口计算偏重；不新增第二套缓存，先用现有小团队数据和测试验证，若有证据再抽取 Agent card 构建。
- `/agents` 从全局状态解耦后 TopBar 仍可后台消费全局 state；页面主体不得因 TopBar 数据缺失而阻塞。

## 方案反思

- 完整 payload 是页面真正解耦全局 state 的必要条件；只加 ranking 会让 KPI、趋势或明细继续等待旧快照，因此维持 `summary/comparison/daily/ranking/agents/signals` 一体输出。
- `custom` URL 的增量填写与严格 API 校验存在中间态冲突，已明确由前端在两端齐全前暂停请求，避免把不完整输入误降级为“今天”或短暂显示 400。
- 第一版复用 `_snapshot` 保证口径，但必须用接口测试锁住身份合并和 90 天边界；若后续需要性能抽取，应保持 payload 函数只依赖 cards，便于无行为变化地替换数据装配层。

## 实现后反思

- 实现保持了 payload 的单一事实源：KPI、线索、排行、趋势和明细都来自同一次 `/api/agents` 响应；`/api/state.agent_overview` 未删除，旧消费者不受影响。
- `ranking[]`、`agents[]` 和逐日 `segments[]` 均显式带 `operator`。页面底部桌面表格新增操作员列，手机摘要也显示操作员；控制条没有重新加入操作员或运行终端筛选，搜索也不匹配这两个字段。
- 自定义窗口的半填写状态不会请求严格 API，而是显示中性 skeleton；两端齐全后才发送 custom query。直接调用接口仍严格返回 `400`，避免把不完整窗口伪装成今天。
- 浏览器在 1280、768、375 三档验证了桌面双栏、平板表格盒内横滚、手机摘要和页面根无横向溢出；接口样例验证了操作员及秒级时长。服务端全量测试与覆盖率、前端单测和生产构建均通过。
