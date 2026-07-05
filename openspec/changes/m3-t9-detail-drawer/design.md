# 设计：m3-t9-detail-drawer

## 方案
1. `frontend/src/lib/skillsChartLayout.ts`
   - 新增 `resolveDetailTrendLayout(dayCount, viewportWidth)`，14d 内适配容器，30/90d 使用内部横滚并 `scrollToEnd=true`。
   - 新增 `resolveDetailTrendEndDay(today, daily, fallback)`，严格按 `detail.today -> daily[] 最大合法 day -> fallback`。

2. `frontend/src/components/Charts.tsx`
   - `DetailTrend` 读取 `.detail-trend-box` 内容宽度。
   - 长窗口在 `axisEnd`、天数、track 宽度、容器宽度变化后设置 `scrollLeft = scrollWidth - clientWidth`。
   - 右端日期 label 总是渲染，避免验收只能依赖不可见滚动位置。

3. `frontend/src/views/Skills.tsx`
   - URL `sel` 可作为深链恢复抽屉。
   - 明细表打开抽屉时写入 `sel`；关闭抽屉清空 `sel`。
   - 排行 Bar 仍只作为筛选/联动选择，不自动打开抽屉。

4. `frontend/src/styles.css`
   - 增加不透明承载区 token：`--solid-elev`、`--solid-elev2`。
   - `.skills-drawer`、KPI、section、`.detail-trend-box`、loading/error 使用实底。
   - 抽屉外层 `overflow-x:hidden`，长图只允许 `.detail-trend-box` 横滚。

## 验收验证计划
- QA-1：浅色/深色主题 computed background alpha 均为 1，截图不透底层图表。
- QA-2：`/api/skill/<skill>` 延迟 2 秒，loading 实底；数据返回后 500ms 内滚到右端。
- QA-3：`detail.today` 缺失且 `daily[]` 乱序，最大 day 为 `2026-07-04` 时不得定位到 `2026-07-05`。
- QA-4：1440x900、768x1024、375x812 三档 viewport root/drawer 不横溢，只有 chart box 横滚。
- QA-5：500 和永久挂起状态下 loading/error 实底、root 无横溢、关闭清 `sel`。

## 风险
- `sel` 同时服务图表联动和抽屉深链；实现用 `suppressedDrawerSkill` 避免排行 Bar 点击自动打开抽屉，同时保留外部深链恢复能力。
- `--elev` / `--elev2` 是半透明 token，抽屉承载区不得直接使用它们作为背景。
