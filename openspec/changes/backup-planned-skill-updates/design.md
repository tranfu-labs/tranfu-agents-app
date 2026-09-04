# 设计：backup-planned-skill-updates

## 方案
新增 `_update_plan(tfs_bin)`:执行 `update --skills-only --check-only --json`,解析 `skills[]`,只返回
`status == "outdated"` 的 `{name,path}`。任何 outdated 项缺 path、path 非字符串或 JSON 无效均返回
`update_plan_failed`,不执行正式 update。

runner 把计划项交给现有 `_snapshot_inventory()`,因此路径安全、备份原子性、registry 快照和回滚不变。
计划为空时仍创建只含 registry 的完整 run,随后执行 update;避免复制 tfs 的最终更新判断。

## 权衡
不再调用 `tfs installed --json`,避免访问本轮不会更新的 project/Documents 路径。runner 只识别 tfs 的
`outdated` 计划状态,不解释 scope/runtime/hash。

## 风险
要求新版 tfs 输出 path;旧版会安全失败而非无备份更新。check 与 update 之间远端极短竞态仍由 tfs 行为承担;
本 change 不引入 scope 推导或第二套更新规则。
