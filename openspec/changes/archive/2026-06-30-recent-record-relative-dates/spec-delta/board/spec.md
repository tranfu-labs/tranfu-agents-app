# specs/board delta：最近记录 date-only 相对日期

## 修改

- 操作员详情与单 skill 详情的"最近记录"列表中,若 `first_seen` 缺失但存在原始 UTC date-only `day`,时间列可见文本须显示相对日期:
  - `day` 等于服务端返回的 UTC `today` 时,中文显示 `今天`,英文显示 `today`。
  - `day` 等于 `today - 1` 时,中文显示 `昨天`,英文显示 `yesterday`。
  - 更早日期显示 `N天前` / `Nd ago`。
  - 鼠标悬浮 title 保留原始 `day`,不得把 date-only 值强行按浏览器时区换算或补造具体时刻。
  - 未来日期、非法日期或缺失值仍回退原始文本。

## 不变

- `first_seen` 有效时的最近记录规则不变:浏览器本地今天内显示分钟/小时相对时间,昨天及更早显示本地绝对时间,hover 显示本地绝对时间+时区。
- `day`、`first_day`、`last_day`、`today`、SKILLS 图表日轴与日级聚合仍是服务端 UTC 日口径。
- `/api/skill/{name}` 与 `/api/operator/{name}` 响应字段不变。

## 可验证行为

- `today=2026-06-30`,记录仅有 `day=2026-06-30` 且无 `first_seen` → 最近记录可见文本为 `今天`,title 为 `2026-06-30`。
- `today=2026-06-30`,记录仅有 `day=2026-06-29` 且无 `first_seen` → 最近记录可见文本为 `昨天`,title 为 `2026-06-29`。
- `today=2026-06-30`,记录仅有 `day=2026-06-25` 且无 `first_seen` → 最近记录可见文本为 `5天前`,title 为 `2026-06-25`。
