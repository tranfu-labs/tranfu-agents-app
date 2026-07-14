# spec-delta:board（agents-today-pie-chart）

## MODIFIED Requirements

### Requirement: Agents single-day distribution and multi-day trend

`AgentActivityChart` MUST 根据当前窗口的真实统计日数量选择图形。当前指标全窗为零时 MUST 只显示 Empty；窗口只有一个真实统计日且当前指标为正值时 MUST 显示环形扇形图；窗口包含两个及以上真实统计日时 MUST 继续显示逐日堆叠柱状图。

单日环形扇形图 MUST 按当前 `rank=operator|runtime` 视角与当前活跃 Agent 数/活跃时长指标展示 Top 8 + 其他分组占比，并复用多日柱状图的颜色映射、图例、hover/focus 降权、tooltip、主题变量和键盘交互。圆环中心 MUST 显示当前指标总值；tooltip MUST 同时保留当日活跃 Agent 总数和活跃总时长。单日图不得伪造小时级时间数据。

多日柱状图的坐标轴、逐日堆叠、日期抽样、今日进行中、短窗铺满、长窗内部横滚和最后非零日定位 MUST 保持现有行为。

#### Scenario: Today renders an operator distribution ring

- **WHEN** 用户打开默认 `/agents`
- **AND** 当前操作员视角的活跃 Agent 指标大于零
- **THEN** 趋势面板显示按操作员分组的环形扇形图
- **AND** 圆环中心显示当日活跃 Agent 总数
- **AND** 页面不绘制单根日期柱或伪造小时坐标轴

#### Scenario: Runtime and metric switches update the same ring

- **WHEN** 用户在今天窗口切换到运行终端视角或切换到活跃时长指标
- **THEN** 扇区占比、中心值、图例和 tooltip 使用新的视角与指标
- **AND** tooltip 仍同时显示当日总人数和总时长

#### Scenario: Multi-day windows retain bars

- **WHEN** 用户选择 `7d`、`14d`、`30d`、`90d` 或包含至少两天的有效自定义窗口
- **THEN** 趋势面板继续显示逐日堆叠柱状图
- **AND** 不显示单日环形扇形图

#### Scenario: Single-day zero value remains empty

- **WHEN** 今天窗口的当前指标为零
- **THEN** 趋势面板只显示空状态
- **AND** 不显示空圆环、零高度柱或坐标轴
