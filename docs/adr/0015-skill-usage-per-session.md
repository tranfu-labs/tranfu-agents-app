# ADR-0015 Skill 使用按会话去重统计

- 状态:Accepted
- 关联:ADR-0003(心跳去重)、ADR-0005(shim 自动探测)、ADR-0014(存储上限)、PROTOCOL.md §5 §6

## 背景 / 问题

`skills_seen` 与 profile 只能说明某台机器装过哪些 Skill,不能回答团队实际用了哪些 Skill。
运营需要长期趋势判断维护、沉淀或下架,但上报链路是 at-least-once,不能用简单计数器递增。

## 决策

- 事件可带可选顶层字段 `skill`,只记录 Skill 名,不记录参数、prompt、代码、输出或记忆。
- 口径为**一个会话用过某 Skill 算一次**;同一 `session_id + skill` 重复投递通过唯一键幂等。
- `skill_uses` 专用表永久保留,不跟随 `events` 的 90 天窗口清理。
- shim 默认上报 Skill 名;本机设置 `TF_REPORT_SKILLS=0` 时不得附加 `skill` 字段。
- ingest 必须在心跳短路前处理 `skill`,避免重复 status/step 的 Skill 调用被吞掉。
- 无 `session_id` 时无法按会话去重,因此忽略 `skill` 并正常返回。

## 后果

- ✅ 能稳定得到团队真实使用排行,且 spool 重试不会重复计数。
- ✅ Skill 名被视为工具级元数据,敏感度与工具名、已装 Skill 清单相同,不触碰内容捕获硬约束。
- ⚠️ 服务端上线后不会自动产生历史数据;队友需重跑 `install.sh` 更新本地 shim,数据逐步出现。
- ⚠️ 子代理若有独立 `session_id`,其 Skill 使用会独立计数;未来如需按顶层任务归并,在读侧利用 parent 链处理。
