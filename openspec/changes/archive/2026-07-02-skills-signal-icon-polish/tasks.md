# 任务：skills-signal-icon-polish

- [x] 1. 更新 `frontend/src/components/skills/HealthBar.tsx`，移除 Skill 视角问题线索和按人视角使用线索的可见动作文案，保留 evidence icon 的链接、`aria-label` 与 `title`。
- [x] 2. 更新 `frontend/src/styles.css`，将 `.evidence-icon-link` 默认态调整为浅灰弱提示色，并为 `:hover` / `:focus-visible` 恢复当前高亮色与明确交互反馈。
- [x] 3. 更新 `docs/wireframes/pages/skills.md`，同步桌面、平板、手机的「问题线索」示意，去掉旧动作文案。
- [x] 4. 运行 `npm --prefix frontend run test:unit`。
- [x] 5. 运行 `npm --prefix frontend run build`。
- [x] 6. 走查 `/skills?view=skill&w=7d`、`/skills?view=operator&w=7d` 和 375px 手机宽度，确认文案、icon hover/focus 与页面无横向溢出。
