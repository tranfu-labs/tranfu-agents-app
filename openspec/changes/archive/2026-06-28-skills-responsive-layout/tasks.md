# 任务:skills-responsive-layout

- [x] 1. `/skills` 总览页响应式结构。
      调整视角卡、筛选条、趋势图、排行表、治理 Lens 和公司库漏斗在平板/手机下的布局;确保排行在漏斗上方,趋势图仅组件内横滚。
- [x] 2. `/skills` 总览排行表手机摘要行。
      Skill 主榜、未收录占比榜、按人主榜在 ≤600px 下展示名称、来源/占比、7d/30d/总计/用户/最近等摘要字段;保持整行可点和键盘可达。
- [x] 3. `/skill/:name` 子页面响应式。
      指标卡平板/手机列数、趋势图内部滚动、分布区单列、最近记录手机摘要行。
- [x] 4. `/operator/:name` 子页面响应式。
      指标卡平板/手机列数、趋势图内部滚动、runtime + 使用 Skill 排行单列、Skill 排行和最近记录手机摘要行。
- [x] 5. CSS 溢出治理。
      限定 SKILLS 统计域局部规则,修正长名称、图表、表格、Lens 按钮在 375px/768px 下的横向溢出。
- [x] 6. 趋势图响应式验证。
      `/skills?win=7` 在手机下完整铺满图表容器;30/90 天和详情 30 天只在 `.chart-box` 内横滚,浮窗不溢出视口。
- [x] 7. 自检与视口验证。
      运行 `npm --prefix frontend run build`;在 375x812、768x1024、1440x900 检查 `/skills` 三种 query、`/skill/:name`、`/operator/:name`,暗/亮主题各看一遍。
      保存关键截图,并检查 `document.documentElement.scrollWidth <= window.innerWidth + 1`。
