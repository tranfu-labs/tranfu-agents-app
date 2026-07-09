# 任务：m3-t9-detail-drawer

- [x] 1. 前置确认：改动只触碰 M2 前端与 OpenSpec，不触碰服务端/SQLite/shim。
- [x] 2. `skillsChartLayout.ts`：新增详情趋势布局 helper 与右端日期 helper。
- [x] 3. `skillsDashboard.test.ts`：补充 14d fit、30/90d scroll、非法 dayCount、乱序 daily fallback 单测。
- [x] 4. `Charts.tsx`：`DetailTrend` 接入容器宽度、右滚、右端 label。
- [x] 5. `Skills.tsx`：支持 `?sel=` 深链恢复，关闭清 `sel`，排行 Bar 不自动开抽屉。
- [x] 6. `styles.css`：抽屉/KPI/section/chart/loading/error 改为不透明实底，限制横溢。
- [x] 7. 验证：`test:unit`、`build`、`lint`、浏览器矩阵和 `git diff --check`。
