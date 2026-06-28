# specs/board delta：浏览器本地时间展示

## 修改

- 操作员详情与单 skill 详情的"最近记录"列表,时间列须以浏览器本地时区展示 `first_seen`:
  - 当 `first_seen` 落在浏览器本地今天且不晚于当前时间时,可见文本显示克制相对时间:
    中文 `刚刚` / `N分钟前` / `N小时前`,英文 `just now` / `Nm ago` / `Nh ago`。
  - 当 `first_seen` 落在浏览器本地昨天及更早时,可见文本显示本地绝对时间
    `YYYY-MM-DD HH:mm:ss`。
  - 鼠标悬浮时间单元格时,title 须显示浏览器本地绝对时间与浏览器时区名
    (如 `2026-06-28 10:32:07 Asia/Shanghai`;时区名不可得时省略)。
  - `first_seen` 缺失时回退原始 UTC 日期 `day`,不得把 date-only 值强行按浏览器时区换算。

## 不变

- `day`、`first_day`、`last_day`、`today`、SKILLS 图表日轴与日级聚合仍是服务端 UTC 日口径。
- `/api/skill/{name}` 与 `/api/operator/{name}` 响应字段不变。

## 可验证行为

- 浏览器时区为 Asia/Shanghai,当前本地时间为 `2026-06-28 01:00:00`,记录
  `first_seen=2026-06-27T16:30:00+00:00` → 最近记录可见文本为 `30分钟前`,hover title 为
  `2026-06-28 00:30:00 Asia/Shanghai`。
- 同一当前时间,记录 `first_seen=2026-06-27T15:00:00+00:00` → 可见文本为
  `2026-06-27 23:00:00`,不得显示相对时间。
- 仅有 `day=2026-06-27` 且无 `first_seen` → 可见文本回退 `2026-06-27`。
