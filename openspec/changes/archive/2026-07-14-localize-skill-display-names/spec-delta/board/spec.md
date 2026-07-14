# board spec delta：Skill 双语显示名称

## MODIFIED Requirements

### Requirement: Skill slug 与本地化显示名称分离

所有 Skill 统计与治理 API MUST 继续使用 slug 作为稳定 identity。每个含 Skill 的响应对象 MUST 同时提供来自 catalog 或 profile `SKILL.md` 的可选 `display_name/display_name_zh` 原值；包含多个 Skill 的 payload MUST 另提供以 slug 为键的 `skill_names` 双语映射，供其它页面和集成直接复用。服务端不得只返回一个随 locale 变化的单一 label。中文界面 MUST 按 `display_name_zh → display_name → slug` 显示，英文界面 MUST 按 `display_name → display_name_zh → slug` 显示。显示名不得改变数据库聚合、source 归因、URL、query、颜色、选择器或删除目标。

#### Scenario: 公司库 Skill 在中文界面展示

- **GIVEN** catalog 中 `openspec-driven-development` 的 `display_name_zh` 为 `OpenSpec 驱动开发`
- **WHEN** 用户以中文打开 Skills 总览、线索、证据或详情页面
- **THEN** 所有可见名称均显示 `OpenSpec 驱动开发`
- **AND** 详情 URL、筛选参数和 API identity 仍使用 `openspec-driven-development`
- **AND** API 对象同时返回 `display_name=OpenSpec-Driven Development` 与 `display_name_zh=OpenSpec 驱动开发`

#### Scenario: 英文与缺失字段回退

- **WHEN** 英文界面存在 `display_name`
- **THEN** 显示英文名称
- **AND WHEN** 英文名称缺失但中文名称存在
- **THEN** 回退中文名称
- **AND WHEN** 两者均缺失
- **THEN** 回退 slug 且页面仍可用

### Requirement: Skill 名称全局一致与可搜索

`/skills` 的排行、趋势图、明细、抽屉、治理线索、漏斗及其 `/skills/new`、`/skills/evidence`、`/skills/clues/:kind`、`/skill/:name`、`/operator/:name` 下钻 MUST 使用同一显示规则；Agent profile Skill 与 Admin Skill 清理视图 MUST 同步。名称搜索 MUST 同时匹配 slug、`display_name` 与 `display_name_zh`，包括服务端分页的 evidence/clue 查询。可访问名称与 tooltip MUST 不得残留可解析显示名对应的 slug。

#### Scenario: 用中文显示名搜索英文 Skill slug

- **WHEN** 用户搜索 `OpenSpec 驱动开发`
- **THEN** 总览、新发布列表与 evidence 记录均能命中 slug `openspec-driven-development`
- **AND** 点击结果仍以 slug 打开唯一 Skill 详情

#### Scenario: 显示名冲突

- **GIVEN** 两个 slug 拥有相同显示名
- **WHEN** 用户搜索该显示名
- **THEN** 两个 Skill 均可命中
- **AND** 选择、跳转与治理操作仍由各自 slug 区分
