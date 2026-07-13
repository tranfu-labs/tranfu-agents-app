# 提案：agents-followup-integrity

## 背景

上一轮 Agents 时间窗与布局优化已经完成，但复盘发现仍有五类收尾问题：误删了原有摘要事实、自定义时间窗 URL 不能增量保留、Unix 时间转服务日存在时区风险、Runtime/操作员视角刷新后丢失，以及 custom/窗口聚合与 1440px 验收覆盖不足。

## 提案

- 恢复 Agent 总数、运行中、今日/本周活跃、运行质量、待处理等原有摘要事实，保留新的时间窗变化卡片与紧凑问题线索。
- 让 custom `wstart/wend` 在只填写一端时也保留已填写值，并按 `Asia/Shanghai` 解析服务端统计日。
- 用 `rank=runtime|operator` 写入 URL，刷新和复制链接保持排行榜视角。
- 补充 custom URL round-trip、服务日边界、窗口聚合和 URL 视角单测。
- 重新执行 1440×900、1080/1081 和 375px 浏览器验收；记录未修改模块的既有 lint 基线，不扩大本 change 的修复范围。

## 影响

- 影响 Agents 前端 URL 状态、摘要展示、时间窗纯函数与测试、Agents 线框/事实源。
- 不改变服务端 API、事件协议、数据库字段、轮询源或 Agent 身份合并规则。
