# ADR-0003 心跳去重:状态/步骤变化或长断档恢复才落新行

- 状态:Accepted
## 背景
agent 会高频发心跳;若每条都落库,活动流与存储都会噪声爆炸。
## 决策
`POST /v1/events`:当 `status` 或 `current_step` 相对该身份上一行**发生变化**时 INSERT 新行;
连续段内的纯心跳只 UPDATE `last_seen` 并返回 `{"heartbeat":true}`,不进活动流。
若 status/step 未变化但距上一条已确认心跳超过 `STALE_SECONDS=180`,仍须 INSERT 新行作为恢复后的
连续段起点,不得覆盖旧行 `last_seen`;pending batch 中尚未 flush 的最新心跳也算已确认心跳。
恢复边界使用内部来源 `heartbeat_resume`,参与最新卡片与 metrics,但不进入只展示状态变化的 feed。
身份 = `operator + (agent 或 runtime)`。
## 后果
- ✅ 活动流只反映真实状态转变;卡片与活跃时长仍实时更新。
- ✅ 异常退出后同状态恢复不会抹掉断档边界。
- 约束:活动流不可改成"每心跳一条";长断档恢复行是内部计时边界,不得作为状态变化展示。
