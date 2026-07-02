# Board Spec Delta：optimize-skills-overview-query

## 修改

### `/api/skills` 性能边界
`GET /api/skills` 的 overview 聚合必须保持 used-only 和窗口语义不变，同时避免无必要的 raw
`skill_uses` 全历史逐行扫描。实现应优先使用 SQLite 组合索引和 SQL 预聚合降低 Python 侧处理行数。

验收要求：

- 同一环境下 `/api/skills?w=7d` TTFB/总耗时 P95 应小于 800ms。
- 相对变更前同环境采样至少 3x 改善；如未达成，必须说明剩余瓶颈。
- 生产库规模或生产 `EXPLAIN QUERY PLAN` 拿不到时，不得声称已验证生产 P95，只能报告可复现环境和合成样本数据。

### Operator 聚合语义
`/api/skills.operator_table` 与 `operator_daily` 的优化不得改变既有语义：

- 只统计 `mode='used'`。
- 排除空 operator。
- `rt` 与 `src` 仅应用于 `operator_table` / `operator_daily`，且同时存在时取交集。
- `scope=new` 时，operator 聚合必须收敛到当前窗口内历史首次 used 的 skill 名单。
- `operator_daily` 只输出当前 `window.start..window.end` 内的记录。
- `sessions_window`、`previous_sessions`、`sessions_total`、`session_count`、`skill_count`、
  `window_skill_count`、runtime/source 计数和近 14 天趋势必须保持原字段语义。

### `/api/skills` 缓存边界
不得优先用缓存掩盖聚合根因。只有在 SQL/索引优化后仍无法达到性能目标时，才允许引入 `/api/skills`
短 TTL 缓存。若引入缓存：

- 默认 TTL 为 5 秒，允许配置范围 3-10 秒。
- 缓存键必须归一化 `days/w/wstart/wend/rt/src/scope`。
- 缓存容量必须有上限，避免无界增长。
- 必须覆盖不同窗口、runtime/source、scope 隔离和 TTL 过期行为。
