# spec delta:ingest(本变更新增的规则)

> 合入后并入 `openspec/specs/ingest/spec.md`。

## 新增规则(MUST)
- profile 可选字段新增 `shim_version`,取值为本机 `~/.tranfu/manifest.json` 中的 `version`。
- 服务端必须像其它 profile 字段一样按身份保存最新 `shim_version`;该字段不得包含 prompt、代码、输出或用户私密内容。

## 可验证行为(新增)
- 带 `shim_version` 的 profile 事件写入后,`/api/state.sessions[]` 对应卡片包含同值 `shim_version`。
