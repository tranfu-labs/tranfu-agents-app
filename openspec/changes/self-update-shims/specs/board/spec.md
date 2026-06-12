# spec delta:board(本变更新增的规则)

> 合入后并入 `openspec/specs/board/spec.md`。

## 新增规则(MUST)
- `GET /api/state` 返回 `shim.version`,表示服务端当前分发的 shim 内容版本。
- 看板在 agent 卡片或详情中显示本机上报的 `shim_version` 短码。
- 当某 agent 的 `shim_version` 缺失或不等于 `shim.version` 时,看板必须显示过期/旧版提示。

## 可验证行为(新增)
- 服务端当前版本为 `abc...`,某 agent profile 上报 `shim_version=abc...` → 不显示过期。
- 某 agent profile 缺失版本或上报不同版本 → 显示过期角标。
