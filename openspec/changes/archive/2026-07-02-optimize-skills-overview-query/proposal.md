# 提案：optimize-skills-overview-query

## 背景
`/skills?view=operator&w=7d` 首屏慢点已经通过只读诊断收敛到后端
`/api/skills?w=7d` 聚合路径，而不是页面 HTML、传输体积或前端渲染。

已采样的生产现象：

- `/skills?view=operator&w=7d` 页面 HTML 约 0.10-0.23s。
- `/api/skills?w=7d` 5 次采样约 3.92s、4.31s、4.54s、5.22s、4.69s。
- TTFB 接近总耗时，响应约 133KB，`table=167`、`operator_table=9`、
  `current_sessions=324`。

生产端 `TF_DB`、行数和 `EXPLAIN QUERY PLAN` 当前拿不到，因此本次不承诺已验证生产 P95。
后续验证以同环境 before/after 和合成样本为准，并在最终说明里明确这一限制。

## 提案
优化 `/api/skills` 的 SQLite 聚合路径，范围限定为后端聚合、索引和测试：

- 为 `skill_uses` 增加面向 `/api/skills` 读路径的组合索引，减少 `mode='used'`、
  时间窗口、skill、operator、runtime 聚合时的全表扫描和回表成本。
- 改写 `skills_overview` 中 operator 维度聚合，避免 Python 逐 raw session-skill 行扫描全历史；
  改为用 SQL 先按 operator/skill/runtime/day 等低基数字段聚合，再在 Python 侧完成 catalog source
  映射和现有字段组装。
- 保持 `/api/skills` 响应语义不变：`view=operator` 仍是前端视角参数，后端 `/api/skills`
  仍返回 skill/operator 两套聚合字段；operator 口径仍为 used-only、排除空 operator，并继承 `w/days`
  与 `rt/src/scope` 语义。
- 不做前端渐进渲染，不引入预聚合表，不改变模块边界。
- 短 TTL 缓存只作为 SQL/索引优化后仍不达标时的第二层；本轮默认不启用缓存。

## 影响
受影响模块：

- `server/db.py`：补充 `skill_uses` 组合索引，放在 schema/migration 初始化路径中。
- `server/routes/board.py`：改写 `/api/skills` overview 的 operator 聚合实现。
- `tests/`：补充或扩展 SKILLS overview 行为测试和性能验证辅助测试。
- `openspec/specs/board/spec.md`：归档时补充 `/api/skills` 性能与缓存边界要求。

验收目标：

- 同一环境下 `/api/skills?w=7d` TTFB/总耗时 P95 < 800ms。
- 相对 before 至少 3x 改善。
- 若只能达到 800ms-1s，最终说明需列出剩余瓶颈和下一层方案。
- 最终回复必须列出实际跑过的 test/build/typecheck 命令及结果。
