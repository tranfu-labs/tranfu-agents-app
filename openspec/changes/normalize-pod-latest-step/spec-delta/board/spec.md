# board 规格增量：Pods 卡片最新步骤归一

## ADDED Requirements

### Requirement: Pods 卡片步骤使用面向用户的最新状态投影

`/api/state.sessions[]` MUST 保留原始 `current_step`，并可增加仅供 Pods 卡片展示的
`pod_step?: string | null`。`/` Pods 卡片 MUST 优先消费该派生字段，把最新步骤作为展示投影处理，
不得把已知的内部工具前缀、生命周期事件或 Skill 统计补采副产物直接当作用户文案。
该投影只作用于 Pods 卡片步骤行，不得改写原始事件或既有 `current_step` 消费者。

#### Scenario: 工具开始与完成

- **GIVEN** 事件 `current_step` 为 `tool: Bash`
- **AND** `pod_step` 为 `tool: Bash`
- **WHEN** 中文界面渲染 `/`
- **THEN** 步骤行显示 `▸ 正在运行命令 Bash`
- **AND** 英文界面显示 `▸ Running command Bash`
- **WHEN** `current_step` 与 `pod_step` 更新为 `tool done: Bash`
- **THEN** 中文显示 `▸ 已完成命令 Bash`
- **AND** 英文显示 `▸ Finished command Bash`

#### Scenario: 生命周期不泄漏到步骤行

- **GIVEN** 最新非扫描事件为 `status=done,current_step="turn end"`
- **AND** `pod_step` 为 `turn end`
- **WHEN** Pods 卡片渲染
- **THEN** 步骤行 MUST NOT 显示 `turn end`
- **AND** MUST 使用既有本地化状态表达终态

#### Scenario: Skill 扫描不覆盖卡片步骤来源

- **GIVEN** 同一 identity、同一 session 已有非扫描事件
- **AND** 终态后追加一条或多条
  `source ∈ {heartbeat, heartbeat_resume},status=done,current_step="skill: <name>"`
  的 Skill 扫描补采事件
- **WHEN** `/api/state.sessions` 组装卡片
- **THEN** 卡片状态、时间、原始 `current_step` 及其它最新事实仍按最新事件返回
- **AND** `pod_step` MUST 回退到该 session 最近的非扫描事件
- **AND** 不得从同身份的其它并发 session 借用步骤
- **AND** `heartbeat` 与 `heartbeat_resume` 两种扫描来源 MUST 使用同一判定
- **AND** 原始 events、`current_step`、`skill_uses` 与 `/api/state.feed` MUST 保持不变
- **AND** `source=heartbeat` 的扫描行可保留在 feed，`heartbeat_resume` MUST 继续按既有规则被 feed 排除
- **AND** AgentDetail、Agents 等既有消费者 MUST 继续使用原始 `current_step`
- **AND** 无前序非扫描事件时 `pod_step` MUST 为 `null`，不得抛错

#### Scenario: 真实任务与自由文本安全退化

- **GIVEN** `task="接入自检"` 且 `current_step="tf-doctor"`、`pod_step="tf-doctor"`
- **WHEN** Pods 卡片渲染
- **THEN** 任务行 MUST 原样显示 `接入自检`
- **AND** 步骤行 MUST 原样显示 `tf-doctor`
- **GIVEN** `current_step` 是其它未识别自由文本
- **THEN** 步骤投影 MUST 原样保留该文本，不得截断、翻译或清空

### Requirement: 活动流不继承 Pods 卡片步骤投影

本变更 MUST NOT 把 Pods 卡片步骤归一规则接入活动流。`/api/state.feed` 继续表示原始真实事件变化，
前端 Feed 继续使用原始 `current_step || task` 摘要；如需重写历史事件文案，MUST 另行确认产品范围。

#### Scenario: 同页卡片与活动流边界不同

- **GIVEN** `/api/state.feed` 包含 `tool done: Bash`、`turn end` 或 `skill: alpha`
- **WHEN** `/` 同时渲染 Pods 卡片和活动流
- **THEN** Pods 卡片按本增量归一最新步骤
- **AND** 活动流仍保留原始历史事件摘要
