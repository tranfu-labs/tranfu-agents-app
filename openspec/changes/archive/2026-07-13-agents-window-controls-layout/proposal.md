# 提案：agents-window-controls-layout

## 背景

Agents 列表当前把时间口径固定为今天/本周，Runtime 与操作员筛选虽然存在但和 Skills 总览的控制条语义不一致。主分析区还把趋势图放在左侧、排行榜放在右侧，问题线索使用较大的四张按钮卡，首屏信息密度和 Skills 统计页不统一。

## 提案

- 给 `/agents` 顶部控制条增加与 Skills 一致的时间窗：今天、本周、上周、近 7/14/30/90 天、自定义，默认今天；Runtime、操作员继续在同一控制条。
- 基于已有 90 天活跃序列展示当前窗口与上一同长度窗口的活跃 Agent 数、活跃时长变化，并保留当前在线数与运行质量快照。
- 将问题线索压缩为 Skills 风格的紧凑事实条，保留点击后写入筛选的行为。
- 将桌面主分析区调整为左排行榜、右时间趋势图；使用与 Skills 页面一致的紧凑条形排行和图表面板语言，平板/手机继续单列。
- 把窗口解析与窗口聚合抽成纯函数并补充前端单测，更新 Agents 线框与 board 事实源。

## 影响

- 影响 `frontend/src/views/Agents.tsx`、`frontend/src/lib/agentsDashboard.ts`、Agents 组件及 `frontend/src/styles.css`。
- Agents URL 新增 `w/wstart/wend` 查询参数；原有筛选参数继续保留，变化使用 replace，不引入浏览器持久化。
- 不改变服务端 API、事件协议、数据库字段和 Agent 卡片按身份合并规则。
