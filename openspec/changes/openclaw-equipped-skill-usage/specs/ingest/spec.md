# spec delta:ingest(事件采集域)—— openclaw-equipped-skill-usage

## ADDED Requirements

### Requirement: skill 使用记录区分使用态与装备态

服务端 MUST 用可选事件字段 `skill_mode`(枚举 `used`/`equipped`,默认 `used`)区分 skill 的使用态与装备态:
`used` 表示 agent 跨过工具边界主动拉入 skill(Claude Code / Codex / Hermes 口径);`equipped` 表示框架把 skill
判定相关、编译进 prompt 但无使用边界(OpenClaw)。当事件同时具备 `skill` 与 `session_id` 时,服务端 MUST 以
`(session_id, skill, mode)` 幂等记录该会话的 skill,`mode` 取自 `skill_mode`(缺省或非法值 MUST 按 `used` 处理)。
同 skill 的 `used` 与 `equipped` MUST 为两条独立记录,且 MUST 保留 `session_id`、`operator`、`runtime`、`mode`、
首见 UTC 日,不受 events 90 天保留窗口影响。

#### Scenario: 装备态落库
- **WHEN** 事件带 `skill`、`session_id`、`skill_mode=equipped`
- **THEN** `skill_uses` 落 1 行 `mode='equipped'`

#### Scenario: 同 skill 的使用态与装备态共存
- **WHEN** 同一 `session_id`、同一 `skill`,分别以 `used` 与 `equipped` 各报一次
- **THEN** `skill_uses` 落 2 行(主键含 `mode`)

#### Scenario: 装备态幂等
- **WHEN** 同 `session_id`、同 `skill`、`equipped` 投递两次(含 spool 重试)
- **THEN** 记录 1 行,第二次响应仍 200

#### Scenario: 缺省 skill_mode 向后兼容
- **WHEN** 事件带 `skill` 但不带 `skill_mode`
- **THEN** 落 `mode='used'`(旧客户端行为不变)

#### Scenario: 非法 skill_mode 容错
- **WHEN** `skill_mode` 为枚举外的值
- **THEN** 落 `mode='used'`,不报错、正常返回

### Requirement: 装备态与使用态在读侧分语义

`/api/state.skills` 排行 MUST 把 `equipped` 与 `used` 分语义呈现,二者数值 MUST NOT 相加;同名不同 `mode` 为两条独立条目。
`used` 排行的口径与数值 MUST NOT 因本变更改变。

#### Scenario: 同名 skill 的两种语义分条
- **WHEN** 某 skill 同时存在 `used` 与 `equipped` 记录
- **THEN** 排行出现两条,各自计数,互不相加

#### Scenario: 既有使用态排行不回归
- **WHEN** 全部 `skill_uses` 行均为 `used`(迁移后旧数据)
- **THEN** 排行数值与本变更前一致

### Requirement: 装备态采集的隐私边界

OpenClaw 下 skill 名取自注入 prompt 的 `<skill>` 块;上报与本地日志 MUST 只含 skill 名与结构事实,
MUST NOT 含 prompt 正文、skill 描述、参数或输出。`TF_REPORT_SKILLS=0` MUST 关闭该装备态采集路径。

#### Scenario: 关闭开关时不采集
- **WHEN** `TF_REPORT_SKILLS=0`
- **THEN** 插件不附加 `skill` / `skill_mode` 字段、不上报装备态

#### Scenario: 只报名不报内容
- **WHEN** 插件从注入 `<skill>` 块提取到 skill 名并上报
- **THEN** 事件仅含 skill 名,不含 prompt 正文、skill 描述、参数或输出
