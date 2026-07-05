# 变更提案:reflow-skills-trend-window(SKILLS 趋势图布局与默认窗口)

- 状态:Proposed
- 关联:specs/board、docs/wireframes/pages/skills.md、skills-chart-timeaxis、skills-view-ux-polish

## 背景 / 问题
SKILLS 总览当前把「每日使用趋势图」放在 KPI/健康条之后、主排行之前，作为全宽独占层。这个结构在默认
30d 时可读性尚可，但当默认时间范围改为 7d 后，趋势图会因为天数变少而失去当前 30d 观察到的良好比例，
且全宽独占的视觉分量会超过它实际承担的任务。

经讨论，用户希望:

- `/skills` 默认时间范围改为 7d。
- 「每日使用趋势图」放到「使用排行 / 操作员排行」下方。
- 7d 时趋势图保持当前 30d 的单日槽宽，右对齐显示最新 7 天。
- 30d/90d/custom 较长窗口默认显示最新日期，向左滚动查看更早日期。

这不是简单移动组件，而是要把趋势图从「全局大图」改为「排行的时间解释图」，并把图表视窗尺寸与日期轨道长度解耦。

## 目标
- `/skills` 无 URL 参数进入时默认窗口为 `7d`，旧 `win` fallback 与新 `w` fallback 保持一致。
- 桌面布局改为「左:排行 + 趋势图 / 右:治理待办」；平板和手机单列顺序为「排行 -> 趋势图 -> 治理待办」。
- 趋势图使用固定单日槽宽，按当前 30d 观感定标；`7d`、`today`、`this_week` 等短窗口右对齐，不拉伸。
- `30d`、`90d`、`custom>7d` 使用内部横向滚动，进入或切换窗口后默认滚到最新日期。
- Skill 视角保留排行选中态联动趋势图；Operator 视角不新增排行行选中态，避免和点击行进入 operator 详情冲突。
- 保持 SKILLS 页面根节点无横向滚动；横向滚动只发生在图表内部。

## 非目标
- 不改变 `/api/skills`、`/api/skill/{name}`、`/api/operator/{name}` 的数据口径。
- 不更换图表类型，不引入图表库。
- 不调整 Donut、明细表、抽屉、公司库漏斗的业务内容。
- 不改变单 Skill 详情页和单 Operator 详情页的信息架构；若复用图表 helper，仅保证现有行为不退化。
- 不给 Operator 总览排行新增“选中而不跳转”的第二套交互。

## 方案概述
前端集中修改 `/skills` 总览:

- `frontend/src/lib/skillQuery.ts` / `frontend/src/lib/skillsWindow.ts`:默认窗口从 30d 改为 7d，并覆盖无参、旧 `win`、非法 fallback。
- `frontend/src/views/Skills.tsx`:把 `StackedSkillChart` 从全宽独占 section 移入排行 frame 的下半区；治理待办保留右列。
- `frontend/src/components/Charts.tsx`:把趋势图几何改为固定单日槽宽 + 固定视窗 + 可滚动日期轨道；短窗口右对齐，长窗口自动滚到最右。
- `frontend/src/styles.css`:补齐排行 frame 内部趋势图区、桌面 split、平板/手机单列、图表内部滚动与右对齐样式。
- `frontend/src/lib/skillsDashboard.test.ts` 或新增图表 layout 测试:覆盖默认 7d 与图表宽度/对齐/滚动决策。

## 影响
- board spec:更新 `/skills` 默认窗口、页面层级、趋势图放置位置、图表尺寸/滚动规则与可验证行为。
- wireframes:更新 `/skills` 三个断点下的大框架，明确趋势图位于排行下方、漏斗继续下沉。
- 仅前端改动为主；不触碰采集、SQLite schema、服务端聚合口径。
