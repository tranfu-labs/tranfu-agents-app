# 任务：agents-today-pie-chart

## 方案与事实源

- [x] 采访确认单日使用扇形图，并尽可能复用现有柱状图风格。
- [x] 完成显示信息、显示框架、风格候选与选定版文档。
- [x] 输出 Agents 单日趋势字符线框与 board spec delta。

## 实现

- [x] 新增单日扇区纯函数并补充单元测试。
- [x] 在 `AgentActivityChart` 中渲染单日环形扇形图，保留多日柱状图。
- [x] 泛化图表锚点并补齐扇区、中心值、响应式与主题样式。

## 验证

- [x] 运行 `npm --prefix frontend run test:unit`。
- [x] 运行 `npm --prefix frontend run build`。
- [x] 浏览器检查今天的两个视角、两个指标、三种主题与手机布局。
- [x] 浏览器回归 7 天与 30 天多日柱状图及图表盒内部滚动。
- [x] 对照方案逐条复核实现，完成事实源归档。
