# 提案：recent-record-relative-dates

## 背景
SKILLS 详情页的"最近记录"已经会把 `first_seen` 这种具体时间戳按浏览器本地时区显示,并在本地今天内显示相对时间。但历史数据或降级数据可能只有 date-only 的 `day`,当前会直接显示原始 `YYYY-MM-DD`。

用户希望最近记录里日期本身也能有相对表达,让今天、昨天和最近几天的数据更容易扫读。

## 提案
1. 扩展前端最近记录时间格式化函数:
   - `first_seen` 有效时保持现有规则不变。
   - `first_seen` 缺失但有 `day` 时,按 UTC date-only 语义显示相对日期:今天、昨天、N 天前。
   - 相对日期 hover title 保留原始 UTC 日期,避免把 date-only 值误当具体本地时刻。
2. `/skill/:name` 与 `/operator/:name` 的"最近记录"继续走同一个格式化函数,并传入服务端 `today` 作为 date-only 相对计算基准。
3. 增补单元测试覆盖 date-only 今天、昨天、N 天前、未来/无效日期兜底。

## 影响
- 受影响模块:
  - `frontend/src/lib/timeFormat.ts` 与 `timeFormat.test.ts`。
  - `frontend/src/views/SkillDetail.tsx`、`frontend/src/views/OperatorDetail.tsx`。
  - `openspec/specs/board/spec.md` 与相关 wireframe 注释。
- 不影响服务端 API、数据库结构、UTC 日统计口径、图表轴和后台清理台时间展示。
