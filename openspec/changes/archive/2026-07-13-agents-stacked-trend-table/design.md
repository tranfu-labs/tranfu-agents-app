# 设计：agents-stacked-trend-table

字符图见 `wireframes.md`，任务见 `tasks.md`，行为增量见 `spec-delta/board/spec.md`。

## 方案

### 1. 单一筛选与窗口事实源

`/agents` 继续从 URL 解析 `rank/q/status/signal/w/wstart/wend/rt/op/sort`。先按非排序筛选得到可见 Agent，再使用 `/api/state.agent_overview.today`、`agent_overview.days` 和每张卡的 `active_days` 计算当前窗口行统计，最后按选择的排序项排列。排行、趋势、窗口 KPI 和明细表全部消费同一份可见 Agent 与同一窗口。

明细表的窗口字段严格随当前窗口变化：

- `active_seconds`：该 Agent 在窗口内的逐日活跃秒数之和；
- `active_days`：窗口内活跃秒数大于 0 的天数。

状态、当前任务/步骤和最后活跃是当前快照；运行质量来自现有 `quality` 聚合，界面标为累计运行质量，不伪造成窗口质量；Skills/MCP 与 Shim 来自最新 profile/心跳。

排序选项把旧的固定“今天活跃/本周活跃”调整为“窗口活跃时长/窗口活跃天数”。旧 URL 的 `sort=today|week` 兼容映射到新窗口排序，不让历史链接失效。

### 2. Runtime/操作员堆叠趋势

新增纯函数按 `window.days × visibleAgents` 生成两套分段日序列：

- Runtime 视角的 segment key 为 `agent.runtime`；
- 操作员视角的 segment key 为 `agent.operator`，缺失时使用明确的“未标记”分组；
- 每个 segment 同时累计 `active_agents` 与 `active_seconds`；一个 Agent 在一天内只进入一个 Runtime 和一个操作员分段，因此所有分段之和必须等于每日总量。

图表按当前指标选择数值，先按整个窗口的总量选 Top 8，其余合并为 `__other`。每一天画一根堆叠柱；图例按窗口总量排序，hover/focus 可强调对应分段；柱子 hover/click 显示日期、当天各分段降序明细与合计。窗口右端为服务端 `today` 时保留进行中纹理。

短窗口填满图表可视宽度并限制柱宽；长窗口只在 `.chart-box` 内横向滚动并默认定位最新日期，页面根不横滚。

### 3. Agent 明细表

新增 `AgentDirectoryTable`，桌面列为：

1. Agent（名称、状态、任务/步骤）；
2. 操作员；
3. Runtime；
4. 当前时间窗（活跃时长、活跃天数）；
5. 累计运行质量（成功率、runs/errors）；
6. 资源（Skills/MCP）；
7. Shim；
8. 最后活跃。

整行点击、Enter 或 Space 下钻 `/agent/:key`，局部链接/按钮阻止冒泡。平板允许表格容器内部横滚；手机不展示桌面表头，行压缩为多行摘要，仍保留 `<table>` 语义和整行键盘下钻。空态沿用 Agents 现有空态。

### 4. 可测性评估

- `frontend/src/lib/agentsDashboard.ts`：包含每日分段、窗口统计、兼容解析和排序，属于可测纯逻辑，必须补单测。
- `AgentActivityChart.tsx`：负责 SVG/交互，数据模型由纯函数提供；组件不再重复聚合逻辑，走 AI 视觉验证。
- `AgentDirectoryTable.tsx`：纯展示与导航，行数据由纯函数提供；走 AI 视觉与键盘验证。
- `styles.css`：纯 CSS，若单文件 diff 超过 200 行也不强制单测，但必须在三档视口和深浅主题做视觉验证。

## 权衡

- 不扩展服务端 API：`sessions[].active_days` 已是每个 Agent 的 90 天日级事实，前端筛选后才能正确重算任意 `q/status/signal/rt/op` 组合；服务端总览无法预生成所有组合。代价是聚合在浏览器执行，但规模仅为 Agent 数 × 最多 90 天。
- 不把运行质量包装成窗口指标：当前 payload 没有逐日 runs/success/error，贸然按窗口展示会制造错误事实。本轮明确标为累计质量。
- 操作员超过 8 个时合并“其他”，避免图例和配色失控；日明细仍显示“其他”合计，不丢总量。
- 表格在手机使用摘要行而不是退回卡片，保证相同信息结构跨断点一致。

## 风险

- 堆叠高度取整可能产生 1–2px 视觉误差；每个 segment 按共同 scale 计算，tooltip 数值使用原始整数。
- 缺失 operator 的 Agent 若被静默丢弃会破坏总量；必须放入“未标记”分组并由测试守住。
- 旧 `sort=today|week` 若直接删除会破坏分享链接；解析层保留兼容映射。
