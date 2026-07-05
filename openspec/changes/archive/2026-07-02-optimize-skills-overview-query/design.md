# 设计：optimize-skills-overview-query

## 方案

### 1. 补充组合索引
现有 `skill_uses` 索引只有：

- `idx_skill_uses_skill(skill)`
- `idx_skill_uses_skill_mode(skill, mode)`
- `idx_skill_uses_day(day)`

只读诊断中的合成样本显示，当前 operator 聚合存在全表扫描；单列索引不足以覆盖
`mode='used'`、时间窗口、operator、skill、runtime 组合查询。

计划新增面向读路径的组合索引：

- `idx_skill_uses_mode_day_skill_runtime_operator`：服务 daily、period、attribution、governance、
  operator daily/trend 等窗口聚合。
- `idx_skill_uses_mode_operator_day_skill_runtime_session`：服务 operator 聚合、operator daily、
  distinct session 统计和 runtime/source 分布。
- `idx_skill_uses_mode_skill_day_operator_runtime`：服务 skill 维度的全历史与窗口聚合。

索引通过 `server/db.py` 的 `_ensure_skill_uses_schema` 幂等创建，兼容现有 SQLite 单文件部署。

### 2. 改写 operator 聚合
当前 `skills_overview` 中 operator 聚合查询按
`operator, session_id, skill, runtime, day` group 后交给 Python 逐行累加。
由于 `skill_uses` 主键已经是 `(session_id, skill, mode)`，这条路径在常规 used-only 聚合里接近扫描 raw
`skill_uses` 全历史行数。

改写为分层聚合：

- SQL 先按 `operator, skill, runtime` 计算全量、7d、30d、当前窗口、上期窗口、最近日期等 operator
  汇总字段。
- SQL 单独按 `operator` 计算 distinct `session_id`，保持 `session_count` 语义。
- SQL 按当前窗口和近 14 天分别生成 `operator_daily` 与趋势所需的 `day/operator/skill/runtime` 聚合行。
- Python 只负责：
  - 应用 catalog source 映射和 `src` 过滤。
  - 汇总 `runtime_counts`、`source_counts`、`window_*`、`trend_14d`。
  - 输出现有 `operator_table` / `operator_daily` 字段和排序。

这样避免为 operator 视角读取每条 raw session-skill 行，同时不把 catalog source 逻辑下推到 SQL，
保持 catalog 映射仍在 board 域已有 helper 中集中处理。

### 3. 缓存边界
本轮默认不新增 `/api/skills` TTL 缓存。若 SQL/索引优化后在同环境仍达不到目标，下一步才允许引入短 TTL：

- 默认 5 秒，允许范围 3-10 秒。
- 缓存键必须归一化 `days/w/wstart/wend/rt/src/scope`。
- 缓存必须有上限，不能无界增长。
- 必须覆盖不同 `days/w/wstart/wend`、`rt/src/scope` 隔离和 TTL 过期测试。

缓存若进入实现，应仍保持在 `server/routes/board.py` 的 board 读路径内，不引入外部缓存服务。

## 权衡

- 选择索引 + SQL 聚合改写，而不是先加缓存：缓存见效快但会掩盖 SQL 根因，也增加新鲜度与缓存键治理成本。
- 暂不做预聚合表：预聚合性能上限更高，但会引入新持久状态和一致性成本；当前证据尚不足以证明必要。
- 不做前端渐进渲染：生产采样显示 HTML 快、API TTFB 慢，前端拆请求只能改善体感，不能解决主瓶颈。
- 不下推 catalog source 到 SQL：source 来自 catalog 映射和 fallback 规则，留在 Python helper 中更清晰，避免跨层耦合。

## 测试与验证

### 单元/契约测试
需要覆盖：

- `/api/skills?w=7d` 的 `operator_table` 排序、`sessions_window`、`previous_sessions`、`sessions_30d`、
  `sessions_total`、`session_count`、`window_skill_count` 不回归。
- `rt/src` 对 `operator_table` 和 `operator_daily` 取交集过滤，不影响 skill 视角 `table/daily`。
- `scope=new` 下 operator 聚合只收敛到当前窗口历史首次 used skill。
- `mode=equipped` 和空 operator 不进入 operator 聚合。
- `operator_daily` 只输出当前 `window.start..window.end` 内 used rows。

### 性能验证
实现前后用同一脚本在本地或 CI 可运行的临时 SQLite 样本上采样：

- 固定生成 `skill_uses` 合成数据，例如 10k、50k、100k、300k rows。
- 记录 `/api/skills?w=7d` 或直接调用 `skills_overview(conn, 30, "7d")` 的 best/avg/P95。
- 记录关键 SQL 的 `EXPLAIN QUERY PLAN`，确认 operator 路径不再全表 raw scan。
- 最终评论列出 before/after，明确生产库规模和生产 EXPLAIN 未拿到。

### 必跑命令
按仓库实际脚本执行：

- `python -m py_compile server/*.py server/routes/*.py`
- `python -m pytest -q`
- `python -m coverage run -m pytest && python -m coverage report --include='server/**/*.py'`
- `npm --prefix frontend run test:unit`
- `npm --prefix frontend run build`

## 风险

- 新增组合索引会增加 SQLite 文件体积和写入时索引维护成本；但 `skill_uses` 写入频率低于 `/api/skills`
  读聚合压力，且本次只新增有限数量索引。
- 聚合改写可能造成边界语义回归，尤其是 `scope=new`、`rt/src`、空 operator、equipped 排除和
  `session_count` distinct 语义；用现有测试扩展覆盖。
- 若生产实际数据分布与合成样本差异很大，可能仍达不到 P95 < 800ms；届时按已定义边界评估短 TTL 缓存，
  不直接引入预聚合表。

## 回滚

- 代码回滚即可恢复旧聚合逻辑。
- 新增索引可保留；若需要完全回退，可在独立 migration 中 `DROP INDEX IF EXISTS ...`。
- 因本轮不新增持久汇总表，回滚不涉及数据迁移或一致性修复。
