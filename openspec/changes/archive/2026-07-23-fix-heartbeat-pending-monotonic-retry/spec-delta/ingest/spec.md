# ingest spec delta：pending 单调入队与 flush 自动恢复

## 规则增量

- 同一事件 id 的 pending `last_seen` MUST 单调不减。并发请求即使以不同顺序生成 `recv` 与取得写锁，
  后入队的较旧时间也不得覆盖已入队的较新有效时间。
- 后台 heartbeat flush 循环 MUST 隔离单轮普通运行时异常；一次 SQLite 写入或 commit 失败不得终止
  后台线程，且同一 pending MUST 保留到后续间隔自动重试成功后才清除。
- `flush_heartbeat_batch()` 被显式调用时仍可向调用方报告异常；自动恢复责任只属于长期运行的后台循环。

## 可验证行为增量

- 同一事件 pending 先入队 `00:02`、后入队 `00:01`，最终值仍为 `00:02`；`00:04:01` 的同状态心跳
  相对最后确认时间仅 121 秒，不得生成 `heartbeat_resume`。
- 后台循环第一次 flush 发生瞬时 SQLite 异常、第二次恢复时，线程继续运行，原 pending 自动写入
  SQLite 并在 commit 成功后清除。
