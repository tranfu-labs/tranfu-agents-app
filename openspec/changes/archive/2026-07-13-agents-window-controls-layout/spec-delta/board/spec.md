# spec-delta:board（agents-window-controls-layout）

## MODIFIED Requirements

### Requirement: Agents list controls and window comparison

`/agents` 顶部控制条 MUST 同时承载 Runtime/操作员排行榜视角切换、搜索、状态、时间窗、Runtime、操作员与排序筛选。视角切换 MUST 位于控制条而不是排行榜卡片内部。时间窗 MUST 复用 Skills 的 `today`、`this_week`、`last_week`、`7d`、`14d`、`30d`、`90d`、`custom` 选项，缺省语义为 `today`，并通过 `w/wstart/wend` 保持在 URL；筛选变化使用 replace，不得写入浏览器持久化存储。

时间窗区域 MUST 展示当前窗口与上一同长度窗口的活跃 Agent 数、活跃时长变化，以及当前在线数和运行质量快照。活跃序列以 `/api/state.agent_overview.today` 为统计日右端；上一窗口不存在或两边均为 0 时，变化值 MUST 显示 `—`，前期为 0 且本期大于 0 时 MUST 显示 `+∞%`。

#### Scenario: Agents defaults to today and exposes shared filters

- **WHEN** 用户打开没有窗口参数的 `/agents`
- **THEN** 时间窗控制显示“今天”
- **AND** Runtime 与操作员选择器位于同一个顶部控制条
- **AND** 页面 URL 不因初次渲染被强制写入无关参数

#### Scenario: Agents window comparison uses adjacent equal windows

- **WHEN** 用户打开 `/agents?w=14d`
- **THEN** 页面以最近 14 个服务端统计日作为当前窗口
- **AND** 以其前紧邻的 14 个统计日作为上一窗口
- **AND** 活跃 Agent 数与活跃时长显示当前值及相对上一窗口的变化

### Requirement: Agents compact issue signals and analysis layout

Agents 问题线索 MUST 使用与 Skills 健康条一致的紧凑事实条视觉，不得以四张大卡占据同等重量的主内容区域；每个线索仍 MUST 可点击并回填对应的 `status/signal` 筛选。桌面 `>1080px` 主分析区 MUST 左侧展示 Runtime/操作员排行榜、右侧展示当前时间窗活跃趋势图；两张卡片外框底边 MUST 对齐。`<=1080px` MUST 退化为单列，手机根页面不得产生横向滚动。

#### Scenario: Desktop places rank before trend

- **WHEN** 浏览器视口为 `1440x900`
- **AND** 用户打开 `/agents?w=today`
- **THEN** 排行卡的左边界 MUST 小于趋势卡的左边界
- **AND** 两张卡片底边差值 MUST 不超过 `4px`

#### Scenario: Compact signals remain actionable

- **WHEN** 任意问题线索数量大于 0
- **THEN** 线索以紧凑条状事实项显示
- **AND** 点击该项 MUST 保留已有的 `status=attention&signal=...` 筛选行为
