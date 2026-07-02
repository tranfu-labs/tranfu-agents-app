# 提案：skills-first-screen-polish

## 背景
GitHub Issue 要求针对 `/skills` 首屏在 14 寸笔记本截图尺寸下做基础体验优化，目标视口已确认是 `1440x900`，并且平板与手机也要一起回归。

当前实现已经有 SKILLS dashboard 的主结构，但首屏仍有几类体验问题：
- 时间窗口选项直接显示 `today`、`this_week`、`7d` 等 key，语言切换后仍不符合当前语言。
- `/skills` 首屏核心文案存在中文硬编码，英文态会混入中文，尤其是 KPI、问题线索、待处理线索和移动筛选摘要。
- 搜索 Skill 名的控件在桌面/平板可用宽度紧张时容易被 label 与 input 的 flex 行为挤到换行。
- KPI 卡片中“总触发次数”等指标的数值、证据入口、标题被拆成多行，首屏信息密度不够，按钮图标没有和核心数字建立一眼可扫的关系。
- 手机首屏需要继续保持“控制摘要 → 问题线索 → 待处理线索 → 排行/趋势 → 过去 W 变化”的判断流，不能让完整筛选表单或 KPI 网格抢占首屏。

## 提案
本变更只打磨 `/skills` 首屏前端体验，不改服务端 API 与统计口径：

1. 补齐 SKILLS 首屏所需 i18n key，让时间窗口、筛选摘要、KPI、问题线索、待处理线索、动作 tooltip 在中英文切换时一致变化。
2. 将窗口展示从原始 query key 改为 display label：中文显示“今天/本周/上周/7 天/14 天/30 天/90 天/自定义”，英文显示“Today/This week/Last week/7d/14d/30d/90d/Custom”。
3. 调整 `SkillsToolbar` 搜索字段结构与 CSS，桌面和平板保持 label + input 单行，移动端仍铺满宽度。
4. 调整 `KpiStrip` 卡片结构：顶部一行放核心数值与证据 icon，下面放标题、短结论和环比/快照；保持证据入口为 icon button 且有可访问名称。
5. 收紧响应式布局：桌面 8 格一行、平板 4×2、手机 2×4；手机继续按 spec 的首屏判断流排序。
6. 更新 `docs/wireframes/pages/skills.md` 对应的 change 线框增量，后续归档时回流。

## 非目标
- 不修改 `/api/skills`、`/api/skills/evidence`、`/api/skill/{name}` 或 `/api/operator/{name}` 的字段、聚合口径、缓存策略。
- 不重做 SKILLS 页面信息架构，不改 Donut、明细抽屉、证据页的数据行为。
- 不新增当前实现里尚未存在的导出 CSV 入口；基线 wireframe 中的导出能力不纳入本轮。
- 不引入图表库或新的持久化状态。
- 不把筛选条件写入 `localStorage` 或 `sessionStorage`。

## 影响
- 受影响模块：`frontend/` 的 `/skills` 页面与 SKILLS 首屏组件、`openspec/specs/board` 的前端可验证行为、`docs/wireframes/pages/skills.md` 的版式事实源。
- 对外行为：用户在中英文切换后，`/skills` 首屏时间窗口和核心文案随语言变化；1440×900 首屏 KPI 更紧凑，搜索框不因 label 换行破坏控制条；平板/手机无页面根横向滚动。
- 风险：i18n key 增多，若遗漏会显示 key 名；通过单元测试和三视口截图验证兜底。
