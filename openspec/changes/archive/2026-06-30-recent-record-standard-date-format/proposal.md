# 提案：recent-record-standard-date-format

## 背景
SKILLS 详情页与操作员详情页的"最近记录"已经把 `first_seen` 按浏览器本地时区展示,并支持:

- 本地今天内显示 `刚刚` / `N分钟前` / `N小时前`。
- 本地昨天及更早显示 `昨天 HH:mm:ss` / `N天前 HH:mm:ss`。
- 缺失 `first_seen` 时按服务端统计日 `day` 显示 `今天` / `昨天` / `N天前`。

用户希望继续优化最近记录时间,日期展示采用业界通用方法。当前统一 `N天前` 的方式在记录稍旧时不够稳定:例如 `28天前 09:18:55` 不如 `06-02 09:18` 易扫读,也不适合跨年历史记录。

## 提案
1. 调整最近记录专用格式化函数,将有效 `first_seen` 的可见文本改成分层规则:
   - 浏览器本地今天内:保持克制相对时间,中文 `刚刚` / `N分钟前` / `N小时前`,英文 `just now` / `Nm ago` / `Nh ago`。
   - 浏览器本地昨天:中文 `昨天 HH:mm`,英文 `yesterday HH:mm`。
   - 浏览器本地 2-6 天前:中文 `周一 HH:mm` 等星期标签,英文 `Mon HH:mm` 等星期标签。
   - 浏览器本地今年更早: `MM-DD HH:mm`。
   - 非浏览器本地今年: `YYYY-MM-DD HH:mm`。
   - hover title 继续保留完整本地绝对时间到秒,并附浏览器时区名。
2. 调整缺失 `first_seen` 的 date-only 回退,按服务端返回的 `today` 作为统计日基准显示:
   - `day=today`:中文 `今天`,英文 `today`。
   - 昨天:中文 `昨天`,英文 `yesterday`。
   - 2-6 天前:中文 `周一` 等星期标签,英文 `Mon` 等星期标签。
   - 同统计年更早: `MM-DD`。
   - 跨统计年: `YYYY-MM-DD`。
   - hover title 保留原始 `day`,不得把 date-only 补造成具体时刻。
3. `/skill/:name` 与 `/operator/:name` 继续共用同一个 formatter,不新增页面级分支逻辑。
4. 补充单元测试覆盖昨天、近一周、同年旧日期、跨年、date-only fallback、未来/无效兜底等边界。

## 影响
- 受影响模块:
  - `frontend/src/lib/timeFormat.ts` 与 `frontend/src/lib/timeFormat.test.ts`。
  - `openspec/specs/board/spec.md` 与相关 wireframe 注释。
  - `AGENTS.md`、`docs/architecture/module-map.md` 中的前端展示规则。
- 不影响服务端 API、SQLite schema、SKILLS 聚合口径、`Asia/Shanghai` 日级统计窗口或具体 UTC instant 存储规则。
