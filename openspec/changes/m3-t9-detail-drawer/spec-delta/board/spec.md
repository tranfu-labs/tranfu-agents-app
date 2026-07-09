# spec delta: board

> 合入后并入 `openspec/specs/board/spec.md`。本变更只修改 SKILLS 总览详情抽屉展示规则，不改服务端接口和聚合口径。

## 修改规则(MODIFIED)
- SKILLS 总览明细行打开同页右侧抽屉时，抽屉外层 backdrop 可保持半透明遮罩；右侧抽屉面板、KPI、趋势图、runtime / operator / 最近记录、loading/error 等内容承载区域必须使用不透明实底。
- 抽屉内 `DetailTrend` 的横轴右端必须来自单 skill 详情 payload：优先 `detail.today`，缺失时使用 `detail.daily[].day` 最大合法日期，仍缺失时才使用既有 fallback。不得硬编码具体日期。
- 抽屉内 `DetailTrend` 必须提供右端统计日可见标识；若轴标签抽样会隐藏最后一天，必须强制显示最后一天标签或等效标识。
- 抽屉内 30d / 90d 等长趋势图如果需要横向滚动，初始渲染、`?sel=` 深链恢复、趋势天数切换、桌面 / 窄屏 viewport 变化后，都必须重新定位到右端统计日可见的位置。
- SKILLS 统计域页面根不得因抽屉趋势图出现横向滚动；长趋势只允许在抽屉内部图表容器横向滚动。抽屉自身不得被 SVG `min-width` 撑出 viewport。
- 关闭抽屉必须清空 URL 中的 `sel`；排行 Bar 的 `sel` 联动不得强制打开抽屉。

## 可验证行为(新增)
- 浅色与深色主题下，抽屉面板、KPI、趋势图 section、列表 section 的 computed background alpha 均为 1。
- 验收数据右端为 `2026-07-04` 时，抽屉趋势图初始可视范围包含 `07-04`。
- `/api/skill/<skill>` 延迟、永久挂起或返回 500 时，抽屉 loading/error 状态仍实底，页面根不得横向溢出。
- 1440x900、768x1024、375x812 三档 viewport 下，root 和 drawer 不横溢，只有 chart box 可横滚。
