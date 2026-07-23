# ingest spec delta：pending 与 SQLite 原子交接

## 规则增量

- “上一条已确认心跳” MUST 取 SQLite `last_seen`（缺失时回退 `recv`/`ts`）与同事件 pending
  心跳中的最新有效时刻；旧 pending 不得覆盖或回退较新的 SQLite 时间。
- 同状态/同步骤事件因 skill、profile、shim 版本等语义写入而即时推进 SQLite `last_seen` 时，服务端
  MUST 同时淘汰已被该写入覆盖的旧 pending，后续 flush 不得造成 `last_seen` 回退。
- 插入同一 session 的任何新事件行前，服务端 MUST 先将上一事件行尚未落库且较新的 pending
  固化到 SQLite，再移除该 pending；此规则同时适用于状态变化、步骤变化和 `heartbeat_resume`。
- batch flush 与 ingest MUST 原子协调：pending 不得在对应 SQLite 更新提交前对 ingest 暂时不可见；
  SQLite 写入失败时 pending MUST 保留以供重试。
- 同一事件的 `last_seen` MUST 单调不减；pending/DB 交接不得制造虚假断档或丢失已确认的活跃端点。

## 可验证行为增量

- pending 后发生即时 skill 写入，再在 180 秒内收到纯心跳，不新增 `heartbeat_resume`，DB 时间不回退。
- pending 后收到状态或步骤变化，新行插入前旧行 `last_seen` 固化为 pending 时间。
- flush 与 ingest 并发时，ingest 只能观察 flush 前的 pending 或 flush 后的 SQLite 时间，不能观察两者
  都缺失的中间态。
- flush 失败后 pending 仍存在，重试成功后才从 map 清除并更新 SQLite。
