# 提案：m3-t9-detail-drawer

## 背景
T9 修复 SKILLS 总览详情抽屉的全局缺陷 15-16：抽屉承载区半透明导致底层图表双重曝光，抽屉内趋势图在长窗口下初始停在最旧日期，并可能把横向滚动泄漏到页面根或抽屉外层。

产品与 QA 已锁定正式 8 条验收：抽屉实底、右端日期定位、`?sel=` 深链恢复、浅深主题 computed background、慢返回、`detail.today` 缺失 fallback、三档 viewport overflow、loading/error 失败态与关闭清 `sel`。

## 提案
- 只改 M2 前端，不改后端 API、SQLite、shim 或持久化状态。
- `DetailTrend` 增加可测布局 helper，长窗口只在图表容器内横滚，并在 mount、数据右端、天数和容器尺寸变化后滚到右端。
- 详情趋势右端日期按 `detail.today -> max(detail.daily[].day) -> fallback` 解析，且强制渲染右端日期 label。
- `/skills?w=...&sel=...` 可恢复抽屉；关闭抽屉清空 URL `sel`。
- 抽屉、KPI、section、chart、loading/error 使用不透明实底；backdrop 保持半透明。

## 影响
- 前端：`Charts.tsx`、`Skills.tsx`、`styles.css`、`skillsChartLayout.ts`、`skillsDashboard.test.ts`。
- OpenSpec：补充 board 前端规则 delta 与 `/skills` 抽屉线框。
