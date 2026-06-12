# ADR-0014 存储与 schema:限流 / 90天保留+WAL / profile 全量覆盖 / session 去重 / parent / 版本号

- 状态:Accepted
- 关联:PROTOCOL.md §3 §6 §8、ADR-0003、ADR-0004

## 背景 / 问题
一组与存储和 schema 相关的缺口需要一并收口。

## 决策
- **限流(§8):** 请求体 > 256 KiB 直接 413;落库 `input`/`output` 各截断 16 KiB、`meta` 4 KiB;
  看板展示再截断到 4000 字。防止超大 POST 撑爆 SQLite/内存。
- **保留 + WAL:** 事件表只保留 90 天窗口,更早的删除(插入时按计数节流触发 prune);
  连接开启 `journal_mode=WAL`,读写互不阻塞。
- **profile 全量覆盖(修订 ADR-0004):** 带 profile 的事件按 full-snapshot 语义整体替换旧 profile,
  **不再 `dict.update` 增量合并**。本地删掉的技能/集成会真正消失,避免 leverage/reuse 被陈旧条目刷高。
  `leverage` 口径明确为"累计曾出现过的资产",非"当前在用"。
- **去重键含 session_id(修订 ADR-0003):** 去重键 = `operator+runtime+agent+session_id`。
  同一身份并发多个 session 不再互相吞掉活性。
- **parent_session_id:** 新增可选字段/列,子 agent 挂到父 run 下,可重建 agent 树。
- **事件版本号 `v`:** 新增可选 `v` 字段(当前 "0.1"),便于未来兼容路由。
- **传输(§3):** 标准 Python/shell shim 必须 fire-and-forget + 短超时;失败本地 spool(有界)、至少一次投递。
  服务端去重容忍重复,所以"至少一次"安全。进程内插件若承载派生统计而非核心状态事件,可按后续 ADR 的
  更具体约束处理(例如 ADR-0018 的 OpenClaw equipped skill reporter)。

## 后果
- ✅ 高事件率下更稳;敏感大载荷有界;离线不丢事件。
- 约束:改 schema 列时保留 `init_db` 里的 ALTER 兜底以兼容旧库。
