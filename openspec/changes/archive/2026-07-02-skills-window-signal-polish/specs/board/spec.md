# spec delta:board(本变更新增/修改的规则)

> 合入后并入 `openspec/specs/board/spec.md`。本 delta 只覆盖 SKILLS 总览页的时间窗、操作员排行、问题线索和环比入口。

## 修改规则(MODIFIED)
- `/api/skills.operator_table` 不再固定以 30 天作为默认排行依据。每行须提供当前 `window.start..window.end` 的
  `sessions_window`,以及上一同长窗口的 `previous_sessions`;默认排序为
  `sessions_window desc, sessions_total desc, operator asc`。
- `/api/skills.operator_table` 仍保留 `sessions_7d`、`sessions_30d`、`sessions_total`、`skill_count`、
  `session_count` 等兼容字段,但 `/skills` 按人视角的主排行必须优先使用当前窗口字段。
- `/api/skills` 可接收可选 `rt`、`src` 查询参数;这两个参数只影响 `operator_table` / `operator_daily`
  的窗口化聚合,用于定义按人视角的证据范围。`skill` 搜索词、Top N、隐藏 0 使用不得进入 `/api/skills`
  overview 请求,也不得影响操作员排行。
- `/api/skills.operator_table` 须提供当前窗口内且已应用 `rt/src` 的 `window_runtime_counts` 与
  `window_source_counts`。当 `rt` 与 `src` 同时存在时,计数必须是二者交集,不得用两个独立计数近似。
- SKILLS 总览的 `cmp` URL 参数保留向下兼容,但不再驱动可见 UI;previous-window 变化默认始终展示,无 previous 数据时显示空态。
- SKILLS 总览中所有可见 `W` 文案须改为当前时间窗 i18n label 派生:
  `last_week` → 「上周变化」/ `Last week changes`;
  `this_week` → 「本周变化」/ `This week changes`;
  `7d` → 「近 7 天变化」/ `Last 7 days changes`;
  `30d` → 「近 30 天变化」/ `Last 30 days changes`;
  `custom` → 「自定义周期变化」/ `Custom range changes`。
- 问题线索卡片不得在首屏直接渲染具体 skill 名名单;具体 records / items / names 只能出现在待处理线索、证据页或详情抽屉中。
- 问题线索卡片不得使用 KPI 评分语气、红绿箭头、达成率或庆祝式增长文案;其职责是提示"哪里断了、下一步看哪份名单"。

## 新增规则(MUST)
- `/skills` 工具栏不得显示环比开关;previous-window delta 是默认上下文,用户没有关闭入口。
- 从按 Skill 视角切到按人视角时,不得把旧 skill 搜索词带入操作员排行。按人视角内的搜索框只作为 operator 本地搜索。
- 证据入口 icon 在 KPI 卡、问题线索和排行行内须与同一行文本视觉居中;不得贴近行上沿。
- 证据页继续保留明细名单;问题线索卡的去名单化不得影响 `/skills/evidence` payload 与 evidence 下钻能力。

## 可验证行为(新增)
- 造数:operator A 最近 7 天 3 条 used、operator B 最近 30 天 10 条但最近 7 天 1 条 →
  `/api/skills?w=7d` 的 `operator_table` 中 A 排在 B 前,且 A 的 `sessions_window=3`。
- 同一造数查 `/api/skills?w=30d` → 排序可随 30 天窗口变化。
- `/api/skills?w=7d&rt=codex&src=own` → `operator_table.sessions_window` 只统计当前窗口内 codex + own 交集。
- `/skills?view=operator&w=7d&rt=codex&src=own` → 操作员排行使用当前窗口内 codex + own 计数;改变 skill Top N 或隐藏 0 使用不改变操作员排行。
- `/skills?view=skill&w=last_week` 中文首屏显示「上周变化」,英文首屏显示 `Last week changes`,不出现裸 `过去 W 变化`。
- `/skills` 工具栏无环比开关;KPI 卡仍显示 previous-window delta 或空态。
- `/skills` 问题线索卡不出现 `openspec-driven-development`、`figma-implement-d`、`coolify-deploy` 等具体 skill 名;点击 icon 仍进入对应 evidence 明细。
- 375px 手机宽度下,问题线索的跳转 icon 与文字行垂直居中,页面根无横向滚动。
