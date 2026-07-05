# 设计：recent-record-relative-dates

## 方案
在 `frontend/src/lib/timeFormat.ts` 内把最近记录时间格式化拆成两层:

1. `first_seen` 有效:
   - 继续使用现有具体时间戳规则。
   - 浏览器本地今天内显示 `刚刚` / `N分钟前` / `N小时前` 或英文等价。
   - 昨天及更早显示本地绝对时间。
2. `first_seen` 缺失,但 `day` 是合法 `YYYY-MM-DD`:
   - 不用 `new Date(day)` 做本地时区换算。
   - 按 UTC date-only 计算它与服务端 `today` 的日差。
   - 日差 0 显示 `今天` / `today`;日差 1 显示 `昨天` / `yesterday`;日差 2 及以上显示 `N天前` / `Nd ago`。
   - 未来日期或非法日期保持原始 day。
   - title 保持原始 day,表达这是 date-only 数据,不是具体本地时刻。

`formatRecentRecordTime` 增加可选 `referenceDay` 参数。详情页传 `data.today`;测试中显式传入固定日期,避免依赖运行日。

## 权衡
- 不把 `day` 解析成浏览器本地日期,保留它作为服务端 UTC 日的语义。这样不会在东八区凌晨把 UTC 昨天误显示成本地昨天/今天。
- 只改最近记录的 date-only fallback。Skill 排行、指标卡里的 `last_day` / `first_day` 仍是 UTC date-only 统计字段,本轮不扩散到全站日期列。
- 相对日期不额外加"周前/月前",避免历史数据被过度概括;最近记录最多 50 条,`N天前` 足够清楚。

## 测试用例
- `first_seen` 本地今天内仍显示分钟级相对时间。
- `first_seen` 本地昨天仍显示本地绝对时间。
- 缺 `first_seen`, `day=today` 显示 `今天` / `today`。
- 缺 `first_seen`, `day=yesterday` 显示 `昨天` / `yesterday`。
- 缺 `first_seen`, `day=today-5` 显示 `5天前` / `5d ago`。
- 缺 `first_seen`, `day` 是未来或非法值时显示原始文本。

## 风险
- 浏览器与服务端日期不同步时,date-only 相对文案可能偏一天。详情页改为传入服务端 `today` 后可降低该风险。
- 旧数据只有 `day` 时仍没有具体小时分钟,title 不补造时间戳。
