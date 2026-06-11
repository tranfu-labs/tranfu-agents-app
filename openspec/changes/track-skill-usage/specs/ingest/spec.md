# spec delta:ingest(本变更新增的规则)

> 合入后并入 `openspec/specs/ingest/spec.md`。

## 新增规则(MUST)
- 事件 JSON 接受可选字段 `skill`(字符串,skill 名;不含参数与内容)。
- 事件同时具备 `skill` 与 `session_id` 时,服务端记录"该会话用过该 skill",
  以 `(session_id, skill)` 幂等:同会话同 skill 重复投递(含 spool 重试)不得产生第二条记录。
- 该记录保留 `session_id`、`operator`、`runtime`、首见日期(UTC 日),
  且**不受 events 90 天保留窗口影响**(永久保留)。
- 即使事件命中心跳去重(status/step 无变化仅刷新 last_seen),`skill` 字段仍必须被处理。
- 事件无 `session_id` 时,`skill` 字段忽略:不落库、不报错、正常返回。
- shim 侧:`TF_REPORT_SKILLS=0` 时不得附加 `skill` 字段;默认(未设置或非 0)附加。
  skill 名提取失败时不附加该字段,不得阻塞或报错(沿用 shim 静默约定)。
- 向后兼容:不带 `skill` 字段的事件(旧 shim),ingest 行为与现状完全一致。

## 可验证行为(新增)
- 同一 session_id + 同一 skill 投递两次 → 记录 1 行;第二次响应仍 200。
- 两个不同 session_id 各报同一 skill → 2 行。
- 带 skill 但无 session_id 的事件 → 200,0 行。
- 连续两个相同 status/step 的事件均带同一 skill → 第二个命中 heartbeat 路径,记录仍为 1 行
  (即字段被处理过,而非 0 行)。
- 同一 session_id 报两个不同 skill → 2 行。
