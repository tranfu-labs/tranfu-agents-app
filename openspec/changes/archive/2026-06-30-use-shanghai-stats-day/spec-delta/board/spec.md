# specs/board delta：全局日级统计默认 Asia/Shanghai

## 修改

- `/api/skills?days={7|30|90}` 返回的 `today` 改为服务端统计时区 `Asia/Shanghai` 当日;`days` 影响的 daily/operator_daily 与 governance 窗口按 `Asia/Shanghai` 日期计算。
- `/api/skill/{name}` 与 `/api/operator/{name}` 返回的 `today`、`first_day`、`last_day`、7/30 天指标、日级序列均按 `Asia/Shanghai` 日期语义。
- `/api/state` 中活跃统计的 `today_active`、`week_active`、`active_series`、`active_days` 按 `Asia/Shanghai` 日边界拆分;`/api/state.now` 仍是服务端 UTC instant。
- `/api/state.skills` 的 7/30 天、`last_day` 和趋势按 `Asia/Shanghai` 日期语义。
- SKILLS 图表横轴仍以服务端 `today` 为右端,但该 `today` 是 `Asia/Shanghai` 当日。

## 不变

- 具体时间戳字段 `recv`、`last_seen`、`first_seen` 继续保存 UTC ISO instant。
- 最近记录中 `first_seen` 的浏览器本地展示规则不变。
- 旧数据不迁移;历史已写入的 `day` 保持原值,新写入数据进入 `Asia/Shanghai` 日期桶。
- `mode=used` 与 `mode=equipped` 的隔离口径不变。

## 可验证行为

- 服务端当前 UTC 时间为 `2026-06-12T16:05:00+00:00` 时,`/api/skills` 与 `/api/skill/{name}` 返回 `today=2026-06-13`。
- 一个活跃区间从 `2026-06-12T15:59:00+00:00` 到 `2026-06-12T16:01:00+00:00` 时,活跃秒数按上海日边界拆成 `2026-06-12` 60 秒与 `2026-06-13` 60 秒。
- `days=7` 的 SKILLS daily 只包含服务端上海日 `today` 往前 6 天内的 `day`。
