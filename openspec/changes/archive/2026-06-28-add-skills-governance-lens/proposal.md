# 变更提案:add-skills-governance-lens(SKILLS 使用排行管理者筛选 Lens)

- 状态:Proposed
- 关联:skills-stats-page、skills-operator-view、skills-view-ux-polish

## 背景 / 问题
SKILLS 首页现在能看整体趋势、按 Skill/按人排行、公司库采纳漏斗,但管理者想回答一个更直接的问题:

> 下面这个 Skill 列表里,哪些 Skill 被频繁使用,却还没有被公司库收录?

现有"来源=非公司库"全局筛选只能把表格缩小到未收录项,但不能表达"未收录使用占全部使用的比例",
也不能把这个问题作为使用排行里的一个明确管理视角呈现。若把它做成页面顶部 KPI 卡,又会抢掉
SKILLS 页"先看整体趋势和主榜"的主线。

## 目标
- 在 `/skills` 的**使用排行**内部新增管理者筛选 Lens,而不是新增页面顶部报表。
- 默认 Lens 仍为"全部 Skill";用户选择"未收录使用占比"后,排行表切换为未收录 Skill 列表。
- "未收录使用占比"使用百分比口径:
  `当前时间窗内 source=非公司库 的 used 会话数 / 当前时间窗内全部 used 会话数`。
- Lens 只出现在"按 Skill"视角;按人视角不显示,避免主语混乱。
- `external` 不算未收录;只有服务端来源字段 `非公司库` 算未收录。
- 只统计 `mode=used`,不包含 `equipped`。

## 非目标
- 不改采集协议、不新增写侧字段、不改 `skill_uses` 表结构。
- 不改变 `/api/skills.table` 既有 used-only 主榜字段和默认排序。
- 不把管理 Lens 做成全局筛选条项;它只影响使用排行区域,不影响趋势图、漏斗或按人视角。
- 不实现"提交收录/一键推荐到公司库"等后续治理动作。

## 方案概述
后端 `/api/skills` 增加只读字段 `governance.untracked_usage`,由服务端按当前 `days`
窗口计算总 used 会话数、未收录 used 会话数、未收录占比和未收录 Top 列表。前端在
`SkillsTable` 上方新增 Lens 条:

`[ 全部 Skill ] [ 未收录使用占比 28% · 14/50 ]`

选择第二个 Lens 后,下方表格切换为未收录列表,列改为 `Skill / 占比 / used会话 / 用户 / runtime / 趋势 / 最近`,
行点击仍进入 `/skill/:name`。趋势图、过滤条、公司库漏斗保持原行为。

## 影响
- specs/board: `/api/skills` 新增 `governance.untracked_usage` 字段与前端 Lens 行为规则。
- frontend: `Skills.tsx`、类型、i18n、demo 数据、CSS 和 `/skills` wireframe 更新。
- tests: `/api/skills` 增加治理聚合单测;前端构建与桌面/窄屏走查。
