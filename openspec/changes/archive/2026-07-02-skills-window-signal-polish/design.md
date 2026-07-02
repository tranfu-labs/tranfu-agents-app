# 设计:skills-window-signal-polish

> 目标是修正 SKILLS 总览页的观察窗口语义和首屏线索表达。它不是重新设计 SKILLS 页,而是在现有 `skills-stats-page`、`skills-operator-view`、`skills-view-ux-polish` 基础上收敛几个已确认的运营判断问题。

## 锁定口径
- **操作员排行的观察范围**:继承 `w/days` 时间窗,并继承 `runtime/source`。不继承 skill 搜索词、Top N、隐藏 0 使用。
- **搜索语义**:从按 Skill 切到按人视角时,清空原 skill 搜索词,避免旧 `q` 把操作员榜误筛掉;按人视角内新输入的 `q` 仍作为 operator 本地搜索。
- **previous-window**:默认始终展示。没有 previous 数据时显示既有 `—` / 快照空态,不提供关闭入口。
- **问题线索**:首屏只讲结论和下一步证据入口,不露具体 skill 名。具体 names / records 继续在 `/skills/evidence` 或待处理线索中出现。
- **语气**:问题线索不是 KPI 评分,不使用红绿箭头、达成率、庆祝增长等表达。

## 实现方案

### 1. 后端补窗口化操作员排行字段,并让 operator 聚合接收 rt/src
修改 `server/routes/board.py::skills_overview`:

- `GET /api/skills` 新增可选查询参数 `rt`、`src`。它们只用于 `operator_table` / `operator_daily` 的窗口化聚合,不影响 skill 视角的 `daily` / `table` / `governance` / `period_comparison`。
- `src` 过滤用 `_skill_source(skill,catalog_by)` 在 Python 聚合阶段收口,确保 `runtime + source` 组合筛选是交集而不是两个独立计数的近似值。
- `operator_table[]` 新增:
  - `sessions_window`:当前 `window.start..window.end` 内 used 记录数。
  - `previous_sessions`:上一同长窗口 used 记录数。
  - `window_runtime_counts`:当前窗口且已应用 `rt/src` 后的 runtime 计数。
  - `window_source_counts`:当前窗口且已应用 `rt/src` 后的 source 计数。
  - `window_skill_count`:当前窗口内 distinct skill 数。
- 保留既有 `sessions_7d` / `sessions_30d` / `sessions_total` / `skill_count` / `session_count` / `runtime_counts` / `source_counts`,用于历史列和向后兼容。
- `operator_table` 默认排序改为 `sessions_window desc, sessions_total desc, operator asc`。
- `operator_daily` 同样应用 `rt/src`,继续作为趋势图数据源。

这样 `w=last_week`、`w=30d`、`w=90d` 进入时,后端默认顺序和主计数都跟当前窗口一致;`rt=codex&src=own` 时 operator 排行也是真正的交集口径。

### 2. 前端请求与操作员排行只继承 runtime/source 证据范围
修改 `frontend/src/lib/skillsWindow.ts` 与 `frontend/src/views/Skills.tsx`:

- `skillsWindowQuery(params)` 输出 `w/days/wstart/wend/rt/src`,不输出 `q/topn/hz/cmp/sel`。
- `setView('operator')` 时清空 `q` 和 `sel`,并把默认 sort 改为 `sessions_window`。
- `OperatorTable` 表头新增或替换主数值列为当前窗口列,列名使用 `windowDisplayLabel(...)` 派生,例如「近 7 天」/ `Last 7 days`。
- `operatorRows` 过滤拆成两层:
  - 观察范围过滤:由服务端 `rt/src` 聚合完成,前端不再用 skill 视角的 local source/runtime 近似过滤 operator 数据。
  - operator 本地搜索:仅在 `view=operator` 且用户输入后按 operator 名过滤;不把 skill 视角遗留搜索带过来。
- Top N 和隐藏 0 使用不参与 operatorRows;它们只影响 skill 排行局部。

### 3. 时间窗 label 派生所有 `W` 文案
修改 `frontend/src/lib/skillsPresentation.ts` 与 `frontend/src/lib/i18n.ts`:

- 保留 `windowDisplayLabel(key,t)` 作为下拉和摘要 label。
- 新增 `windowChangeLabel(key,t)`:返回 `windowDisplayLabel + changesSuffix`,如:
  - zh: `上周变化`、`本周变化`、`近 7 天变化`、`近 30 天变化`、`自定义周期变化`
  - en: `Last week changes`、`This week changes`、`Last 7 days changes`
- 新增 `windowInLabel(key,t)` 或等价 helper,替换句内 `W 内` / `0 in W` / `W 触发` 这类文案。
- 覆盖位置:
  - `KpiStrip` 标题。
  - `GovernanceTodo` 的「装了 W 内没用」。
  - `FunnelSection` 的「W 用」。
  - `SkillsDetailTable` / `SkillDrawer` 中可见的 `W 内`、`W′ 上期`、`W 触发`。
  - evidence summary 中 `windowKey` 直出的 `W`。

### 4. 删除环比开关,默认展示 comparison
修改 `frontend/src/views/Skills.tsx` 与 `KpiStrip.tsx`:

- 从 toolbar 删除 `compareToggle` checkbox。
- `KpiStrip` 移除 `showComparison` prop 和 `comparisonOff` 分支;`Delta` 始终按 current/previous 渲染。
- `skillQuery.ts` 可保留 `cmp` parser 作为旧 URL no-op 兼容,但 UI 不再读它;后续 spec 写明 `cmp` 保留但不驱动界面。

### 5. 问题线索改成结论型,不露具体 names
修改 `frontend/src/components/skills/HealthBar.tsx`:

- skill 视角 5 项仍是:未收录占比、装了没用比例、公司库覆盖率、Top3 集中度、平均 skill/会。
- 每项结构保留 `title + value + action line + evidence icon`,但 action line 改为通用结论:
  - 未收录占比:`看未收录 used 名单`
  - 装了没用比例:`看已装未用名单`
  - 公司库覆盖率:`看有证据的公司库 skill`
  - Top3 集中度:`看集中使用分布`
  - 平均 skill/会:`看会话使用分布`
- 不再调用 `compactNameList(...)` 生成首屏 names。
- 去掉 `classifySkillHealth(...)` 直接映射到 `good/warn/bad` 的表达,改成统一中性 `signal` class;数值只是事实,不是评分。
- operator 视角的 usage signals 同步采用中性信号和结论型文案。

### 6. 证据 icon 居中
修改 `frontend/src/styles.css`:

- `.skills-health .evidence-icon-link` 设置 `margin-top:0; align-self:center; flex:none;`.
- `.skills-health span` 保持 `align-items:center`,必要时给 line-height 稳定值。
- 保持 KPI 顶部 `.skills-kpi-top .evidence-icon-link{margin-top:0}` 现状。
- `RankBars` 内 `.rank-evidence` 保持 22px 尺寸,同样无 `margin-top`。

## 测试方案

### 后端单测
更新 `tests/test_skills_stats_page.py` 或新增同域测试:

- 造 operator A 在当前 `7d` 窗口内 3 条、operator B 在 30 天历史内更多但当前窗口 1 条:
  `/api/skills?w=7d` 的 `operator_table[0].operator == A`,且 `sessions_window == 3`。
- 同一数据查 `/api/skills?w=30d` 时排序随 30 天窗口变化。
- 造 previous window 数据,断言 `previous_sessions` 正确。
- 造 runtime/source 混合数据,断言 `window_runtime_counts` / `window_source_counts` 只统计当前窗口。

### 前端单测
更新 `frontend/src/lib/skillsDashboard.test.ts`、`skillsPresentation.test.ts`、`skillsCopy.test.ts`:

- `windowChangeLabel('last_week')` 中英文分别为「上周变化」/ `Last week changes`。
- `windowInLabel('7d')` 不返回裸 `W`。
- 源码检查不再出现 `compareToggle` UI 和 `comparisonOff` 可见文案。
- HealthBar 源码不再把 `compactNameList` 用于问题线索首屏。

### AI / 手动验证
- 1440x900 打开 `/skills?view=skill&w=last_week`:标题显示「上周变化」;首屏无 `过去 W 变化`。
- 1440x900 打开英文模式 `/skills?view=skill&w=7d`:标题显示 `Last 7 days changes`,无中文和裸 `W`。
- 1440x900 打开 `/skills?view=operator&w=7d&rt=codex&src=own`:操作员排行按窗口内 codex + own 使用排序,不受 skill Top N / 隐藏 0 影响。
- 问题线索卡不出现 `figma-implement-d`、`coolify-deploy` 等具体 skill 名;点击 icon 仍进入对应 evidence。
- toolbar 中没有环比开关;KPI 卡仍显示 delta 或空态。
- 375x812 手机 `/skills?w=7d`:控制摘要和首屏问题线索不横向溢出,证据 icon 垂直居中。

## 风险与权衡
- **保留 `cmp` no-op**:避免旧链接报错;代价是 URL 里手写 `cmp=0` 不再改变界面。该行为符合"不提供关闭入口"。
- **operator 本地搜索与 skill 搜索隔离**:切视角清空 `q` 会丢掉用户刚输入的 skill 搜索,但这是为了避免 skill 搜索污染 operator 观察范围。
- **只把 runtime/source 下沉到 operator 聚合**:全页 skill 视角仍沿用现有前端本地筛选,避免本次扩大到所有 KPI / governance 的口径重算;operator 排行单独需要交集过滤,所以在后端收口。
