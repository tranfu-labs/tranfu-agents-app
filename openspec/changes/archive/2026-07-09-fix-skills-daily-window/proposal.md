# 提案:fix-skills-daily-window

## 背景
`/skills` 总览切换时间窗口时,主分析区的每日使用趋势卡没有可靠地随当前窗口重绘。当前图表标题固定为「每日使用」/ `Daily usage`,无法表达当前统计窗口;图表轴也主要通过 `days` 与右端日期反推,没有把 `/api/skills` payload 中的 `window.start..window.end` 当作事实源。

这会让用户切换 `7d`、`14d`、`30d`、`90d`、`last_week` 或 `custom` 后,看到的趋势卡像是仍停留在旧口径,尤其是标题始终不变。

## 提案
- 让 `/skills` 主趋势卡标题从当前时间窗 i18n label 派生,例如「近 7 天使用」/ `Used in Last 7 days`;按人视角保留 `· 按人` / `· by operator` 后缀。
- 让主趋势图优先使用 `/api/skills.window.start..end` 生成完整 date-only 轴,只在 payload 缺失窗口边界时回退旧的 `end + days` 推导。
- 增加前端单元测试覆盖窗口标题与窗口轴生成,防止再次回归。

## 影响
- 影响模块:M2 看板前端(`/skills` 主分析区趋势卡)。
- 不改变后端聚合口径、API schema、SQLite schema 或 shim 上报协议。
- 不改变页面布局,只改变趋势卡标题文案与图表日期轴绑定。
