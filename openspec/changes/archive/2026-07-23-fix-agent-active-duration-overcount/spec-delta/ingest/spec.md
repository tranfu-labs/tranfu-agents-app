# ingest spec delta：长断档恢复必须落新段

## 规则增量

- 纯心跳去重的“状态、步骤相同只更新 `last_seen`”规则仅适用于新事件距上一条已确认心跳 `<= STALE_SECONDS=180` 秒。
- 当同一 `operator + runtime + agent||runtime + session_id` 的状态、步骤相同，但新事件距上一条已确认心跳 `> 180` 秒时，服务端 MUST 插入新事件行，以当前服务端 `recv` 作为新连续段起点；不得覆盖旧行 `last_seen`。
- “上一条已确认心跳” MUST 同时考虑 SQLite 行的 `last_seen` 与尚未 flush 的 heartbeat pending map 最新值。
- 新段插入 MUST 触发现有 state dirty/SSE 更新；正常阈值内纯心跳仍可批量更新，不进入活动流。
- 恢复边界行 MUST 可被最新卡片与活跃时长读取，但不得进入只展示真实状态变化的活动流。

## 可验证行为增量

- 同状态、同步骤在 180 秒内重复上报仍返回 `heartbeat=true` 且不新增事件行。
- 同状态、同步骤在超过 180 秒后恢复会新增事件行，旧行 `last_seen` 保持最后确认心跳。
- pending map 已含较新的心跳时，以 pending 时间计算断档，不得误切连续段。
