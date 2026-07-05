# spec delta:board(本变更新增/修改的规则)

> 已合入 `openspec/specs/board/spec.md`。

## 修改规则(MUST)
- `/api/state.leverage.assets` 表示 used-only distinct skill 数:来源为 `skill_uses WHERE mode='used'` 的 `COUNT(DISTINCT skill)`。profile installed、`skills_seen` only、`equipped` only 不计入。
- `/api/state.leverage.skills_week` 表示当前 7 天窗口内历史首次 `used` 的 distinct skill 数。历史首次日定义为该 skill 在 `skill_uses WHERE mode='used'` 的最小 `day`;该 first used day 落在 `[today-6,today]` 时计入。
- `/api/state` 与 `/api/skills` 必须复用同一套 used-only helper 推导新增 skill 名单,不得各自维护不同口径。
- `skills_seen` 仍可作为内部发现/安装痕迹派生态,但不得作为 nav 上 `assets` 或 `skills_week` 的展示事实源。

## 接口扩展
- `GET /api/skills` 增加可选 query `scope={all|new}`。缺省或 `all` 保持原总览;`new` 时,`table`、`daily`、`operator_table`、`operator_daily`、`period_comparison`、`attribution`、`governance.untracked_usage` 只包含当前窗口内历史首次 used 的 skill;`funnel` 保持公司库整体口径。
- `/api/skills` 返回 `scope` 与 `new_skill_count`。`new_skill_count` 为当前窗口内历史首次 used distinct skill 数。
- 非法 `scope` 返回 400。

## 前端规则(MUST)
- 顶部 `+N 7天新发现` 必须是可键盘访问的链接,目标为 `/skills?w=7d&scope=new`。
- 顶部 `N Skill 资产` 文案必须表达 used-only skill assets,不得暗示安装量或已发现量。
- `/skills?scope=new` 必须呈现可行动名单态:能看到具体 skill、operator 贡献、当前窗口与上个窗口的变化字段;不得默认跳 raw evidence。
- 手机端可以隐藏顶部新增数字,但 `/skills` 首屏控制摘要旁必须提供一键/键盘可达的新增名单入口。
- 新增名单态不得 KPI 化,不得新增红绿箭头或同比话术;聚合数旁边必须能展开或跳到名单。

## 可验证行为
- 同一 session 对同一 skill 重复上报 used → nav assets 只计 1 个 distinct skill,新增 skill 也只计 1。
- 同一 skill 多个 session used → nav assets 仍只计 1 个 distinct skill。
- 仅 profile installed 或仅 `skill_mode=equipped` 的 skill → 不计入 `/api/state.leverage.assets` 或 `skills_week`。
- 某 skill 首次 used 在 9 天前、当前 7 天再次 used → 不出现在 `/api/skills?w=7d&scope=new`,但出现在默认 `/api/skills?w=7d`。
- 某 skill 首次 used 在当前 7 天,且 alice/bob 各有一个会话 → `/api/skills?w=7d&scope=new` 的 table 只含该 skill,operator_table 只含 alice/bob,该 skill `previous_sessions=0`。
