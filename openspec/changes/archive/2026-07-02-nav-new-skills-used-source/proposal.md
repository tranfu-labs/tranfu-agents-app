# 提案:nav-new-skills-used-source

## 背景
顶部导航里的 `+N 新增 Skill` 与 `N 资产` 由 `skills_seen` / profile 侧痕迹放大,会把 installed-only、profile-only、equipped-only 混进展示数字。SKILLS 页已经以 `skill_uses` 的 `mode=used` 作为真实使用事实源,nav 数字也应与该口径一致。

## 提案
- 将 `/api/state.leverage.assets` 改为 used-only distinct skill count,来源为 `skill_uses WHERE mode='used'`。
- 将 `/api/state.leverage.skills_week` 改为当前 7 天窗口内"历史首次 used"的 skill 数。
- 为 `/api/skills` 增加 `scope=new` 筛选态,返回当前窗口内首次 used 的可行动 skill 名单,并保留 operator 贡献、当前窗口与上个窗口变化字段。
- 顶部 `+N 7天新发现` 跳转 `/skills?w=7d&scope=new`;手机 `/skills` 首屏保留新增名单入口。

## 影响
- 服务端 board 域:`/api/state` leverage helper、`/api/skills` 查询参数与响应字段。
- 前端 SKILLS 总览:URL 查询参数、控制摘要、顶部导航 readout copy 与跳转。
- 文档事实源:合并到 `openspec/specs/board/spec.md`、`docs/wireframes/pages/skills.md` 与 AGENTS。
