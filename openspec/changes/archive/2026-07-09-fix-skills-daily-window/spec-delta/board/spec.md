# board spec delta:fix-skills-daily-window

## 修改
- `/skills` 主分析区的每日使用趋势图必须以 `/api/skills` 返回的 `window.start..window.end` 作为日期轴事实源逐日铺满;仅当响应缺失有效窗口边界时,前端才允许回退到以窗口右端和 `days` 推导日期轴。
- `/skills` 主分析区趋势卡标题必须随当前时间窗口 i18n label 派生,例如「近 7 天使用」/ `Used in Last 7 days`;按人视角标题必须继续表达 operator 口径,例如「近 7 天使用 · 按人」/ `Used in Last 7 days · by operator`。
