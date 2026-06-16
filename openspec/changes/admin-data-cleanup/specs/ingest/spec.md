# spec delta:ingest(本变更修改的不变量)

> 合入后并入 `openspec/specs/ingest/spec.md`。本变更只补一条与删除联动的不变量,采集行为本身不变。

## 修改不变量(MUST)
- `skills_seen.first_day` 不再只是"首次出现即写入、此后不动"。当某 skill 的 `skill_uses` 引用因后台清理(admin 域 `_purge`)或恢复(restore)发生增减时,`first_day` 必须**按剩余引用重算**(取剩余最早首见日;无引用则删除该行)。详见 specs/admin。
