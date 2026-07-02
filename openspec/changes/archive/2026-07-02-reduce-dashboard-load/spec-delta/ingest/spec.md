# spec-delta:ingest

## 配置新增

- `TF_HEARTBEAT_BATCH_SECONDS`:纯心跳 `last_seen` 批量写入间隔,秒,float 或 int。
  默认 `15`;设为 `0` 时禁用 batch,恢复每次纯心跳即时更新 `events.last_seen`。

## 规则新增 / 修改

- 纯心跳 `last_seen` 可以进程内 batch:
  - 当事件命中心跳去重(status/current_step 相对同 identity + session 的上一行不变)且无其它即时写入语义时,
    服务端可以不立即 `UPDATE events.last_seen`,而是将最新 `last_seen` 放入进程内 pending map。
  - 后台 flush 按 `TF_HEARTBEAT_BATCH_SECONDS` 间隔用一个 SQLite 事务批量更新 pending 的 `events.last_seen`。
  - flush 成功后必须通知 board 域 state dirty,以便 SSE / cache 后续展示最新 liveness。
  - 服务进程异常退出时,允许丢失最多一个 batch 窗口内的纯心跳 liveness 刷新;状态变化事件不得丢。
- 以下事件不得进入纯心跳 batch,必须即时落库或即时处理:
  - `status` 或 `current_step` 变化。
  - `done` / `error` / `idle` 等终态或显式状态切换。
  - 携带 `skill` 且产生新的 `skill_uses` 记录。
  - 携带 profile 字段并更新 `profiles`。
  - 携带新的或变化的非空 `shim_version`。
- 纯心跳 batch 不改变现有响应语义:
  - 命中心跳去重仍返回 `{"ok": true, "heartbeat": true, ...}`。
  - 该响应只代表服务端接受了 liveness 刷新,不保证 `events.last_seen` 已同步落盘。
- 插入真实事件行时,同一 session 旧事件行上挂起的 pending heartbeat 可以清理,避免之后用旧行覆盖或产生无意义写入。
- `shim_version` sticky 写入必须避免 no-op:
  - 首次收到某 identity 的非空 `shim_version` 时插入。
  - 收到不同非空 `shim_version` 时更新。
  - 收到与当前值相同的非空 `shim_version` 时不得重复更新 `agent_shim_versions.updated`。
  - 缺失或空白 `shim_version` 仍不得清空 sticky 值。

## 可验证行为

- 连续发送两条相同 `status/current_step` 的纯心跳,且 batch interval > 0:
  第二条返回 `heartbeat:true`;flush 前 DB 中上一事件行 `last_seen` 不变;flush 后 `last_seen` 变为最新接收时间。
- `TF_HEARTBEAT_BATCH_SECONDS=0` 时,纯心跳立即更新 `events.last_seen`,保持旧行为。
- running → done 或 running → error 必须立即插入新事件行,不等待 batch。
- 连续相同心跳中第二条携带新 skill 时,`skill_uses` 立即产生记录,不得被 batch 短路吞掉。
- profile 更新必须即时写入 `profiles`,不得等待 heartbeat batch。
- 连续发送相同非空 `shim_version` 时,`agent_shim_versions.updated` 不应随每次心跳变化;发送不同版本时必须立即更新。
- 缺失或空白 `shim_version` 不清空已有 sticky 版本。
