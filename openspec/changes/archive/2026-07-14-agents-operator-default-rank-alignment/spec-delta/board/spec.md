# board spec delta：Agents 操作员默认视角与排行对齐

## MODIFIED Requirements

### Requirement: Agents 默认按操作员观察

`/agents` 的视角切换器 MUST 按“操作员｜运行终端”的顺序呈现。缺失或非法 `rank` 时 MUST 默认 `operator`；选择运行终端时 MUST 写入 `rank=runtime`，刷新和分享链接后继续保持该视角。中文界面面向用户的 Runtime 标签 MUST 显示为“运行终端”，但内部查询参数和数据字段保持 `runtime`。

#### Scenario: 无 rank 参数打开 Agents

- **WHEN** 用户打开 `/agents?w=last_week`
- **THEN** 操作员切换项位于前面并处于选中状态
- **AND** 排行与每日趋势按操作员分组

#### Scenario: 显式切换运行终端

- **WHEN** 用户选择“运行终端”
- **THEN** URL 包含 `rank=runtime`
- **AND** 刷新后仍按运行终端分组

### Requirement: Agents 排行榜使用稳定列轨道

排行榜每行的名称、进度条、数量和窗口元信息 MUST 使用跨行一致的列轨道；同一断点下所有进度条 MUST 从同一水平位置开始。长名称可省略，但不得推动单行进度条起点或造成页面根横向滚动。

#### Scenario: 排行名称长度不同

- **WHEN** 排行同时包含长度不同的操作员或运行终端名称
- **THEN** 各行进度条左边界一致
- **AND** 其余统计列保持可读且页面根不横向滚动
