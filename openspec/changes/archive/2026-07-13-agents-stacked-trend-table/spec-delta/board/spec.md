# board spec delta：Agents 分组趋势与窗口明细表

## MODIFIED Requirements

### Requirement: Agents 主分析区反映当前视角的每日分布

`/agents` 的 Runtime/操作员视角切换 MUST 同时驱动排行和活跃趋势。趋势 MUST 以每日堆叠柱展示当前筛选集合在各 Runtime 或操作员之间的分布，并保留活跃 Agent/活跃时长指标切换。窗口总量 Top 8 以外的分组 MUST 合并为“其他”，所有分段之和 MUST 等于当日总量。长窗口只允许图表容器内部横滚。

#### Scenario: 切换到操作员视角

- **WHEN** 用户在 `/agents` 选择操作员视角
- **THEN** 排行和趋势都按操作员分组
- **AND** 每日柱可读出各操作员分布与当日合计

#### Scenario: 操作员分组超过八个

- **WHEN** 当前窗口内有超过 8 个有值操作员
- **THEN** 图例保留窗口总量最高的 8 个操作员
- **AND** 其余操作员按日汇入“其他”且不改变每日合计

### Requirement: Agent 明细使用表格并响应控制条

`/agents` 底部 `// Agent 明细` MUST 使用响应式表格而不是卡片网格。表格行 MUST 使用顶部 `q/status/signal/w/wstart/wend/rt/op/sort` 形成的同一筛选集合；当前时间窗列 MUST 展示该 Agent 在所选窗口的活跃时长和活跃天数，不得继续显示固定今天/本周统计。状态/任务/最后活跃保持当前快照，运行质量 MUST 标明为累计口径。整行 MUST 可点击且可用 Enter/Space 下钻 Agent 详情。

#### Scenario: 切换时间窗

- **WHEN** 用户从今天切到近 30 天
- **THEN** 表格每行的窗口活跃时长与活跃天数按近 30 天重算
- **AND** 表格行集合继续服从其余顶部筛选

#### Scenario: 手机查看 Agent 明细

- **WHEN** 视口宽度不超过 600px
- **THEN** 表格行压缩为无根级横滚的摘要行
- **AND** 仍保留 Agent、状态、窗口活跃、运行质量、资源和最后活跃等关键事实
