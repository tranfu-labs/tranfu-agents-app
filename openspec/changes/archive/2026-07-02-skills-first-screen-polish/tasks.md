# 任务：skills-first-screen-polish

- [x] 1. 补齐 `/skills` 首屏 i18n key。
      更新 `frontend/src/lib/i18n.ts`，覆盖时间窗口、KPI、问题线索、待处理线索、动作 tooltip、移动筛选摘要。
- [x] 2. 收口展示 helper。
      更新 `frontend/src/lib/skillsPresentation.ts`，新增 `windowDisplayLabel`，让 `mobileFilterSummary` 支持 `t`；
      更新 `frontend/src/lib/skillsPresentation.test.ts` 覆盖中英文输出。
- [x] 3. 更新 `/skills` 控制条。
      `frontend/src/views/Skills.tsx` 的窗口选项、custom 起止、环比、隐藏 0 使用、移动摘要改走 i18n；
      搜索 field 增加稳定 class/结构。
- [x] 4. 更新 KPI 卡片结构。
      `frontend/src/components/skills/KpiStrip.tsx` 接收 `t`，把核心数值和证据 icon 放到同一行；
      title、短结论、环比/快照全部走 i18n。
- [x] 5. 更新首屏线索组件文案。
      `HealthBar.tsx` 与 `GovernanceTodo.tsx` 接收 `t`，首屏可见文案和 aria/title 不再硬编码中文。
- [x] 6. 更新响应式 CSS。
      `frontend/src/styles.css` 调整搜索 field nowrap、KPI 8/4×2/2×4、KPI top row、手机顺序和无效旧选择器。
- [x] 7. 验证。
      跑 `npm --prefix frontend run test:unit`、`npm --prefix frontend run build`；
      用 1440×900、768×1024、375×812 截图检查 `/skills?view=skill&w=7d&topn=8` 中英文、首屏密度和无根横滚。
