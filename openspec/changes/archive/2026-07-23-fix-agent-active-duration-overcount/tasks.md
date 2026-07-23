# 任务：fix-agent-active-duration-overcount

## 方案与事实源

- [x] 核对线上异常、board/ingest 实现、Agents API/详情消费链路和 ADR 约束。
- [x] 定义连续段、断档、迟到终态、身份区间并集和上海日切分口径。
- [x] 写入 board/ingest spec delta、Agents 线框差异并完成方案反思。

## 服务端

- [x] 在 ingest 纯心跳去重中保留超过 180 秒的同状态恢复边界。
- [x] 将 metrics 改为 session 连续段 + 最终身份区间并集 + 上海日切分。
- [x] 保持质量、状态、缓存和 `/api/state`/`/api/agents` 对外契约兼容。

## 前端与文档

- [x] 将 Agents 明细中英文列文案改为“距上次活跃 / Time since last active”。
- [x] 同步 ADR、模块地图、AGENTS 和行为/线框事实源。

## 测试与验证

- [x] 补重叠 session、断档恢复、pending 心跳、迟到终态、跨日/跨窗口、未来窗口和历史异常样本回归测试。
- [x] 运行服务端 py_compile、pytest 与整体覆盖率 >= 95%。
- [x] 运行前端 unit 和 production build，并检查文案响应式展示。
- [x] 对照 proposal/design/spec delta 反思代码符合度并记录验证结果。
