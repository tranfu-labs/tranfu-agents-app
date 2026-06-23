# spec delta:ingest(本变更修订的规则)

> 合入后并入 `openspec/specs/ingest/spec.md`,覆盖 `self-update-shims` 留下的相关条目。

## 修订规则(MUST)

- `shim_version` 由 "profile 子字段" 升格为 **`/v1/events` 顶层可选字段**。
  - 客户端 SHOULD 在每次事件上报时携带该字段(取本机 `~/.tranfu/manifest.json` 的 `version`),
    哪怕事件不是 `SessionStart`。
  - 旧客户端只通过 profile 携带的路径仍兼容(服务端兜底入库一次)。
- 服务端**不得**再把 `shim_version` 作为 profile 全量替换的一部分;
  必须按 `(operator, agent_key, runtime)` 粒度独立存储,**收到非空值时更新,缺失时保留旧值(sticky)**。
- 服务端持久化字段不得包含 prompt、代码、输出或用户私密内容(语义沿用)。

## 可验证行为(新增)

- 三连事件场景:`{shim_version: A}` → `{}`(无该字段) → `{shim_version: B}`,
  服务端按 sticky 语义,聚合视角下该 agent 的 `shim_version` 依次为 A、A、B。
- OpenClaw 上报的 payload **必须**包含 `shim_version` 顶层字段(只要本机 manifest 可读)。
- 旧 shim 客户端只在 SessionStart 通过 profile 传 `shim_version`,服务端仍能在 `agent_shim_versions` 表写入一次。
