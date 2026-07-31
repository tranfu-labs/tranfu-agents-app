# board 规格增量：Pods 卡片最新步骤归一

## ADDED Requirements

### Requirement: 看板四个入口使用面向用户的最新状态投影

`/api/state.sessions[]` MUST 保留原始 `current_step`，并可增加供看板展示的
`pod_step?: string | null`。`/` Pods 卡片、活动流、`/agent/:key` 详情和 `/agents` 明细 MUST
经同一个步骤格式化函数展示；Pods 卡片、详情和明细 MUST 优先消费该派生字段，把最新步骤作为展示投影处理，
活动流 MUST 以事件自己的原始 `current_step` 作为格式化输入。
不得把已知的内部工具前缀、生命周期事件或 Skill 统计补采副产物直接当作用户文案。
该投影不得改写原始事件或既有 `current_step` API 消费者；旧服务端缺失 `pod_step` 时，前三者
按字段未定义兼容回退原始 `current_step`。

#### Scenario: 工具开始与完成

- **GIVEN** 事件 `current_step` 为 `tool: Bash`
- **AND** `pod_step` 为 `tool: Bash`
- **WHEN** 中文界面渲染任一入口
- **THEN** 步骤行显示对应工具的人话开始文案
- **AND** 英文界面显示对应工具的人话开始文案
- **WHEN** `current_step` 与 `pod_step` 更新为 `tool done: Bash`
- **THEN** 中文显示对应工具的人话完成文案
- **AND** 英文显示对应工具的人话完成文案

#### Scenario: 生命周期不泄漏到四个入口步骤行

- **GIVEN** 最新非扫描事件为 `status=done,current_step="turn end"`
- **AND** `pod_step` 为 `turn end`
- **WHEN** 任一四个入口渲染
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
- **WHEN** 任一适用入口渲染
- **THEN** 任务行 MUST 原样显示 `接入自检`
- **AND** 步骤行 MUST 原样显示 `tf-doctor`
- **GIVEN** `current_step` 是其它未识别自由文本
- **THEN** 步骤投影 MUST 原样保留该文本，不得截断、翻译或清空

### Requirement: 活动流不继承卡片的 pod_step 回退来源

本变更 MUST NOT 把卡片的 `pod_step` 回退值借入活动流。`/api/state.feed` 继续表示原始真实事件变化，
前端 Feed 以原始 `current_step || task` 为格式化输入，并与其它入口复用同一展示函数；如需改变 API
事件原文或历史记录事实，MUST 另行确认产品范围。

#### Scenario: 同页卡片与活动流边界不同

- **GIVEN** `/api/state.feed` 包含 `tool done: Bash`、`turn end` 或 `skill: alpha`
- **WHEN** `/` 同时渲染 Pods 卡片和活动流
- **THEN** Pods 卡片按本增量归一最新步骤
- **AND** 活动流按自己的原始事件步骤使用同一展示规则，不借用 `pod_step`
