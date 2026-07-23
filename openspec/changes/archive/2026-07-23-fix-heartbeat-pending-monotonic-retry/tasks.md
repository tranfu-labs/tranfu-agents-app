# 任务：fix-heartbeat-pending-monotonic-retry

## 方案与事实源

- [x] 对照 QA 复现、ingest 规格、ADR-0003/0013 和现有锁模型定位剩余缺口。
- [x] 定义 pending 单调入队与后台 flush 单轮失败隔离规则。
- [x] 写入 ingest spec delta 并完成方案反思。

## 服务端

- [x] 让同一事件 pending 入队只保留最新有效时间。
- [x] 让后台 flush 循环在单轮异常后继续下一轮重试。

## 测试与验证

- [x] 补乱序 pending 不倒退与后台首次失败后自动成功回归测试。
- [x] 运行 targeted test、py_compile、全量 pytest 与整体覆盖率 >= 95%。
- [x] 运行前端 unit 和 production build。
- [x] 对照 proposal/design/spec delta 反思代码符合度并记录验证结果。
