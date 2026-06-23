# spec delta:board(本变更修订的规则)

> 合入后并入 `openspec/specs/board/spec.md`,覆盖 `self-update-shims` 留下的相关条目。

## 修订规则(MUST)

- `/api/state` 返回的 agent card `shim_version` 字段来源,改为**该 agent 最近一次非空上报值**(sticky),
  不再随 profile 全量替换的缺失而清空。
- 看板"shim 版本"状态由二态(在线 / 旧 shim)扩为**三态**:
  - `current` —— `agent.shim_version` 等于服务端 `shim.version`(常态显示)。
  - `outdated` —— `agent.shim_version` 存在但不等于服务端 `shim.version`(显示"旧 shim",橙色)。
  - `unknown` —— `agent.shim_version` 缺失/空(显示"等待客户端心跳",灰色)。
- `unknown` 不得被误标为 `outdated`(即:不允许"字段缺失 → 旧"的简化判定)。

## 可验证行为(新增)

- 服务端 `shim.version=X`,某 agent 上报 `shim_version=X` → 卡片为 `current`,无角标。
- 同一 agent 上报 `shim_version=Y(≠X)` → 卡片为 `outdated`,显示"旧 shim"。
- 某 agent 从未上报过 `shim_version` → 卡片为 `unknown`,文案"等待客户端心跳",颜色灰。
- 已上报过的 agent 后续事件不带 `shim_version` → 卡片仍呈现最近一次非空值,不退回 `unknown`。
