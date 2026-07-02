# 任务:skills-daily-layout-responsive

- [x] 修改 `/skills` 主分析区结构:排行、每日使用、待处理线索拆为独立模块。
- [x] 按窗口长度切换桌面布局:`<=14d` 排行/每日使用左右并列,`>=30d` 上下堆叠。
- [x] 将待处理线索改为独立治理行,每个分类独立区块并响应式换行。
- [x] 调整 `StackedSkillChart` 布局 helper:短窗口 fit 可视宽度,长窗口保持内部横滚。
- [x] 补充前端单元测试覆盖短/长窗口布局决策和 bar 宽度上限。
- [x] 更新 `/skills` 线框事实源,回流本变更 `wireframes.md` 到 `docs/wireframes/pages/skills.md`。
- [x] 运行 `npm --prefix frontend run test:unit`。
- [x] 运行 `npm --prefix frontend run build`。
- [x] 用浏览器验证 1440x900、1280x800、768x1024、375x812 下 `7d/14d/30d/90d` 的布局与页面根横向滚动。
