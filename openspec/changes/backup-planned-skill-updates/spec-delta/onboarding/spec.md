# onboarding 规格增量：只备份本轮更新计划

## 新增规则

- runner 更新前必须调用 `tfs update --skills-only --check-only --json`,只把 `status=outdated` 的 path
  交给备份流程;不得调用 `tfs installed --json` 全量枚举。
- 任一 outdated 项缺少有效 path 或计划 JSON 无效时,必须停止且不得执行正式 update。
- runner 不按 scope/runtime/hash 筛选;计划范围与 path 由 tfs 决定。

## 可验证行为

- 计划含 user outdated 与 Documents project noop/未列出项 → 只备份 user path,不访问 Documents。
- 计划为空 → 不访问 Skill 路径,仍可执行正式 update。
- outdated 缺 path → 状态为 `update_plan_failed`,正式 update 未调用。
