# 设计：operator-detail-windowed-analysis

字符线框见 `wireframes.md`，行为增量见 `spec-delta/board/spec.md`。

## 方案

### 1. 把详情统计范围与返回上下文分开

新增不依赖 React/DOM 的操作员详情 query 纯模块，集中负责三件事：

1. 从 SKILLS 总览 query 中白名单提取 `w/wstart/wend/rt/src`，生成详情页的统计 query。
2. 生成 `/api/operator/{name}` 请求 query；自定义窗口只在 `w=custom` 时发送完整的 `wstart/wend`。
3. 把来源页已识别的 SKILLS query 编码到单独的 `from` 参数中；显式返回时恢复 `/skills?view=operator...`，直接访问详情而没有 `from` 时，则只用当前统计范围生成最小返回地址。

`from` 只表达 `/skills` 的 query，不接收任意 path 或 origin，避免把返回入口变成开放跳转。详情统计、标题和 API 请求永远不读取 `from` 内的搜索词、Top N、隐藏零使用或选中 Skill。

从 `/skills` 打开详情使用 history push；总览内部筛选仍使用 replace。刷新、复制详情链接和浏览器前进后退都由 URL 恢复同一统计范围。

### 2. 扩展操作员详情读模型

`GET /api/operator/{name}` 新增：

```text
?w={today|this_week|last_week|7d|14d|30d|90d|custom}
&wstart=<unix>&wend=<unix>&rt=<runtime>&src=<source>
```

服务端复用 `_skills_window`、catalog 来源映射和既有 runtime/source 匹配规则，不在详情端复制另一套窗口语义。操作员详情前端即使 URL 省略 `w`，也会先解析为 `7d` 并显式请求 `w=7d`；API 无参数调用则同时保留旧顶层语义，并让新增的 `analysis` 默认使用 `7d`。

兼容边界按字段明确如下：

- 现有顶层 `operator/today/skill_names/catalog` 原样保留。
- 现有顶层 `metrics.sessions_7d/sessions_30d/sessions_total/skill_count/session_count/first_day/last_day` 保留当前全局 used-only 语义；`skill_count/session_count/first_day/last_day` 不因窗口或 `rt/src` 改义。
- 现有顶层 `daily[]/skills[]/runtime[]/records[]` 保留当前全历史 used-only 语义、字段、排序和最近 50 条上限；即使请求带新参数，这组兼容字段也不被过滤。
- 新增顶层 `window` 与 `applied_filters`，以及新增 `analysis` 子对象。只有 `analysis` 承载新页面的窗口事实：`metrics/daily/skills/runtime/records` 全部服从 `operator + mode=used + window + optional rt + optional src`。
- 新增 query 与 `analysis` 是加法契约；本 change 不重定义任何既有顶层字段。新前端只消费 `analysis` 渲染窗口详情，不能拿兼容字段拼出另一套范围。

`analysis` 至少包含：

- `metrics`：`sessions_window`、`previous_sessions`、当前窗口 `skill_count/session_count/runtime_count`、当前窗口首日和末日。
- `daily[]`：只含当前窗口、当前观察范围的 used-only 日×Skill聚合。
- `skills[]`：当前窗口内有使用的完整 Skill 清单；每项含 `sessions_window/previous_sessions/session_count/share/runtime_counts/last_day`。
- `runtime[]`：当前窗口、当前观察范围的 runtime 分布。
- `records[]`：当前窗口、当前观察范围最近 50 条 used 记录。

`analysis` 的所有块使用同一个 SQL 约束集合：规范化后的 operator、`mode='used'`、当前/上期日期边界、可选 runtime、可选 catalog 来源。`equipped` 不进入任何个人统计。顶层兼容字段继续走既有无筛选查询，明确不作为窗口页面的数据源。

操作员只要在全局存在 used 记录，所选范围即使为空也返回 200 和零值/空数组；只有全局不存在 used 记录时才返回 404。这样复制窄筛选链接不会把“当前范围为空”误报为“操作员不存在”。

### 3. 自适应主分析区

前端以服务端 `window.days` 判定图形：

- 单统计日（包括 `today` 和一天 custom）：左侧显示环形构成，按 `sessions_window` 取 Top 5，其余合并为“其他”；中心显示当前窗口使用记录总数。右侧显示可下钻的紧凑 Top 5，每条真实 Skill 行明确显示来源、记录数、会话数和占比；长尾只显示“其他 N 个”，不伪装成可下钻 Skill。
- 多统计日：左侧显示当前窗口逐日按 Skill 堆叠趋势，固定 Top 8 + 其他；右侧显示可下钻的紧凑 Top 8，每条真实 Skill 行同样明确显示来源、记录数、会话数和占比。
- 当前范围总量为零：主分析区显示带当前窗口和筛选摘要的 Empty，不渲染空环或空坐标轴。

Top 5/Top 8 是操作员详情的固定概览阈值，不读取 SKILLS 总览 `topn`。单日环形只表达构成，不伪造小时趋势；多日趋势继续使用服务端 date-only 统计日。

环形模型与排行截断/长尾合并放入纯函数，复用现有 Skill display name、颜色与 donut 扇区几何。图例/排行提供稳定的键盘入口，环形扇区不是获取名称与精确值的唯一方式。

### 4. 页面信息架构

页面顺序调整为：

1. 返回入口与“操作员 · 当前时间窗”标题；runtime/source 以人话 chip 显示。
2. 当前窗口摘要：使用记录、使用 Skill、会话、runtime；口径说明继续明确“会话×Skill used 记录，非调用次数”。
3. 自适应主分析区：单日环形或多日趋势 + 紧凑排行。
4. runtime 分布。
5. “完整 Skill 明细 · N”：展示当前窗口全部 Skill，默认按 `sessions_window desc, previous_sessions desc, name asc`；列为 Skill、来源、当前窗口、上期、占比、会话、runtime、最近。整行 Enter/Space 可下钻 `/skill/:name`。
6. 最近记录：继续不可点，时间按既有浏览器本地时区规则展示。

标题、当前窗口列名、单日/多日图标题和空态文案全部从同一窗口 i18n label 派生，不直接显示 `w=today`、`window_start` 等内部值。

### 5. 响应式与加载边界

- 桌面：主分析区左右并列，单日为近等宽；多日趋势略宽于紧凑排行。完整清单独占整行。
- 平板和手机：主分析区、runtime、完整清单、最近记录按真实 DOM 顺序单列；手机排行和两张表使用摘要行。
- 30/90 天或长 custom 只允许趋势 `.chart-box` 内部横滚并默认定位最新日期；页面根不得横滚。
- 详情 URL 的统计范围变化时，不在新 URL 下继续展示旧范围 payload；显示数据区 skeleton/刷新态，直到同 URL 请求完成。
- 页面仍独立请求 `/api/operator/{name}`，不得等待全局 `/api/state` 或 `/api/skills` 首包。

## 测试

### 单元测试

- query 纯模块只把 `w/wstart/wend/rt/src` 放进统计 URL；`q/topn/hz/sel/sort/dir/scope` 只存在于编码后的返回上下文。
- custom 只有两端完整时才生成 custom API query；直接访问详情能生成最小 `/skills?view=operator...` 返回地址。
- 单日模型按 Top 5 + 其他聚合，多日排行按 Top 8 截断；总量、占比和长尾数量保持守恒。
- 单日/多日/空态判定覆盖一天 custom、两天 custom 和零记录。

### 服务端测试

- `w=today` 的 `analysis.metrics/daily/skills/runtime/records` 只返回今天，上期值取昨天；顶层兼容字段保持原语义。
- `w=7d&rt=codex&src=own` 对所有返回块应用同一个交集，其他 runtime/source 不泄漏。
- equipped-only 记录仍不计入任何字段。
- 操作员全局存在但当前范围为空时返回 200 零值；全局无 used 记录仍返回 404。
- 非法预设窗口返回 400；有效 custom 沿用 `_skills_window` 的上海统计日语义。
- Skill 明细排序、share 与 `sessions_window` 总和一致，最近记录仍最多 50 条。
- `test_operator_detail_no_query_preserves_legacy_contract`：造 31 天前、5 天前和今天的 used 数据后，无参数请求逐项断言顶层 `metrics/daily/skills/runtime/records` 与变更前语义相同（含 31 天前记录、30 天排行和最近 50 条规则）；同时断言新增 `window.key=7d`、`analysis` 仅含近 7 天数据。带 `w=today&rt=codex&src=own` 再请求时，顶层兼容字段仍与无参数响应一致，只有 `analysis` 收窄。

### 浏览器验证

- 从 `/skills?view=operator&w=today&rt=codex&src=own...` 下钻，标题显示“今天”，所有数据与总览该行范围一致；显式返回恢复来源页视角和筛选。
- 今天显示环形 Top 5 + 其他和紧凑 Top 5；紧凑排行每条真实 Skill 行可见来源，不显示单柱趋势。
- 7d/14d/30d/90d/custom 显示多日趋势和紧凑 Top 8；紧凑排行每条真实 Skill 行可见来源，30d/90d 只在图内滚动。
- 完整 Skill 清单不受 Top 5/8 截断，整行鼠标和 Enter/Space 均可进入 Skill 详情。
- 当前范围为空、API 失败、操作员 404 三种状态文案可区分。
- 中英文、system/light/dark、1440/768/375 三档视口无根级横滚或文字/数值重叠。

## 权衡

- 选择环形图只服务单日构成，而不替代排行：构成图回答“今天主要分布在哪些 Skill”，排行继续提供精确值和下钻。
- 选择固定 Top 5/8，而不继承总览 Top N：个人详情需要稳定、紧凑的管理概览；完整清单已经承担查账职责。
- 选择 URL `from` 保存返回上下文，而不使用 localStorage、sessionStorage 或仅依赖 history：直接刷新和复制链接后仍能恢复显式返回目标，同时不扩大前端持久化例外。
- 不给今天伪造小时序列：服务端只有日级 Skill 使用事实，构造小时趋势会制造不存在的精度。

## 风险

- 新增 query 后，某些调用方可能仍依赖旧固定字段；因此旧顶层字段保持全历史/7d/30d/累计原语义，新前端只消费新增 `analysis`。代价是响应在过渡期同时携带兼容数据与窗口数据，但避免静默破坏现有调用方。
- catalog 拉取失败会影响来源过滤名称映射；沿用现有 catalog 缓存/降级，不在本 change 新建来源体系。
- `from` 可能变长；只保存已识别的 SKILLS query，并拒绝任意路径/域名，避免开放跳转和无界膨胀。
- 环形小扇区难以直接命中；精确读数和键盘下钻始终由紧凑排行/图例承载。
