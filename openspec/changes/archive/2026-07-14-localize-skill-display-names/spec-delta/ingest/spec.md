# ingest spec delta：profile Skill 双语元数据

## MODIFIED Requirements

### Requirement: profile Skill 从 SKILL.md 上报可选显示名称

profile 自动探测 MUST 在读取每个 `SKILL.md` 时保留 `name`，并 best-effort 读取可选 `display_name/display_name_zh`；解析或读取失败 MUST 静默降级且不得阻塞宿主 agent。`name` 仍是 Skill identity，显示字段仅供读侧呈现。

#### Scenario: 本机非公司库 Skill 带双语名称

- **GIVEN** 本机 `SKILL.md` frontmatter 同时定义 `name/display_name/display_name_zh`
- **WHEN** shim 采集 profile
- **THEN** `skills.local[]` 对应项包含三个字段
- **AND** 后续使用事件仍只需上报 slug `skill`

#### Scenario: 旧 Skill 未定义显示名

- **WHEN** `SKILL.md` 只定义 `name`
- **THEN** profile 继续正常上报该 name
- **AND** 不因缺少显示字段抛错或省略 Skill
