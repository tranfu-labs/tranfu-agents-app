# 提案：optimize-recent-record-time

## 背景
SKILLS 详情页的"最近记录"目前通过 `fmtTs(first_seen)` 直接截取 ISO 字符串前 19 位,把服务端 UTC 时间显示成不带时区的墙钟时间。用户在浏览器本地时区查看时会误读事件发生时间。

用户确认的目标是:

- `first_seen` 这类具体时间戳按浏览器本地时区显示。
- 最近记录中,浏览器本地"今天"内的记录显示克制的相对时间。
- 浏览器本地昨天及更早的记录显示绝对时间。
- 鼠标悬浮时显示浏览器时区下的绝对时间。
- 顺带检查是否还有同类时区问题。

## 提案
1. 为前端新增一组可单测的本地时间格式化函数:
   - 具体 ISO 时间戳转浏览器本地绝对时间。
   - 最近记录专用:本地今天内显示相对时间;本地昨天及以前显示绝对时间;同时返回 hover title。
2. `/skill/:name` 与 `/operator/:name` 的"最近记录"首列改用最近记录专用格式。
3. 广度修正:后台 `/admin` 中同样用 `fmtTs()` 直接截 ISO 的位置,改为浏览器本地绝对时间,避免同类 UTC 伪装成本地时间。
4. 明确不改变服务端 UTC 统计口径:`day`、`first_day`、`last_day`、图表日轴、`today` 仍按既有 UTC 日语义展示和计算。

## 影响
- 受影响模块:
  - `frontend/src/lib/*`:新增/调整时间格式化函数与单测。
  - `frontend/src/views/SkillDetail.tsx`、`frontend/src/views/OperatorDetail.tsx`:最近记录时间展示。
  - `frontend/src/views/Admin.tsx`:具体时间戳展示转浏览器本地绝对时间。
  - `docs/wireframes/pages/skill-detail.md`、`docs/wireframes/pages/operator-detail.md`:归档时回流最近记录线框变化。
- 不影响服务端 API、SQLite schema、Skill 聚合口径和 UTC 日统计。
