# 设计：recent-record-date-relative-time

## 方案
`formatRecentRecordTime()` 继续作为 Skill 详情和 Operator 详情的唯一入口:

1. `first_seen` 无效或缺失:
   - 复用现有 `formatRecentRecordDay()`。
   - 以服务端 UTC `today` 为 date-only 相对日期基准。
2. `first_seen` 有效且晚于当前时间:
   - 继续返回本地绝对时间,避免未来时间显示成负相对值。
3. `first_seen` 有效且落在浏览器本地今天:
   - 继续返回 `刚刚` / `N分钟前` / `N小时前`。
4. `first_seen` 有效且落在浏览器本地昨天或更早:
   - 用浏览器本地日期与当前本地日期计算相差天数。
   - 可见文本返回 `relativeDateLabel(daysAgo, lang) + " " + HH:mm:ss`。
   - title 仍使用 `formatLocalTimestamp()` 的完整本地绝对时间和时区。

## 权衡
- 不把跨日记录显示成单纯 `昨天` / `N天前`,因为这些记录有具体 `first_seen`,保留本地时刻能避免最近记录里多条同日记录无法排序和辨认。
- 不用 UTC `day` 计算有效 `first_seen` 的相对日期,因为用户看到的是浏览器本地时区下的具体发生时刻;跨日判断应与本地日期一致。
- 不改变 `last_day`、`first_day`、图表日轴等 date-only 字段,避免破坏 UTC 统计语义。

## 风险
- 浏览器本地时区和服务端 UTC 日期可能不同。该风险由既有设计接受:具体时间戳按浏览器本地语义展示,date-only 统计字段按 UTC 语义展示。
- 如果浏览器无法提供时区名,hover title 会省略时区名;这是既有兜底行为。
- 回滚方式:恢复 `formatRecentRecordTime()` 的跨日分支为 `absolute`,并恢复 spec/wireframe 文案。
