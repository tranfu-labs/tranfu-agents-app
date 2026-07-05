# 设计：recent-record-standard-date-format

## 方案
在 `frontend/src/lib/timeFormat.ts` 内继续保留最近记录的单一入口 `formatRecentRecordTime(firstSeen, fallbackDay, lang, now, referenceDay)`。

实现拆成三类小函数:

- 具体时间戳:
  - 解析 `first_seen` 为 `Date`,所有日边界用浏览器本地日期判断。
  - 今天内走现有分钟/小时相对规则。
  - 昨天、2-6 天前、今年更早、跨年分别返回行业常见日期标签。
  - 可见文本只显示到分钟,hover title 继续用 `formatLocalTimestamp()` 显示完整秒级绝对时间和时区。
- date-only:
  - 解析 `YYYY-MM-DD` 时只按日历日期计算,不投射成浏览器本地时刻。
  - `referenceDay` 优先取服务端返回的 `today`,缺失时才用当前浏览器日期兜底。
  - 输出今天/昨天/星期/同年 MM-DD/跨年 YYYY-MM-DD,hover title 原样保留 `day`。
- 语言:
  - 中文星期使用 `周日` 至 `周六`。
  - 英文星期使用 `Sun` 至 `Sat`。
  - 数字日期使用稳定 ASCII 格式 `MM-DD` / `YYYY-MM-DD`,避免引入 locale 依赖导致快照不稳定。

`SkillDetail.tsx` 与 `OperatorDetail.tsx` 不需要新增逻辑,只继续传入 `data.today`。若实现时发现当前调用未传 `today`,则补齐调用参数。

## 测试设计
单元测试必须覆盖:

- 今天内:30 分钟前、刚刚。
- 昨天:显示 `昨天 HH:mm` / `yesterday HH:mm`。
- 2-6 天前:显示 `周X HH:mm` / `Mon HH:mm`。
- 同年旧日期:显示 `MM-DD HH:mm`。
- 跨年旧日期:显示 `YYYY-MM-DD HH:mm`。
- date-only fallback:今天、昨天、2-6 天、同年旧日期、跨年旧日期。
- 未来 `first_seen` 和无效 `day` 不做负相对或伪造时间。

AI 验证流程:

- `npm --prefix frontend run build`。
- 直接运行最近记录 formatter 单测(若现有 test runner 不稳定,至少通过 TypeScript 构建覆盖类型,并在后续实现里补可运行脚本)。
- 打开本地前端或构建预览,检查 `/skill/:name` 与 `/operator/:name` 最近记录首列在桌面/手机下不溢出、不呈现可点击行。

## 权衡
- 不使用 `Intl.RelativeTimeFormat` 直接生成全部文案:它对"周几 / MM-DD / 跨年"分层规则没有统一入口,且不同浏览器 locale 输出可能不稳定。
- 不把 7 天以上继续显示 `N天前`:大数字相对时间在运营表格里扫读成本高,同年日期和跨年日期更符合通用列表展示。
- 可见文本去掉秒,把秒保留在 hover title:列表更紧凑,同时不丢精确时间。

## 风险
- 不同团队对"近一周"是否用星期标签可能有偏好差异。该规则局限在最近记录展示层,回滚只需恢复 formatter 分支。
- date-only 不能表达具体时刻,必须继续避免本地时区换算;实现中需要保持这一边界,防止统计日被误解为 instant。
