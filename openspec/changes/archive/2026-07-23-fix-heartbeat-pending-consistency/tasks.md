# 任务：fix-heartbeat-pending-consistency

## 方案与事实源

- [x] 对照 QA 复现、ingest 规格、ADR-0003/0013 和现有锁模型定位一致性缺口。
- [x] 定义 DB/pending 最新时间、写前固化、即时写覆盖与 flush 原子交接规则。
- [x] 写入 ingest spec delta 并完成方案反思。

## 服务端

- [x] 实现最后确认心跳取最新有效时间与 pending 固化 helper。
- [x] 让即时语义写入淘汰旧 pending，所有新行插入前固化旧行端点。
- [x] 统一 flush/ingest 锁顺序，DB 成功后再条件清除 batch。

## 测试与验证

- [x] 补旧 pending 不得覆盖新 DB、状态变化固化 pending、flush/ingest 竞争和 flush 失败重试测试。
- [x] 运行 targeted test、py_compile、全量 pytest 与整体覆盖率 >= 95%。
- [x] 运行前端 unit 和 production build。
- [x] 对照 proposal/design/spec delta 反思代码符合度并记录验证结果。
