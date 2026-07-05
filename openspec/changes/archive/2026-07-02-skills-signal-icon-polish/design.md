# 设计：skills-signal-icon-polish

## 方案
本变更是纯前端展示打磨，不改变数据结构、聚合口径或路由。

### 1. HealthBar 去掉可见动作文案
- 文件：`frontend/src/components/skills/HealthBar.tsx`
- Skill 视角当前数组形态为 `[title, value, kind, action]`，按人视角为 `[title, value, action, kind]`。实现时删除 action 字段和 `<em>{action}</em>` 渲染。
- 每个 signal 仍渲染：
  - 左侧圆点；
  - 指标标题；
  - 核心值；
  - 证据跳转 icon。
- `Link` 的 `to={evidencePath(location.search, kind)}` 不变。
- `aria-label` 与 `title` 继续使用 `${t('viewEvidence')}: ${title}`，让不可见动作语义仍能被辅助技术和鼠标提示读取。
- `healthUntrackedAction` 等 i18n key 可先保留，避免扩大无关删除 diff；若后续确认全站不再使用，再单独清理。

### 2. Evidence icon 默认弱化，hover/focus 高亮
- 文件：`frontend/src/styles.css`
- `.evidence-icon-link` 默认态：
  - `color` 改为浅灰弱提示色，优先使用现有主题变量，例如 `var(--faint)` 或 `var(--muted)`。
  - 边框仍使用 `var(--line)`，背景仍使用 `var(--elev2)`，保持按钮轮廓可见。
- `.evidence-icon-link:hover` 与 `.evidence-icon-link:focus-visible`：
  - `color: var(--info)`，恢复当前高亮效果；
  - 保持或增强 `border-color` / `background` 反馈；
  - `focus-visible` 补充可见 outline，保证键盘可达。
- 该样式是全局 evidence icon 样式，因此会作用于当前时间窗变化、问题线索/使用线索、排行、证据摘要等所有同类跳转 icon，符合本次确认的「全都」口径。

### 3. 线框同步
- 文件：`docs/wireframes/pages/skills.md`
- 基线引用：`docs/wireframes/pages/skills.md` 当前桌面、平板、手机三个断点的「③ 问题线索」区域。
- 更新目标：
  - 删除「看未收录 used 名单」「看已装未用名单」「看集中使用分布」等可见动作文字；
  - 每项保留事实线索 + `[↗]`；
  - 注释表中补充 icon 默认浅灰、hover/focus 高亮的交互说明。

## 测试与验证
- 这是纯展示和样式变更，不引入新的可测业务逻辑；不强制新增单元测试。
- 必跑：
  - `npm --prefix frontend run test:unit`
  - `npm --prefix frontend run build`
- 必要 AI/人工验证：
  - 桌面 `/skills?view=skill&w=7d`：问题线索不出现旧动作文案，5 个 icon 仍能跳到对应 evidence。
  - 桌面 `/skills?view=operator&w=7d`：使用线索不出现旧动作文案，5 个 icon 仍能跳到对应 evidence。
  - 375px 手机宽度：问题线索/使用线索无横向溢出，icon 与文字行对齐。
  - hover 与键盘 Tab 聚焦 evidence icon：默认浅灰，hover/focus 后恢复当前高亮色。

## 权衡
- 不删除 i18n action key：本次目标是界面不显示动作文案，删除未使用翻译 key 会扩大 diff，且未来治理行或 tooltip 可能仍复用类似文案。
- 全局改 `.evidence-icon-link`：比逐处加类更一致，也符合「跳转图标全都是」的确认口径；代价是所有 evidence icon 默认态都会更克制，需要验证当前时间窗变化和排行区域也符合预期。

## 风险
- 默认态过浅可能降低可发现性。缓解：保留按钮边框和背景，hover/focus 明确高亮，`title`/`aria-label` 保留语义。
- 去掉动作文案后，部分用户可能不确定 icon 目的。缓解：所有 icon 仍有 tooltip，且跳转目标与指标语义一一对应。
- 回滚方式：纯前端和文档变更，`git revert` 即可，无数据迁移或接口兼容风险。
