# ingest spec delta：turn heartbeat 生命周期有界与 terminal fence

## Requirement：owner 存活不得无限延长 synthetic heartbeat

- Claude Code / Codex 的 `turn heartbeat` daemon MUST 同时受软 owner lease 和独立可信活动硬截止约束。
- 只有 `UserPromptSubmit` / `PreToolUse` 等真实 hook start 请求 MAY 延长可信活动截止；daemon 周期循环、
  owner PID 存活和成功上报 MUST NOT 延长该截止。
- 默认 `TF_HEARTBEAT_MAX_SILENCE_SECONDS=14400`。达到截止后 daemon MUST 最多发送一次质量无副作用的
  `idle`，随后在有界 control poll/report timeout 内退出并停止推进 `last_seen`。
- 已知存在更长单工具静默任务的环境 MAY 显式调大配置；新真实 hook 活动 MUST 能启动或延期正常 heartbeat。

## Requirement：异步 terminal 必须压过更早的迟到 start

- hook 派生 start/stop helper 前 MUST 记录可比较的本机请求顺序时间。
- terminal stop MUST 留下 tombstone；请求时间不晚于该 terminal 的 start helper MUST 被忽略，不得清除 stop、
  创建 generation 或续租。请求时间更晚的新 prompt/tool MAY 覆盖 tombstone并启动新 generation。
- state 更新继续使用 per-session lock 和原子替换；任一异常必须静默，不得阻塞宿主 agent。

## Requirement：服务端 terminal 后拒绝迟到 synthetic heartbeat

- 对同一最终身份/session，最新事件为 `done/error/idle` 时收到
  `status=running && current_step='turn heartbeat'`，服务端 MUST 返回成功但不得 INSERT 新事件、不得推进
  terminal `last_seen`、不得让该 heartbeat 重开活跃段。
- terminal 后先收到新的非 synthetic active 事件时，后续 heartbeat MUST 恢复正常处理。
- heartbeat 与 terminal 并发时，写锁序列无论为何，terminal 后的下一条 synthetic heartbeat 均不得重开 session。
- 本规则不改变普通心跳去重、pending batch、180 秒在线判定、900 秒读侧连续段补偿或 ADR-0025 跨 session 累加。

## Requirement：服务端独立限制 synthetic heartbeat 活动窗口

- 服务端 MUST 识别当前已分发旧 shim 使用的精确 synthetic step `turn heartbeat`；该内部名称未来变化时，
  MUST 在旧版本支持窗口内同时识别旧名与新名。
- 对同一最终身份/session，synthetic heartbeat 只可在最近非 synthetic 真实 active 事件的服务端 `recv` 后
  `TF_HEARTBEAT_MAX_SILENCE_SECONDS` 内推进 `last_seen`。超过上界时 MUST 返回成功但不得 INSERT、UPDATE、
  入 pending 或标记 state dirty。
- synthetic 即时写入与 pending flush MUST 使用相同上界；截止前入队的 pending 不得在截止后把
  `last_seen` 推过 `trusted_recv + max_silence`。
- 新的非 synthetic active 事件 MUST 刷新可信活动锚点。该规则不依赖客户端版本、owner 状态或 terminal 是否到达。

## 可验证行为

- owner 持续存活、Stop 永久缺失、无新真实 hook → heartbeat 到 hard deadline 后只发一次 idle并退出。
- 1 小时 45 分静默 turn 在默认配置内保持；4 小时边界退出；新 PreToolUse 把边界延至该可信活动之后。
- start(100) → stop(200) → 迟到 start helper(100) 不重开；start(300) 作为新 turn 正常启动。
- done → 多条 turn heartbeat：events 行数和 terminal `last_seen` 均不变；done → prompt → heartbeat 正常增长。
- 无 terminal 的旧 daemon 持续上报 → 最近真实活动 + 4h 后，events/pending/last_seen 不再变化；新真实活动后恢复。
