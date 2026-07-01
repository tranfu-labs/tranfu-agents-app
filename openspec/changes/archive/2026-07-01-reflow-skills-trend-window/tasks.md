# 任务:reflow-skills-trend-window

- [x] 1. 默认时间窗口改为 7d。
      `frontend/src/lib/skillQuery.ts` 将 `win` default 改为 7;
      `frontend/src/lib/skillsWindow.ts` 将无参、非法参数、无效 custom fallback 改为 `7d`;
      保留旧 `win=7/30/90` 映射能力。

- [x] 2. 重排 `/skills` 主分析区。
      `frontend/src/views/Skills.tsx` 移除全宽趋势图 section;
      在排行 frame 内部、`RankBars` / `OperatorTable` 之后追加趋势图区;
      `GovernanceTodo` 保持右列;平板/手机自然单列为排行 -> 趋势 -> 治理待办。

- [x] 3. 趋势图几何与滚动行为。
      `frontend/src/components/Charts.tsx` 将 `StackedSkillChart` 改为固定单日槽宽;
      1-7 天右对齐且不拉伸;8-90 天内部横滚并在窗口/右端日期/视角变化时默认滚到最右;
      保留现有浮窗、今日进行中、TopN+其它、空态与 selectedSegment 行为。

- [x] 4. CSS 响应式与滚动边界。
      `frontend/src/styles.css` 增加排行 frame 内部趋势图区样式;
      图表 SVG 不再被通用 `width:100%` 拉伸短窗口;
      确认 `>1080px`、`601px-1080px`、`<=600px` 下页面根无横向滚动。

- [x] 5. 单元测试。
      更新 `frontend/src/lib/skillsDashboard.test.ts` 或新增测试:
      默认窗口为 `7d`;旧 `win` 兼容;无效 custom fallback 为 `7d`;
      图表布局 helper 覆盖 1/7/30/90 天的宽度、右对齐和滚到最右决策。

- [x] 6. AI/视觉验证。
      运行 `npm --prefix frontend run test:unit` 和 `npm --prefix frontend run build`;
      本地打开 `/skills`，用 1440、768、375 视口检查 `7d/30d/90d`;
      验证 7d 右对齐不拉伸，30d/90d 默认显示最新日期，图表只在内部横滚。

- [x] 7. 文档与事实源收尾。
      实现验证后将 spec delta 合入 `openspec/specs/board/spec.md`;
      将 `wireframes.md` 回流到 `docs/wireframes/pages/skills.md`;
      若 AGENTS.md 中 SKILLS 总览布局描述受影响，同步更新。
