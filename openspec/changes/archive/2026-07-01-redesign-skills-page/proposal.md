# 变更提案：redesign-skills-page（SKILLS 页仪表盘化改版）

- 状态：Proposed
- 关联：
  - 前身：`skills-stats-page`（第一版结构：过滤条→堆叠柱→排行+漏斗）
  - 参考：`token_usage` 页面结构（KPI 环带 + 健康条 + 主视图 + 归因 + 明细抽屉）
  - 记忆：[skills-stats-page-decisions](../../../.claude/projects/-Users-wing-Develop-tranfu-agents-app/memory/skills-stats-page-decisions.md)（主榜只排 used、漏斗 own+meta、Top8 堆叠柱）

## 背景 / 问题

现状 `frontend/src/views/Skills.tsx` 的结构是「视角切换 → 过滤条 → Top8 堆叠柱 → 排行表 + 漏斗」。它能回答「哪个 skill 最常用 / 谁用得多」，但**打开页面第一屏没有结论**——所有判断都埋在明细表里，用户要自己滑、自己算、自己对比。

对照 `frontend/src/views/TokenUsage.tsx` 的结构（KPI 环带 → 健康条 → 排行+风险并列 → 趋势 → 归因 Donut → 明细 + 抽屉），Skills 页缺 8 样东西：

1. **无 KPI 环带**——看不到「本期 vs 上期涨了多少、多少 skill 在用、覆盖率多少、闲置率多少」的一屏总览。
2. **无治理健康聚合**——治理只剩一个 Lens（未收录占比），其他判断（装了没用、覆盖率、集中度、闲置率）都要人在表里挖。
3. **时间维度太粗**——只有 7/30/90d 三档，没有环比、没有对比同期、没有自选窗口。
4. **无选中态贯穿**——点一个 skill 直接跳走详情页，没法在当前页高亮它、看它跟其他 skill 的对比。
5. **信息层级失衡**——右侧「漏斗」占黄金位，但它是低频看的静态快照；「风险 / 治理待办」这种高频决策入口缺失。
6. **无归因视图**——过滤器里有 runtime / 来源两个维度，但没做出「按来源占比」「按 runtime 占比」两张 Donut。
7. **无长尾聚合**——排行表全量渲染，没有「其他 N 个 skill」这种收敛动作。
8. **无明细抽屉、无 CSV 导出**——点一行只能跳页；数据带不走。

一句话：**Token Usage 是「先给结论 → 再给切片 → 再给原始表」，Skills 现在是「先给原始表 → 让人自己找结论」**。这次改版把这条主线换过来。

## 目标

- **仪表盘化**：把 Skills 页从「表格 + 图」升级成「KPI + 健康 + 排行 + 归因 + 明细」的五层仪表盘。
- **产品口径明确**：KPI 8 格、治理健康 5 项、治理待办 3 组、归因 2 张 Donut，每一项都定义清楚**分子分母 + good/warn/bad 阈值 + 是否带环比**。
- **贯穿式选中态**：柱图 / 排行 Bar / Donut / 明细表 / 抽屉五处共享同一个「选中的 skill」状态。
- **长尾收敛**：排行 Top N 之外合并成「其他 N 个」，避免视觉污染，可展开还原。
- **明细抽屉替代跳页**：点行开右侧抽屉，保留「前往详情页」逃逸口。
- **漏斗下沉**：漏斗仍保留但挪到页面底部（可折叠），不再占黄金位。

## 非目标

- **不动采集链路**：四 runtime 上报、`skill_uses` 表结构不变。
- **不改 skill 详情页 `/skill/:name`**：抽屉复用现有详情页数据，但详情页本身这轮不重画。
- **不做 skill 效果 / 成功率评估**：治理只看使用/覆盖/集中，不看质量。
- **不引入图表库**：沿用当前内联 SVG 手绘 + 现有 `Charts.tsx` 组件。
- **不改 `/api/skills` 已有字段**：新增聚合字段可选返回，前端做兜底。

## 方案概述（详见 design.md）

- 前端拆 `Skills.tsx` 为 5 层组件：`KpiStrip / HealthBar / MainSplit（趋势+排行 · 治理待办）/ AttributionDonuts / DetailTableWithDrawer / FunnelFooter`。
- 后端 `/api/skills` 补齐两块聚合：**periodComparison**（本期 vs 上一同长度窗口） + **governance.buckets**（未收录/装了没用/收录未装机三组待办）。已有字段（`daily / table / operator_table / funnel / governance.untracked_usage`）继续用。
- 选中态用 URL query `selected=<skill_name>` 全局共享，五处组件都从同一个 hook 读。
- 长尾聚合在前端做：排序后前 N 保留、剩余合并成 `__others__` 虚拟行。
- 抽屉复用 `/api/skills/:name` 已有数据集，按当前时间窗切片。

## 影响

- **specs/board**：新增 KPI 环带、治理健康条、治理待办分组、归因 Donut、明细抽屉、长尾聚合、选中态贯穿、漏斗下沉这些规则；修改主视图排布规则；标记原「排行 + 漏斗」并列结构为**已废弃**。
- **前端**：`Skills.tsx` 从 ~430 行拆成多组件；样式在 `styles.css` 追加 `skills-kpi / skills-health / skills-attribution / skills-drawer` 段。
- **后端**：`/api/skills` 补齐聚合字段（可选返回），前端读到就用、读不到就隐藏；无破坏性 schema 变更。
- **wireframes**：本 change 落 `wireframes.md`，归档时按 `openspec/changes/AGENTS.md` 回流到 `docs/wireframes/pages/skills.md`。
- **不影响**：`/skill/:name`、`/operator/:name`、看板侧栏、Agents 视图、Token Usage 页、`skill_uses` 采集。
