# 设计：agents-window-controls-layout

本文件只谈产品口径与实现权衡。字符图见 `wireframes.md`，任务拆解见 `tasks.md`，spec 增删改见 `spec-delta/board/spec.md`。

## 方案

### 1. URL 与时间窗

扩展 `AgentFilters`：

- `w`: `today | this_week | last_week | 7d | 14d | 30d | 90d | custom`，缺省解释为 `today`；
- `wstart/wend`: 自定义窗口的 Unix 秒参数；
- 原有 `q/status/signal/rt/op/sort` 不变。

时间窗解析以 `/api/state.agent_overview.today` 为右端，保证 Agents 与服务端 `Asia/Shanghai` 统计日一致。`today`、本周、上周按 Skills 的 Monday-based 周口径解析，固定天数窗口最多使用已有 90 天序列；非法或无效 custom 回退到 today。

### 2. 窗口聚合

新增 `agentWindowStats` 纯函数，输入当前可见 Agent、窗口 key 与 overview.today，输出：

- 当前窗口内至少有一天活跃的去重 Agent 数；
- 当前窗口累加活跃秒数；
- 上一同长度窗口对应的 Agent 数和活跃秒数；
- 当前快照在线数、运行质量沿用现有 overview.summary。

变化百分比使用 Skills 相同的规则：`(current - previous) / max(1, previous)`；前期为 0 且本期大于 0 显示 `+∞%`，两边为 0 显示 `—`。默认 today 时前一窗口为昨天；数据不存在时显示 `—`，不伪造趋势。

排行榜沿用现有 Runtime/Operator 分组数据，但按当前窗口重新计算每个组的活跃 Agent 数、活跃秒数与成功率，点击行仍只回填 `rt` 或 `op`。趋势图只绘制选中窗口的日序列，并在窗口右端等于 today 时高亮今日。

### 3. 组件与版式

- `AgentsToolbar` 继续承担 Runtime/Operator 视角切换、搜索、状态、时间窗、Runtime、操作员、排序；桌面与平板 label/input 保持同一行，手机折叠为一行摘要。
- 新增 `AgentWindowBar`，复用 Skills 时间窗变化区的 `.skills-kpi`/`.skills-kpi-card` 独立卡片结构，展示四项窗口结论；卡片不下钻，问题线索仍用 `.skills-health`/`.signal` 的紧凑样式并可点击筛选。
- `AgentRankPanel` 与 `AgentActivityChart` 保持 Agents 数据职责，但调整外框、排行 track、趋势 chart-box 的视觉和布局，使其与 Skills 主分析区组件语言一致；不复用 Skill 专属数据组件，避免错误引入 Skill 口径。
- 桌面 `.agents-analysis` 改为 `minmax(0, .75fr) minmax(0, 1.25fr)`，即左排行、右趋势；两张卡片等高。`<=1080px` 单列，手机问题条和窗口条均可换行但根页面不横滚。

## 权衡

- 不新增后端窗口聚合：已有 90 天逐日活跃序列足以支持本次窗口交互，避免第二个 `/api/state` 源和服务端 API 变更；代价是运行质量仍为当前快照/已有聚合，不提供按窗口严格切片的 runs。
- 不把 Agent 排行强行改成 `RankBars`：`RankBars` 绑定 Skill 名、来源、证据跳转和 `sel`，直接复用会污染语义；本次复用相同视觉规范与条形轨道。
- 自定义窗口只在已有 90 天数据范围内显示有效数据，超出部分自然为空；不伪造历史。

## 风险

- 浏览器时区与服务端统计日可能不同；解析以响应中的 `overview.today` 为准，避免页面切换时受客户端日期影响。
- 当前窗口过滤只影响 Agents 分析层和对比栏，不改变 Agent 卡片的“今日/本周”辅助字段；保留卡片既有事实语义，避免同一张卡随筛选改变字段含义。
