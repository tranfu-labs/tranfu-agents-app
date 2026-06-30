# 提案：use-shanghai-stats-day

## 背景
当前服务端的日级统计默认按 UTC 日切分:

- ingest 写入 `events.day`、`skill_uses.day`、`skills_seen.first_day` 时取 UTC `recv[:10]`。
- `/api/state` 活跃时长、`/api/state.skills`、`/api/skills`、`/api/skill/{name}`、`/api/operator/{name}` 的 `today` 与 7/30/90 天窗口也按 UTC 日期计算。

TRANFU//AGENTS 的默认部署和使用者主要按中国自然日理解"今天"、"近 7 天"、"本周"和 SKILLS 趋势。UTC 日切在北京时间 00:00-07:59 会把当天数据归到前一天,看板与运营认知不一致。

## 提案
把全局日级统计默认口径改为 `Asia/Shanghai`:

- 新写入的 `events.day`、`skill_uses.day`、`skills_seen.first_day` 使用 `Asia/Shanghai` 日期。
- 读侧 `today`、7/30/90 天 cutoff、趋势日轴、本周起点、活跃时长按 `Asia/Shanghai` 日边界计算。
- `recv`、`last_seen`、`first_seen` 等具体时刻继续保存 UTC ISO instant,用于排序、stale 判断和最近记录展示。
- 不迁移旧数据。历史已经落库的 UTC `day` 保持原样,上线后新数据按上海日进入统计。

## 影响
- 服务端:涉及 `server/db.py`、`server/routes/ingest.py`、`server/routes/board.py`。
- API 行为:`/api/state.now` 仍为 UTC instant;日级字段 `day`、`first_day`、`last_day`、`today` 语义变为 `Asia/Shanghai` 日期。
- Admin 行为:`before_day` 和 `first_day` 等 date-only 字段跟随服务端统计日语义。
- 前端:无需版式变更,继续按服务端 `today` 铺日轴。
- 文档/spec:同步 board / ingest 规格、架构说明与 AGENTS 约定。
