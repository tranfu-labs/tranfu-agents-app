# 提案：published-skills-page

## 背景
`/skills` 首屏里的「平均 skill/会」能说明会话里复用 skill 的密度，但对治理动作不够直接。用户希望把这个位置换成当前时间区间内「新发布的 Skill 数」，并能点进独立页面查看具体名单。

现有 `/api/skills?scope=new` 统计的是当前窗口内历史首次 `used` 的 skill，只能覆盖“第一次被用到”的场景；它不能覆盖“已经发布到公司库但还没有被任何人使用”的 skill。新版 tranfu-skills catalog 已在每个 skill item 上提供 `published_at`，可以作为新发布口径的事实源。

## 提案
- 将 `/skills` 的「当前时间窗变化」和「问题线索」中两个「平均 skill/会」指标替换为「新增发布 Skill」。
- 新增发布口径使用 catalog item 的 `published_at`，按服务端统计时区 `Asia/Shanghai` 落到日级窗口；统计范围为 catalog `type in {own, meta}`，不包含 `external`。
- `/api/skills` 增加新发布聚合字段，返回当前窗口与上一同长窗口的新发布数量，以及当前窗口新发布 skill 列表。
- 新增独立页面 `/skills/new`，继承当前时间窗，展示新发布 skill 的名单、发布时间、版本、装机数、当前窗口使用数和最近使用日；即使窗口内没有 used 记录也必须展示。
- 保留 `scope=new` 的“历史首次 used”口径，不改变顶部 `+N 7天新发现` 和现有新增使用名单行为。

## 影响
- 服务端 board/catalog 域：catalog 解析与缓存字段、`/api/skills` 响应结构、时间窗聚合 helper 与测试。
- 前端 SKILLS 域：`/skills` KPI/问题线索、`/skills/new` 路由与页面、i18n、types、链接构造、响应式布局。
- 文档事实源：`openspec/specs/board/spec.md`、`docs/wireframes/pages/skills.md` 与新增 `/skills/new` 线框在归档时同步。
