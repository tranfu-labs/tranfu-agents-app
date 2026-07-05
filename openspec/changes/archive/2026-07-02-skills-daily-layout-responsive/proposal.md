# 变更提案:skills-daily-layout-responsive(SKILLS 每日使用响应式布局)

- 状态:Proposed
- 关联:specs/board、docs/wireframes/pages/skills.md、archive/2026-07-01-reflow-skills-trend-window

## 背景 / 问题
线上 `/skills` 在 14 寸桌面视口下,默认 `7d` 的「每日使用」柱图只占排行卡片底部右侧一小段,
左侧留出大量空白。截图定位后确认,问题来自两个叠加因素:

1. `7d` 仍使用固定 30d 单日槽宽计算,轨道宽约 `54 + 7 * 28 = 250px`。
2. 趋势图被放在排行卡片下方,且右侧还有「待处理线索」侧栏,主分析区空间被分裂。

这不是单纯把 7d 拉宽的问题。用户确认新的布局策略:

- `14d`、`7d` 及更短窗口:主分析区整宽内「排行 Bar」和「每日使用」左右布局。
- `30d` 及更长窗口:主分析区整宽内「排行 Bar」和「每日使用」上下布局。
- 「待处理线索」独立为一行,每个分类是一个独立区块,不再挤占主分析区右栏。

## 目标
- `/skills` 根据当前窗口长度切换主分析区布局:
  - 短窗口 `today` / `this_week` / `last_week` / `7d` / `14d` / `custom<=14天`:排行与每日使用左右并列。
  - 长窗口 `30d` / `90d` / `custom>14天`:排行与每日使用上下堆叠。
- 「每日使用」在短窗口中填满自身面板宽度,避免桌面和平板大面积空白;长窗口保留图表内部横滚并默认显示最新日期。
- 「待处理线索」脱离主分析区侧栏,改为独立治理行;Skill 视角下 3 个分类各自为独立区块。
- 平板和手机保持单列主内容流,避免页面根横向滚动;长窗口横向滚动仍只发生在 `.chart-box` 内。
- 保持现有筛选、排行选中态、Operator 视角下钻、证据入口和数据口径不变。

## 非目标
- 不改 `/api/skills`、`/api/skills/evidence`、`/api/skill/{name}`、`/api/operator/{name}` 的后端聚合口径。
- 不引入图表库,不更换图表类型。
- 不改变 KPI、HealthBar、Donut、明细表、抽屉、公司库漏斗的业务内容。
- 不做「其它」段下钻、图例点击隔离或新的持久化配置。

## 方案概述
前端集中修改 `/skills` 总览:

- `frontend/src/views/Skills.tsx`:把主分析区拆成「排行模块」「每日使用模块」「待处理线索行」三块;
  按当前 `chartDays` / window key 给主分析区加短/长窗口布局类。
- `frontend/src/components/Charts.tsx` 与 `frontend/src/lib/skillsChartLayout.ts`:新增短窗口自适应宽度策略,
  `<=14` 天填满可视图表宽度,`>=30` 天继续固定单日槽宽 + 内部横滚。
- `frontend/src/components/skills/GovernanceTodo.tsx`:保持数据与动作,但输出可作为独立区块行使用的结构/类名;
  Skill 视角下 3 个分类并列或响应式换行。
- `frontend/src/styles.css`:新增短/长窗口主分析区、治理线索区块、平板/手机降级规则。
- `frontend/src/lib/skillsDashboard.test.ts` 或新增布局测试:覆盖短/长窗口图表布局决策。
- `docs/wireframes/pages/skills.md` 在归档时回流本变更线框。

## 影响
- board spec:更新 `/skills` 主分析区布局规则、趋势图短/长窗口宽度策略、待处理线索独立行与可验证行为。
- wireframes:更新 `/skills` 桌面短窗口、桌面长窗口、窄屏降级线框。
- 主要为前端与文档改动;不触碰采集、SQLite schema、服务端聚合口径。
