# 提案：fix-heartbeat-pending-consistency

## 背景

`fix-agent-active-duration-overcount` 已定义并实现心跳断档拆段，但 QA 发现 pending batch 与 SQLite
`last_seen` 的交接仍不一致：

- 即时语义写入把 SQLite `last_seen` 推进后，旧 pending 仍可能覆盖较新的 DB 时间，造成时间回退和虚假
  `heartbeat_resume`。
- 状态或步骤变化插入新行前会直接丢弃旧行 pending，使最后确认心跳永久丢失。
- 后台 flush 在取得全局写锁前清空 pending，ingest 可能在 DB 尚未更新的短暂窗口误判断档。

这些缺陷会少计或错误切分连续段，违反 ingest 事实源中“DB 与 pending 共同确定最后确认心跳”和“切段前
固化 pending 末点”的规则。

## 提案

- 最后确认心跳取 SQLite `last_seen`、`recv`/`ts` 回退值与 pending 时间中的最新有效时刻，不允许旧
  pending 压过较新的 DB 时间。
- 同状态即时语义写入用当前 `recv` 更新 SQLite 时，同时原子移除已被覆盖的 pending。
- 任何新事件行插入前，先把旧行尚未落库且较新的 pending 固化，再移除 pending；状态/步骤变化与
  `heartbeat_resume` 使用同一路径。
- batch flush 按 `app._lock → _heartbeat_pending_lock` 的统一锁顺序，在全局写锁内完成
  pending 快照、SQLite 更新、commit 和 pending 清除，使 ingest 不会观察到“map 已空、DB 未更新”的中间态。
- 不改 schema、API、时长口径或历史数据。

## 影响

- 服务端 ingest 域的心跳 pending 协调与 batch flush。
- ingest 规格、ADR-0003、模块边界说明和回归测试。
- board 聚合、前端、shim、协议字段和数据库 schema 不变。
