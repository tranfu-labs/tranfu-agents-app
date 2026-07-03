# spec delta：board

## 接口扩展
- `GET /api/skills` 响应新增可选字段 `published_skills[]`。每项表示当前时间窗内新发布的公司库 skill，字段至少包含：
  `name/source/version/author/published_at/published_day/updated_at/path/sha/installers/window_sessions/last_day`。
- `GET /api/skills.period_comparison` 新增：
  - `current_published_skill_count`
  - `previous_published_skill_count`
- `GET /skills/new` 作为 React SPA 深链返回 SKILLS 新发布列表页。

## 修改规则(MUST)
- 「新发布 Skill」口径只统计 catalog 中 `type in {own, meta}` 且 `published_at` 可解析的 skill；`external` 不计入。
- `published_at` 必须按 UTC instant 解析，并转换为服务端统计时区 `Asia/Shanghai` 的 date-only `published_day` 后再和 `window.start..window.end` 比较。
- 当前窗口内发布但没有任何 `mode=used` 记录的 skill 仍必须进入 `published_skills[]`，其 `window_sessions=0`。
- `/api/skills?scope=new` 继续表示当前窗口内历史首次 `mode=used` 的 skill 名单，不得改成发布口径。
- `/skills` skill 视角「当前时间窗变化」第 4 格和「问题线索」中的「平均 skill/会」必须替换为「新增发布 Skill」，其入口跳 `/skills/new`，不得跳 `/skills/evidence?kind=avg_per_session`。
- `/skills/new` 必须继承当前时间窗参数 `w/wstart/wend`；页面不依赖全局 `/api/state` 首包，独立请求 SKILLS API。
- `/skills/new` 列表必须能展示未使用 skill，不得因为没有 `/skill/:name` used 详情而隐藏该项。
- 旧 catalog 没有 `published_at` 时，服务端不得报错；相关 skill 不进入新发布统计。

## 可验证行为
- catalog 中 `own` skill 的 `published_at` 落在当前 7 天窗口，且没有 `skill_uses` 记录 → `/api/skills?w=7d` 的 `current_published_skill_count=1`，`published_skills[0].window_sessions=0`。
- catalog 中 `meta` skill 的 `published_at` 落在上一同长窗口 → 当前窗口 `current_published_skill_count=0`，`previous_published_skill_count=1`。
- catalog 中 `external` skill 的 `published_at` 落在当前窗口 → 不计入 `current_published_skill_count`，也不出现在 `published_skills[]`。
- catalog item 缺失或带非法 `published_at` → `/api/skills` 仍 200，且该 item 不计入新发布。
- 从 `/skills?w=14d` 点击「新增发布 Skill」入口 → 进入 `/skills/new?w=14d`，页面展示同一窗口的新发布列表。
