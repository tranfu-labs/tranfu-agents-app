# specs/admin delta：date-only 字段跟随 Asia/Shanghai 统计日

## 修改

- `before_day` 选择器继续表示 `day < before_day`,但 `day` 的语义改为服务端 `Asia/Shanghai` 统计日期。
- `/admin` 中 `first_day` 等 date-only 字段保持服务端统计日期语义,不得按浏览器时区换算。

## 不变

- ISO 时间戳字段仍按浏览器本地时区显示为绝对时间。
- `before_day` 仍必须带 `operator`,禁止全局无 operator 作用域。
