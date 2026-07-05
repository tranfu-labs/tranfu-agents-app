# 设计：fix-skills-rank-layout

## 方案
- 在短窗口桌面布局中让 `.skills-analysis--short` 的网格项使用 stretch，并让排行卡片与趋势卡片自身填满同一行高度，从而以同一 grid row 对齐外框底边。
- 将排行首列从单行省略改为可换行的布局：名称容器允许 `white-space: normal`、`overflow-wrap: anywhere`，色块保持固定尺寸；桌面保留条形轨道、数值和记录动作列。
- 在手机断点下把排行行降级为两列摘要：名称占主列且允许换行，数值与记录动作在右侧，条形轨道独占下一行；所有列使用 `min-width:0` 和 `max-width:100%` 防止根级横滚。
- 对长尾展开行同步应用可换行/可断行规则，避免它成为窄屏溢出来源。
- 用 Playwright route stub 固定 `/api/skills` payload，让 `openspec-driven-development` 和更长无空格名称成为榜首，机械验证默认可见文本、卡片 bottom 差值、根滚动宽度和关键元素 bounding box。

## 权衡
- 不引入 JS 动态测量或窗口 resize 计算，避免把纯布局问题变成运行时状态问题。
- 不改变排行数据结构或排序逻辑，确保修复限定在展示层。
- 桌面允许长名占用两行，换取默认可读性；极端窄屏可以截断，但必须保留完整可读路径。

## 风险
- 排行行变高会增加排行卡片高度，因此需要用同一 grid row stretch 验证与趋势卡片底边对齐。
- 共享样式会影响 operator 视角主分析区，因此需回归 `/skills?view=operator&w=7d`。
- 断点边界在 `1081px` 与 `1080px` 处最容易暴露等高样式残留，需要专门验证。
