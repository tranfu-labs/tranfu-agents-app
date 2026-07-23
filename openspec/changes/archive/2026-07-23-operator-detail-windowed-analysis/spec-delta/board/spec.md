# spec delta：board（操作员详情继承窗口并自适应分析）

> 归档时合入 `openspec/specs/board/spec.md`。

## 接口扩展

- `GET /api/operator/{name}[?w={today|this_week|last_week|7d|14d|30d|90d|custom}&wstart=&wend=&rt=&src=]`
  → 单操作员当前观察范围详情，至少包含 `today/window/applied_filters/analysis/skill_names/catalog`，并保留现有顶层
  `metrics/daily/skills/runtime/records` 兼容字段。
- 新增 `analysis` 无窗口参数时默认 `7d`；窗口、custom 和 `Asia/Shanghai` 统计日语义必须复用 `/api/skills` 的 `_skills_window` 规则。
- `analysis.metrics` 至少返回当前窗口 `sessions_window/skill_count/session_count/runtime_count/first_day/last_day` 与上一同长窗口 `previous_sessions`。
- `analysis.skills[]` 是当前窗口有 used 记录的完整 Skill 清单，每项至少返回
  `name/display_name/display_name_zh/source/sessions_window/previous_sessions/session_count/share/runtime_counts/last_day`。
- 现有顶层 `metrics` 继续表示既有近 7 天/近 30 天/累计及全局首末日语义；现有顶层
  `daily/skills/runtime/records` 继续表示既有全历史 used-only 集合、30 天排行排序、全量 runtime 与最近 50 条，
  不随新增 `w/wstart/wend/rt/src` 改义。新页面不得用这组兼容字段渲染窗口详情。

## 新增/修改规则（MUST）

1. 从 `/skills` 按人视角进入 `/operator/:name` 时，详情统计只继承 `w/wstart/wend/rt/src`。
   Skill 搜索词、Skill Top N、隐藏零使用、选中 Skill、总览排序和新增名单 scope 不得影响操作员详情 API 或可见统计。
2. 来源 `/skills` 的已识别 query 可通过独立的返回上下文随详情 URL 保存；它只能用于显式返回
   `/skills?view=operator...`，不得作为详情统计条件，不得接受任意站外或站内 path 跳转。
3. 操作员详情的标题、摘要、日序列、Skill 排行、runtime 分布、完整 Skill 明细和最近记录必须只使用
   `analysis` 中同一 `operator + mode=used + window + optional rt + optional src` 范围。`equipped` 不得进入
   `analysis` 任何字段；顶层兼容字段不参与新页面渲染。
4. 操作员全局有 used 记录但当前范围为空时返回 200、零值和空数组；只有全局不存在 used 记录时返回 404。
5. 单统计日详情用“Skill 使用构成”环形图，按当前窗口 used 记录取 Top 5 + 其他；中心显示总记录数。
   单日不得继续显示一根柱的伪趋势，也不得构造小时序列。
6. 多统计日详情用“每日使用 · 按 Skill”趋势，固定 Top 8 + 其他；长窗口只允许图表盒内部横滚并默认显示最新日期。
7. 主分析区旁的紧凑排行在单日显示 Top 5、多日显示 Top 8；每条真实 Skill 行必须显示来源并可下钻，
   长尾“其他 N 个”不可伪装成单一 Skill。
8. 操作员详情必须在主分析区下方提供当前窗口完整 Skill 明细，不受 Top 5/8 限制；默认按
   `sessions_window desc, previous_sessions desc, name asc`，整行鼠标与 Enter/Space 均可进入 `/skill/:name`。
9. 详情可见“次数”必须明确为会话×Skill 的 used 记录数、非真实调用次数；若同时展示会话数，字段须明确区分。
10. 页面独立请求带完整统计 query 的 `/api/operator/{name}`，不得等待 `/api/state` 或 `/api/skills` 首包；
    URL 统计范围变化后不得在新 URL 下继续把旧范围 payload 当作已完成结果。
11. `/operator/:name` 平板和手机按标题/摘要 → 自适应主分析 → runtime → 完整清单 → 最近记录的 DOM 顺序单列；
    手机排行和表格使用摘要行，页面根不得横向滚动。

## 可验证行为

- `/skills?view=operator&w=today&rt=codex&src=own&q=alice&topn=20&hz=1` 点操作员：
  详情 API 只收到 `w=today&rt=codex&src=own`；标题显示“今天”，显式返回仍恢复来源总览 query。
- 今天有 7 个 Skill：环形图为 Top 5 + 其他，紧凑排行为 Top 5，完整明细仍有 7 行。
- 近 30 天有 14 个 Skill：趋势为 Top 8 + 其他，紧凑排行为 Top 8，完整明细仍有 14 行。
- runtime 或来源筛选使当前范围为空：接口返回 200，页面显示带当前筛选上下文的空态；未知操作员返回 404。
- 同一操作员同一会话同一 Skill 重复上报、或同名 equipped 记录存在：个人详情 used 统计仍只计幂等后的 used 行。
- 无参数请求：顶层 `metrics/daily/skills/runtime/records` 与变更前逐项一致；新增
  `window.key=7d` 且 `analysis` 只含近 7 天。随后请求 `w=today&rt=codex&src=own` 时，顶层兼容字段不变，
  只有 `analysis` 按今天、Codex、own 的交集收窄。
