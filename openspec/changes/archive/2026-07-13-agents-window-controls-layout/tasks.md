# 任务：agents-window-controls-layout

## 方案与事实源

- [x] 访谈确认时间窗、默认值、对比指标与版式方向。
- [x] 输出 Agents 桌面/平板/手机字符线框。
- [x] 写入 board spec delta，明确 URL、窗口口径、紧凑线索条与主分析区布局。

## 实现

- [x] 扩展 Agents URL 查询解析与时间窗选项，默认 today。
- [x] 新增窗口序列切片、窗口统计与 delta 格式化纯函数。
- [x] 调整 Agents 控制条、窗口对比栏、问题线索、排行榜/趋势图顺序与响应式样式。
- [x] 补充/更新 Agents Dashboard 单测，覆盖时间窗边界、前期为零 delta、窗口聚合和 URL round-trip。

## 验证

- [x] `npm --prefix frontend run test:unit`。
- [x] `npm --prefix frontend run build`。
- [x] 按方案检查桌面 `1440px`、平板 `1080px`、手机 `375px` 的布局与根级横向滚动。
- [x] 对照本 change 逐条复核实现，无偏差后进入归档。
