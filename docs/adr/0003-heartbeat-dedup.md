# ADR-0003 心跳去重:仅状态/步骤变化才落新行

- 状态:Accepted
## 背景
agent 会高频发心跳;若每条都落库,活动流与存储都会噪声爆炸。
## 决策
`POST /v1/events`:仅当 `status` 或 `current_step` 相对该身份上一行**发生变化**时才 INSERT 新行;
纯心跳只 UPDATE `last_seen` 并返回 `{"heartbeat":true}`,不进活动流。
身份 = `operator + (agent 或 runtime)`。
## 后果
- ✅ 活动流只反映真实状态转变;卡片与活跃时长仍实时更新。
- 约束:活动流不可改成"每心跳一条"。
