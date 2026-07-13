# 设计：agents-followup-integrity

本文件只谈实现口径与权衡。字符图见 `wireframes.md`，任务拆解见 `tasks.md`，规范增量见 `spec-delta/board/spec.md`。

## 方案

### 1. 摘要事实恢复

在时间窗变化卡片之后、问题线索之前恢复原 Agents 摘要条，继续使用既有 `summary` 数据：Agent 总数、运行中、今日活跃/本周活跃、运行质量、待处理 Agent。变化卡片只负责当前窗口与上一窗口变化，不替代这些稳定摘要。

### 2. Custom 时间窗与服务日

`agentFiltersQuery` 在 `w=custom` 时分别写入已有的 `wstart` 与 `wend`，允许用户先填任一端再填另一端。`parseUnixDay` 将 Unix instant 转换为 `Asia/Shanghai` 日期后再与 `agent_overview.days` 对齐，避免浏览器本地时间与服务日错位。

### 3. 排行视角 URL 状态

`AgentFilters` 增加 `rank: runtime | operator`，缺省为 `runtime`；顶部视角分段按钮通过 replace 更新 `rank`，`AgentRankPanel` 只消费解析后的视角，不再维护本地 `useState`。`rank` 不作为 Agent 卡片筛选条件，不改变 clear filters 对 q/status/signal/w/rt/op/sort 的既有语义。

### 4. 测试与验收

新增测试覆盖 custom 单端/双端 URL 保留、上海服务日边界、rank URL round-trip、窗口聚合结果与摘要不影响窗口计算。浏览器验收精确覆盖 1440×900 的左右布局/底边对齐，以及 1080/1081 和 375 的单列/无根横滚；lint 运行结果区分本 change 文件与既有未修改文件。

## 权衡

- 恢复摘要条会增加首屏信息，但它是已有事实展示，避免为了新卡片而发生无需求删除。
- 使用固定 `Asia/Shanghai` 服务日转换而不是浏览器本地日期，遵守项目统计事实源；具体时刻仍保留 Unix instant。
- 视角参数使用 `rank`，避免与其他 Agents 筛选字段混淆；不把它写入浏览器存储。
