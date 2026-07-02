# 提案：skills-signal-icon-polish

## 背景
SKILLS 总览的「问题线索」和按人视角的「使用线索」当前在每个指标后展示动作文案，例如「看未收录 used 名单」「看已装未用名单」。这些文案与旁边的跳转 icon 表达同一动作，首屏阅读噪音较高，也会挤占窄屏横向空间。

同时，证据跳转 icon 在默认态就使用高亮色，导致页面上多个证据入口同时争夺注意力。产品期望默认态更克制，只有悬浮或键盘聚焦时再显示现有高亮色。

## 提案
- `/skills` Skill 视角「问题线索」去掉可见动作文案，仅保留指标标题、当前事实值和证据跳转 icon。
- `/skills` 按人视角「使用线索」采用同样规则，去掉可见动作文案，仅保留事实值和证据跳转 icon。
- 所有 `.evidence-icon-link` 默认使用浅灰弱提示色；`:hover` 与 `:focus-visible` 恢复现有高亮色和边框/背景反馈。
- icon 的 `aria-label` 与 `title` 继续保留「查看证据: 指标名」语义，保证可访问名称和鼠标提示不丢失。
- 同步更新 `/skills` 线框图，避免事实源继续展示旧动作文案。

## 影响
- 影响模块：`frontend/` SKILLS 总览 UI、`docs/wireframes/pages/skills.md` 版式事实源、`openspec/specs/board/spec.md` 的前端规则。
- 不改 `/api/skills`、`/api/skills/evidence` 或任何服务端统计口径。
- 不改证据跳转目标；现有 `evidencePath(...)` 链接保持不变。
