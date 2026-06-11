# spec delta:board(本变更新增的规则)

> 合入后并入 `openspec/specs/board/spec.md`。

## 新增规则(MUST)
- `GET /api/state` 返回 `skills` 数组,每项含 `name`、`sessions_7d`、`sessions_30d`、
  `sessions_total`、`users_30d`、`last_day`;按 `sessions_30d` 降序,平手按 `sessions_total`。
- 计数口径:一个会话用过某 skill 算一次(来源即 `skill_uses` 的会话×skill 粒度,读侧不再去重)。
- 时间窗口按 UTC 日切,与活跃统计口径一致。
- 看板展示 Skills 排行区;`skills` 为空时显示空态,不报错。

## 可验证行为(新增)
- 造数据:skill A 在 31 天前 1 个会话、5 天前 2 个会话(2 个不同 operator)使用 →
  `sessions_7d=2`、`sessions_30d=2`、`sessions_total=3`、`users_30d=2`。
- 空库 → `skills: []`,看板显示空态。
- 排行顺序:30 天会话数高者在前。
