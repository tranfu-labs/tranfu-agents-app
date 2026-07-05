# 任务：optimize-recent-record-time

- [x] 1. 新增前端本地时间格式化纯函数,覆盖绝对时间、最近记录相对显示与 hover title。
- [x] 2. 新增 `timeFormat` 单元测试,覆盖本地今天、昨天及以前、跨 UTC/本地日边界、缺 `first_seen` 回退。
- [x] 3. 修改 `SkillDetail.tsx` 与 `OperatorDetail.tsx` 的最近记录首列,按浏览器本地时区显示并加 title。
- [x] 4. 修改 `Admin.tsx` 中同类具体 ISO 时间戳展示,改为浏览器本地绝对时间。
- [x] 5. 更新 `openspec` spec-delta 与 `wireframes.md`,明确浏览器时区展示规则与页面可见变化。
- [x] 6. 自检:运行前端时间格式单测与 `npm --prefix frontend run build`;必要时用浏览器检查 `/skill/:name`、`/operator/:name`、`/admin`。
