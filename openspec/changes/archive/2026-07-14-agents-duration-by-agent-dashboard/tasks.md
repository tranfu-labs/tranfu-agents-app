# 任务：agents-duration-by-agent-dashboard

## 方案与事实源

- [x] 采访确认全部 Agent、固定运行时长、移除操作员/运行终端字段并保留单日扇形图。
- [x] 输出桌面、平板、手机字符线框和前端实现方案。
- [x] 写入 board spec delta，并反思数据口径、旧 URL 与同名 Agent 风险。

## 实现

- [x] 收口 Agents URL/filter 模型，移除 `rank/rt/op` 并默认按窗口运行时长排序。
- [x] 新增按身份 Agent 的窗口排行和逐日时长分段，补齐纯函数单元测试。
- [x] 将排行改为 Agent 时长排行并下钻 Agent 详情。
- [x] 将趋势固定为 Agent 运行时长，保留单日环形扇形图和多日堆叠柱。
- [x] 调整八卡、控制条、明细表、中英文文案和响应式样式。

## 验证

- [x] 运行 `npm --prefix frontend run test:unit`。
- [x] 运行 `npm --prefix frontend run build`。
- [x] 在 1440、768、375 三档验证 today/7d/30d、主题、键盘和无根横滚。
- [x] 对照 proposal、design、spec delta 和 wireframe 逐条反思代码符合度。
