# 提案：agents-stacked-trend-table

## 背景

Agents 运营页虽然已经具备 Runtime/操作员视角、时间窗和排行，但活跃趋势仍只画每日总量，无法回答“某一天由哪些 Runtime 或操作员构成”。底部 Agent 明细仍是两列卡片，卡片展示固定的今天/本周活跃值，与顶部所选时间窗不一致，也不利于横向比较多个 Agent。

## 提案

- 将 Agents 活跃趋势改为按当前视角切换的每日堆叠柱状图：Runtime 视角按 Runtime 分段，操作员视角按操作员分段；保留“活跃 Agent / 活跃时长”指标切换。
- 每日分段保留当前筛选后的 Top 8，剩余分组合并为“其他”，图例和日明细显示分布与合计。
- 将底部 `// Agent 明细` 从卡片网格改为可比较、整行可下钻的响应式表格。
- 表格行使用与顶部控制条一致的可见 Agent 集合，并按当前时间窗计算活跃时长和活跃天数；状态、任务、运行质量、资源、Shim 与最后活跃保持各自真实快照/累计语义。
- 将每日分段、窗口行统计和窗口排序抽为纯函数并补充前端单测，更新 Agents 线框与 board 事实源。

## 影响

- 影响 `frontend/src/views/Agents.tsx`、`frontend/src/components/agents/`、`frontend/src/lib/agentsDashboard.ts`、类型、文案、样式和前端单测。
- 影响 `/agents` 的展示与排序语义；不改变 `/api/state`、事件协议、数据库结构或 Agent 身份合并规则。
- 更新 `openspec/specs/board/spec.md`、`docs/wireframes/pages/agents.md`、模块地图与根 `AGENTS.md` 中的 Agents 视图约束。
