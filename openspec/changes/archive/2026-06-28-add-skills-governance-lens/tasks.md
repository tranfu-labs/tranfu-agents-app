# 任务:add-skills-governance-lens

- [x] 1. `server/routes/board.py`:在 `skills_overview` 中新增 `governance.untracked_usage`。
      口径:当前 `days` 窗口、only used、`source=非公司库` 为未收录、`external` 不计入未收录、
      ratio=未收录 used / 全部 used;Top 行含 sessions/share/users_30d/runtime_counts/trend_14d/last_day。
- [x] 2. `tests/test_skills_stats_page.py`:新增 `/api/skills` 治理聚合测试。
      覆盖 own/external/非公司库/equipped、7/30 天窗口变化、空分母、Top 排序与 share。
- [x] 3. `frontend/src/lib/types.ts` / `frontend/src/lib/skillQuery.ts` / `frontend/src/lib/demo.ts`:
      增加 `governance.untracked_usage` 类型、`lens=all|untracked` query 状态与 demo 数据。
- [x] 4. `frontend/src/views/Skills.tsx`:在按 Skill 视角的"使用排行"卡片内部、表格上方新增管理者筛选 Lens。
      默认 all 保持现有主榜;untracked 切换到未收录占比列表;按人视角不展示;行点击继续进入 Skill 详情。
- [x] 5. `frontend/src/lib/i18n.ts` / `frontend/src/styles.css`:补中文/英文文案与紧凑 Lens 样式。
      窄屏按钮可换行,表格沿用横向滚动。
- [x] 6. 验证:`python -m py_compile server/*.py server/routes/*.py`;
      `pytest tests/test_skills_stats_page.py tests/test_board.py`;
      `npm --prefix frontend run build`;桌面和 ≤600px 检查 `/skills` all/untracked/operator 三种状态。
