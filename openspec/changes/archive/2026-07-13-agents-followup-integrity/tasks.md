# 任务：agents-followup-integrity

## 方案与事实源

- [x] 对照上一 change 复盘并确认五项收尾问题。
- [x] 输出摘要恢复、custom 时间窗、视角 URL 与验证范围方案。

## 实现

- [x] 恢复原有 Agent 摘要事实并保持时间窗卡片、问题线索和主分析区顺序。
- [x] 修复 custom `wstart/wend` 增量 URL 与 `Asia/Shanghai` 服务日转换。
- [x] 将 Runtime/操作员排行榜视角改为 `rank` URL 状态。
- [x] 补充 custom、rank、服务日和窗口聚合单测。

## 验证与收尾

- [x] `npm --prefix frontend run test:unit`。
- [x] `npm --prefix frontend run build`。
- [x] 精确验收 1440×900、1080/1081、375px 布局与根级横向滚动。
- [x] 运行 lint，确认本 change 文件无新增 lint 错误，并记录既有错误。
- [x] 更新基线 wireframe/spec/AGENTS.md，归档本 change 并更新现有 PR。
