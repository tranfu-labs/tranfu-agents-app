# 提案：fix-heartbeat-pending-monotonic-retry

## 背景

`fix-heartbeat-pending-consistency` 已修复 SQLite 与 pending 的时间选择、写前固化和 flush 原子交接，
但 QA 继续发现两个会破坏心跳证据连续性的边界：

- 并发请求在取得全局写锁前生成服务端 `recv`。较早请求若较晚入队，当前 pending 直接赋值会把同一事件
  已有的较新时间覆盖为旧时间，进而制造虚假 `heartbeat_resume`。
- 后台 flush 循环未隔离单次 SQLite 异常。一次瞬时失败就会终止唯一 daemon 线程，而
  `_heartbeat_thread_started` 仍保持真值，后续纯心跳永久失去自动落库能力。

## 提案

- 同一事件 id 的 pending 入队必须比较已有值与新值，只保留最新有效 UTC instant；乱序请求不得让
  pending 时间倒退。
- 后台 flush 循环必须捕获单轮 flush 的普通运行时异常，保留 pending，并在下一配置间隔继续重试；
  一次瞬时数据库失败不得终止线程。
- 补回归测试锁定“较旧 recv 后入队仍不误切段”和“首次 flush 失败、下一轮自动成功并清 pending”。
- 不改 schema、API、时长聚合、前端或历史数据。

## 影响

- 服务端 ingest 域的 pending 入队与后台 flush 生命周期。
- ingest 规格、ADR-0003、模块边界说明和服务端回归测试。
- board、前端、shim、协议字段与数据库 schema 不变。
