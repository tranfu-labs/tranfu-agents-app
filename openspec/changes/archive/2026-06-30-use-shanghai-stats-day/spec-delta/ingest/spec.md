# specs/ingest delta：写入日桶默认 Asia/Shanghai

## 修改

- 服务端写入 `events.day` 时,取服务端接收时间在 `Asia/Shanghai` 下的日期,不再取 UTC 日期。
- 服务端写入 `skill_uses.day` 与 `skills_seen.first_day` 时,取同一套 `Asia/Shanghai` 统计日期。
- 事件具体接收时间 `recv`、心跳刷新 `last_seen`、skill 首见时刻 `first_seen` 仍保存 UTC ISO instant。

## 不变

- 写侧权威时间仍以服务端接收时间为准,客户端 `ts` 只供展示。
- skill 使用仍按 `(session_id, skill, mode)` 幂等;心跳去重前处理 skill 的规则不变。
- 旧数据不迁移,历史 `day` 保持原值。

## 可验证行为

- 服务端当前 UTC 时间为 `2026-06-12T16:05:00+00:00` 时,新事件落库 `events.day=2026-06-13`。
- 同一事件带 `skill=alpha` 时,新 `skill_uses.day=2026-06-13`,对应 `skills_seen.first_day=2026-06-13`。
