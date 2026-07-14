# 提案：agents-operator-default-rank-alignment

## 背景

Agents 控制条当前用英文 `Runtime` 暴露运行环境概念，默认也选中 Runtime 视角。团队实际查看时更常先按操作员理解分布，且“运行终端”比 Runtime 更符合中文界面语义。排行榜每一行独立计算弹性列，右侧内容宽度变化会反向挤压名称和进度条列，导致进度条起点不齐。

## 提案

- Agents 中文界面将面向用户的 Runtime 视角与筛选名称统一显示为“运行终端”，内部字段、查询参数与 runtime 值保持不变。
- 视角切换器顺序改为“操作员｜运行终端”；无 `rank` 参数时默认操作员，显式 `rank=runtime` 继续可复制分享。
- 排行榜使用稳定列轨道，名称、进度条、数量与窗口元信息列在所有行对齐，保证进度条从同一水平位置开始。
- 更新 URL 纯函数单测，并在桌面、平板、手机验证文案、默认选中态、显式切换和排行对齐。

## 影响

- 影响 `frontend/src/lib/agentsDashboard.ts`、Agents 控制条、排行榜样式、中英文文案与相关单测。
- 影响 `/agents` 的默认视角和 URL 序列化语义；不改变 `/api/state`、数据库、runtime 枚举或事件协议。
- 更新 board 事实源、Agents 线框、模块地图与根 `AGENTS.md`。
