# 提案：recent-record-date-relative-time

## 背景
SKILLS 详情页和操作员详情页的"最近记录"已经支持两类时间优化:

- `first_seen` 有效时,浏览器本地今天内显示 `刚刚` / `N分钟前` / `N小时前`。
- `first_seen` 缺失、仅有 UTC date-only `day` 时,显示 `今天` / `昨天` / `N天前`。

当前缺口是:有效 `first_seen` 一旦落在浏览器本地昨天或更早,可见文本仍是完整绝对时间
`YYYY-MM-DD HH:mm:ss`。用户希望"日期方面也要有相对时间",跨日记录也应更易扫读。

## 提案
1. 调整最近记录专用格式化函数:
   - 浏览器本地今天内保持分钟/小时相对时间。
   - 浏览器本地昨天及更早改为 `相对日期 + HH:mm:ss`,例如中文 `昨天 23:00:00`、`5天前 09:18:55`,
     英文 `yesterday 23:00:00`、`5d ago 09:18:55`。
   - hover title 继续显示完整本地绝对时间与浏览器时区名。
2. 保持 date-only 回退规则不变:无 `first_seen` 时仍按服务端 UTC `today` 显示 `今天` / `昨天` / `N天前`,
   hover title 保留原始 `day`。
3. 为跨日 `first_seen` 补充单元测试,覆盖昨天、N 天前、未来时间不相对化等边界。

## 影响
- 受影响模块:
  - `frontend/src/lib/timeFormat.ts` 与 `frontend/src/lib/timeFormat.test.ts`。
  - `openspec/specs/board/spec.md` 与相关 wireframe 注释。
  - `AGENTS.md`、`docs/architecture/module-map.md` 中的前端展示规则。
- 不影响服务端 API、SQLite schema、UTC 日统计口径、SKILLS 图表日轴或 date-only 字段语义。
