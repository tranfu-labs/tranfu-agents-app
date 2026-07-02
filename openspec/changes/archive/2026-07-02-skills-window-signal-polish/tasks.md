# 任务:skills-window-signal-polish

- [x] 1. `server/routes/board.py`:窗口化 `operator_table`,并让 operator 聚合接收 `rt/src`。
      增加 `sessions_window`、`previous_sessions`、`window_runtime_counts`、`window_source_counts`、`window_skill_count`;
      `operator_table` / `operator_daily` 应用 `rt/src` 交集过滤;默认排序改为当前窗口优先,保留既有 7/30/累计字段。
- [x] 2. `tests/`:补后端聚合测试。
      覆盖不同 `w` 下 operator 排序变化、previous window、当前窗口 runtime/source counts、equipped/空 operator 仍不计入。
- [x] 3. `frontend/src/lib/skillsWindow.ts` + `frontend/src/views/Skills.tsx`:移除环比开关并修正操作员排行口径。
      `skillsWindowQuery` 只带 `w/days/wstart/wend/rt/src`;
      切到按人视角时清空 skill 搜索与选中 skill;OperatorTable 主列/默认排序改为 `sessions_window`;
      operator 观察范围只继承 runtime/source,不继承 skill Top N/hide zero。
- [x] 4. `frontend/src/lib/skillsPresentation.ts` + `i18n.ts`:新增时间窗变化/句内 helper。
      替换首屏和抽屉/表格中裸 `W` 文案,覆盖中英文。
- [x] 5. `frontend/src/components/skills/KpiStrip.tsx`:默认始终展示 previous-window delta。
      移除 `showComparison` / `comparisonOff` 可见分支,标题改为当前时间窗变化 label。
- [x] 6. `frontend/src/components/skills/HealthBar.tsx` + `styles.css`:问题线索改成中性结论型。
      不露具体 skill 名;不使用 red/green KPI 口吻;证据 icon 在问题线索、排行行中视觉居中。
- [x] 7. `frontend` 单元测试。
      覆盖时间窗 label helper、无裸 W/compare toggle 文案、HealthBar 不用 names 拼首屏问题线索。
- [x] 8. AI / 手动验证。
      `npm --prefix frontend run test:unit`;`npm --prefix frontend run build`;
      桌面/手机分别查看 `/skills?view=skill&w=last_week`、`/skills?view=operator&w=7d&rt=codex&src=own`、英文模式。
