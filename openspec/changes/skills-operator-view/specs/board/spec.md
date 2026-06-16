# spec delta:board(本变更新增/修改的规则)

> 合入后并入 `openspec/specs/board/spec.md`。建立在 skills-stats-page 的 SKILLS 视图规则之上。

## 接口(新增 / 扩展)
- `GET /api/skills` **扩展**:在既有 `{ daily[], table[], funnel, catalog }` 上新增
  `operator_table[]`(每 operator:7/30/累计使用次数、用过 skill 去重数、会话数、各 runtime 计数、
  近 14 天逐日序列、最近使用日)与 `operator_daily[]`(逐 日×operator 的 used 计数)。
  既有字段与 `days` 语义不变;`days` 同样作用于 `operator_daily`,不影响 `operator_table`。
- `GET /api/operator/{name}` **新增** → 单操作员详情(指标、按 skill 分段的日级序列、
  该人 skill 排行、runtime 分布、最近记录);查无此人 → 404。

## 新增规则(MUST)
- SKILLS 总览页提供"视角切换"(按 skill / 按人)。切换为**整页换主语**:柱状图、主表、行级下钻
  统一为同一主语,不得混搭(不得出现柱状图按人而主表按 skill)。筛选条为两视角共用,仅搜索框
  提示语随视角变。
- 按人视角的所有聚合(`operator_table`、`operator_daily`、`/api/operator/{name}`)**只统计
  `mode=used`**;equipped 不进按人视角任何位置(装备态仅在单 skill 详情页出现)。
- 人维度计量单位 = 会话×skill 去重(`skill_uses` 主键 `(session,skill,mode)` 的 used 行计数),
  语义为"此人在多少个会话里用过 skill",界面须标注其非真实调用次数。
- `operator` 为空的会话不计入 `operator_table`、`operator_daily` 与按人柱状图(不做"未识别"兜底行)。
- 人排行主表固定 7天/30天/累计三列,时间窗只作用于按人柱状图;两视角时间窗统一默认 30 天,
  切换视角不重置当前时间窗。人主表默认按 30 天使用次数降序,平手按累计。
- 按人柱状图按 UTC 日、柱内按 operator 分段;前端取窗口内前 8 的 operator 分色,其余合并为"其它"段
  (复用 skill 视角柱状图的 Top8+其它/悬浮高亮逻辑,仅分段维度不同)。
- 公司库漏斗为独立健康面板,两个视角都显示同一套 skill/catalog 口径漏斗,不随视角增删或改口径。
- 双向下钻:单 skill 详情可达"谁用了它"(既有 operator 分布);单操作员详情的 skill 排行行可跳转
  至对应 `/skill/{name}` 详情。
- `operator_*` 字段与 `/api/operator/{name}` 不进 2 秒主轮询;按人视角进入时加载、低频刷新,
  失败显示错误态。

## 可验证行为(新增)
- 同一操作员在同一会话内多次用同一 skill → 该 (会话,skill) 在按人计数中只计 1。
- 某 skill 对某操作员同时有 used 与 equipped(OpenClaw)→ `operator_table` 与 `/api/operator/{name}`
  仅反映 used,equipped 任何字段不出现、不相加。
- 仅在 OpenClaw 装备过、从未 used 的操作员 → 不出现在 `operator_table` 与按人柱状图。
- 采不到 operator 的会话 → 不出现在 `operator_table`、`operator_daily`。
- 视角从"按 skill"切到"按人"→ 柱状图分段、主表主语整页一致切换,漏斗保持显示,当前时间窗不变。
- `days=7` → `operator_daily` 仅含最近 7 个 UTC 日,`operator_table` 三列不受影响。
- 单操作员详情的 skill 排行行点击 → 进入对应 skill 详情(双向下钻闭环)。
- `GET /api/operator/不存在的人` → 404。
