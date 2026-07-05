# 提案：polish-skills-evidence-first-screen

## 背景

上一轮 `skills-evidence-first-screen` 已把 `/skills` 从 KPI dashboard 拉向证据优先的 operator console，并新增 `/skills/evidence` 证据页。但基于线上截图和 375 mobile / 1440x900 evidence 页审查，当前实现仍有几个偏差：

- mobile 首屏仍先暴露筛选表单，真正的「问题线索 / 待处理线索」被挤到第一屏之后。
- 摘要格继续铺长 skill name 和重复「证据」文字，`openspec-driven-development / tranfu-website-design / strategy-first-development` 这类长名单在卡片里成为噪音。
- `待处理线索` 行里大量 `看证据 / 找人` 文字按钮形成 link farm，文字焦点从线索事实转向动作链接。
- evidence 页 1440x900 第一屏被标题区、摘要区和分组区占用，`total / untracked` 的 raw records 表头和前几行基本掉到首屏外。
- evidence 页摘要仍像 KPI cards，`kind=total` 里的 `UNTRACKED N` 容易被误读成总页主结论，而不是总证据里的一个切片。

本轮目标不是新增图表或改后端统计口径，而是把首屏和证据页的「第一眼看到下一步」做准。

## 提案

1. `/skills` mobile 控制条默认压缩成一行摘要：`7d · 按 Skill · 全部 runtime/source · 筛选`，点开后再显示完整筛选控件；375 宽第一屏必须先露出「问题线索」和「待处理线索」。
2. `/skills` 摘要格只显示短结论，不直接铺长 skill 名单；具体名单只出现在「待处理线索」、evidence 页或展开详情里。重复的「证据」文字入口改成 icon entry。
3. `待处理线索` 行正文只讲事实，例如 `figma · 3 次 · alice/bob · 未收录`；右侧动作收为 icon button。不得使用 `找人` 文案，语义改为「按使用者看证据」。mobile 行点击进入 evidence，次级动作收进 `...` 菜单。
4. `忽略` 只做当前页面内临时隐藏，刷新或重新进入页面后恢复；不得新增后端模型，不得写 localStorage/sessionStorage。
5. `/skills/evidence` 页头和摘要改紧凑，摘要按 kind 收敛成一句上下文：
   - `total`：`284 records · 64 skills · 8 operators · 188 sessions，其中 92 条来自未收录 skill`
   - `untracked`：`92 条未收录使用 · 46 skills · 7 operators`
   - `idle`：`19 个装了但 7d 没用 · 33 installs`
   - `zero_install`：`5 个收录但零装机`
6. `/skills/evidence?kind=total` 里的未收录切片必须显示为上下文句 `其中 N 条来自未收录 skill`，并能进入 `kind=untracked`；不得作为独立 KPI card 站着。
7. evidence 页默认主内容优先展示 facts：有 raw records 的 kind 第一屏必须露出 records 表头和前几行；无 raw records 的 `idle / unused_ratio / zero_install` 第一屏必须露出名单表。`Top skills / Top operators` 永远是辅助，不抢主表。

## 影响

- **前端**：调整 `/skills` 控制条、摘要格、问题线索、待处理线索、icon actions、临时忽略状态和 `/skills/evidence` 布局。预计主要影响 `frontend/src/views/Skills.tsx`、`frontend/src/views/SkillsEvidence.tsx`、`frontend/src/components/skills/*` 与相关 CSS。
- **后端**：不改 API 形状和统计口径；若现有 payload 已包含所需 summary 字段，前端自行组装上下文句。若缺少直接跳 `kind=untracked` 所需 query，复用现有 URL builder。
- **事实源**：更新 board spec-delta 与 wireframes，归档时回流 `docs/wireframes/pages/skills.md`、`docs/wireframes/pages/skills-evidence.md` 和 `docs/wireframes/flow.md`。
- **测试/验证**：补充前端单测覆盖 evidence URL/icon action/temporary ignore；用 Playwright 或 Browser 在 375x812 `/skills` 与 1440x900 `/skills/evidence` 截图验收。
