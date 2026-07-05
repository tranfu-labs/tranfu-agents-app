# specs/admin delta：后台具体时间戳按浏览器时区展示

## 新增

- `/admin` 前端中来自 ISO 时间戳的具体时刻字段(如清单 `last_seen`、删除预览活跃会话
  `last_seen`、回收站批次 `created`)须按浏览器本地时区显示为绝对时间
  `YYYY-MM-DD HH:mm:ss`。
- `/admin` 不使用相对时间展示具体时间戳,以保证清理操作界面的判断稳定。
- date-only 字段(如 `first_day`)保持原始 UTC 日期语义,不得按浏览器时区换算。

## 可验证行为

- 浏览器时区为 Asia/Shanghai,`last_seen=2026-06-27T16:30:00+00:00` → `/admin` 可见时间为
  `2026-06-28 00:30:00`。
- 清单行无 `last_seen` 但有 `first_day=2026-06-27` → 仍显示 `2026-06-27`。
