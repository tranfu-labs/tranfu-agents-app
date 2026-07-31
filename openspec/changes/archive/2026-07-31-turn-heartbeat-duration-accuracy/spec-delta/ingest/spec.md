# ingest 规格增量：turn 心跳复用既有纯心跳路径

## 规则增量

- shim turn 心跳 MUST 使用既有 `POST /v1/events`、当前身份和当前 `session_id`，发送 `status=running`；不得新增协议字段、prompt、代码、输出、token 或费用数据。
- shim turn 心跳 MUST 使用 no-spool 发送策略：网络失败时丢弃当前纯心跳，不得写入或 flush 共享 `spool.ndjson`；普通状态变化、done/error 和 skill 事件继续使用既有可靠 spool。
- turn 心跳是纯心跳语义，MUST 复用现有 `STALE_SECONDS=180` 去重/恢复和 `TF_HEARTBEAT_BATCH_SECONDS=15` pending 批量落库；服务端不因该客户端功能改变 ingest 恢复边界。
- `Stop` 或 `SessionEnd` 后，shim MUST 停止该 session 的 turn 心跳器；缺少 `session_id` 时不得停止其它 session。
- 宿主 PID 消失或 heartbeat TTL 到期时，shim SHOULD 发送一次 `status=idle` 关段事件；该事件可走既有可靠 spool，不得增加 error/runs 质量统计，且不能因失败阻塞宿主 agent。

## 可验证行为增量

- 连续 turn 心跳在 status/step 不变时返回 `heartbeat=true`，服务端按既有 pending + batch 路径推进 `last_seen`。
- 断网持续 17 小时以上时，heartbeat 失败不得把共享 spool 推到 1000 行上限，也不得挤掉此前的 done/error/skill 记录。
- 心跳器启动失败、上报失败、状态文件失败、宿主进程探测失败或 TTL 到期都 MUST 静默，不得让宿主 agent hook 抛错或阻塞；daemon 在可靠宿主检查通过时自行续租，检查不可用时 TTL 才作为绝对兜底。
- 正常 Stop 只需写入 drain 请求并立即返回，不能等待网络 ack 或阻塞宿主；daemon 看到请求后不得再开新 heartbeat。in-flight running 晚到只允许造成最多 180 秒卡片显示瑕疵，不得造成时长虚增。
- 同一 session 并发触发多个 `UserPromptSubmit`/`PreToolUse` 只存在一个有效心跳器；两个不同 session 可以同时发送 running 心跳。
