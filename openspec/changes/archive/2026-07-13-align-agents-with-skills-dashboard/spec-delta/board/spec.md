# spec-delta:board（align-agents-with-skills-dashboard）

## MODIFIED Requirements

### Requirement: Agents summary hierarchy

`/agents` 控制区 MUST 使用与 Skills 相同的“控制条标题 + 当前视角说明”层级，不得在控制 frame 内重复页面标题。时间窗变化与稳定摘要 MUST 合并到单一 Skills 同款八卡 KPI 网格，不得保留第二个摘要 frame、事实带或次级行。八张卡 MUST 为：窗口活跃 Agent、窗口活跃时长、Agent 总数、操作员数、当前在线/运行中、本周活跃、运行质量、待处理 Agent；本周活跃卡的 detail MUST 保留今日活跃。前两张展示当前/上一同长度窗口和 delta，其余六张展示“快照”及对应 detail。问题线索 MUST 位于主分析区之前并保持可点击筛选。

八卡 frame 标题 MUST 与 Skills 使用同一窗口派生规则，直接显示“今天变化 / 本周变化 / 近 N 天变化”等完整标题；不得固定显示“时间窗变化”后只靠右侧 `cnt` 补充窗口，因为手机会隐藏 `cnt`。

每张 KPI 卡的核心数值与真实入口 MUST 位于同一行；入口 MUST 指向当前趋势、排行、Agent 明细或现有 URL 筛选，不得使用无目标的装饰图标。入口必须键盘可达并提供与真实动作一致的可访问名称。

#### Scenario: Stable facts remain visible without a second KPI wall

- **WHEN** 用户在桌面打开 `/agents`
- **THEN** 页面在单一时间窗变化 frame 内显示八张同构 KPI 卡
- **AND** 窗口活跃 Agent 与窗口活跃时长显示环比
- **AND** Agent 总数、操作员数、当前在线、本周活跃、运行质量与待处理 Agent 以快照卡显示
- **AND** Agent 总数卡同时说明当前可见数量与全部身份数量
- **AND** 本周活跃卡的 detail 显示今日活跃，不与默认 today 的窗口活跃时长重复主值
- **AND** 页面不存在第二个摘要 frame、事实带或次级事实行
- **AND** 八张卡的右上角入口均落到真实趋势、排行、筛选或 Agent 明细目标

### Requirement: Agents window visualization matches available evidence

Agents 活跃趋势 MUST 使用与 Skills 每日趋势一致的图表几何和交互规范：按容器内容宽度布局，`1..14` 天填满自身面板且使用相同柱宽上限，`>14` 天只在图表容器内部横向滚动；尾部有数据时默认显示最新日期，尾部全零但窗口内较早日期有数据时默认定位当前指标最后一个非零日期，避免首屏误判为空。轴线、日期抽样、今日斜纹、透明命中区和自定义 tooltip MUST 与 Skills chart 保持同等级表现。该对齐不得改变 Skills chart 的现有行为。

当窗口为 `today` 时，趋势面板 MUST 明确显示当天活跃 Agent 数和活跃时长；有正值时使用紧凑单日 plot、今日标记和 tooltip，不得伪造小时级序列。当当前指标在整窗内全为 0 时，MUST 显示与 Skills 一致的 Empty，不得渲染一排空坐标轴。活跃 Agent 与活跃时长 MUST 通过指标切换分别控制柱高，不得把人数与秒数堆叠或直接相加。

逐日命中区 MUST 支持 pointer hover/click 与键盘 focus，浮层 MUST 锚定日期槽并在视口边缘翻转；日期槽 MUST 使用 roving focus，整张图在顺序 Tab 中只能产生一个日期停靠点，左右方向键切换日期。移动端点空白或滚动图表时 MUST 关闭浮层。只有窗口右端等于服务端 `today` 的列可标记“今日进行中”。

窗口或指标切换时 MUST 关闭旧 tooltip，并把 roving focus 与长窗滚动位置同时重置到新指标最后一个非零日期；不得出现画面显示最新日期、键盘停靠点仍留在最早日期的分裂状态。current/previous 窗口只有每个统计日都存在于 overview 日序列时才可参与显示或环比，部分重叠窗口 MUST 视为不可用。

#### Scenario: Today uses an honest compact snapshot

- **WHEN** 用户打开 `/agents?w=today`
- **THEN** 趋势面板显示当天活跃 Agent 数和活跃时长
- **AND** 页面不展示伪造的小时级趋势
- **AND** 有正值时单日图形使用紧凑 plot，并沿用 Skills chart 的柱宽、今日斜纹与 tooltip 语言

#### Scenario: Empty Agent window does not draw an empty axis

- **WHEN** 当前选择的趋势指标在整个窗口内均为 0
- **THEN** 趋势面板显示 Empty 标题与说明
- **AND** 页面不渲染坐标轴、日期标签或零高度柱

#### Scenario: Short and long windows contain their overflow

- **WHEN** 用户打开 `/agents?w=7d`
- **THEN** 七个统计日按 Skills chart 的同一几何规则填满趋势面板且柱宽不超过同一上限
- **WHEN** 用户打开 `/agents?w=30d`
- **THEN** 趋势长轴只在图表容器内部横向滚动
- **AND** 页面根不产生横向滚动

### Requirement: Agents analysis and card density

桌面 `>1080px` MUST 左侧展示 Runtime/操作员排行、右侧展示活跃趋势，两列 MUST 采用接近 Skills 短窗的近等宽比例而非当前 `.75fr / 1.25fr`，两面板底边对齐。两张面板 MUST 使用同构的 `//标题 + cnt` header；排行空窗 MUST 显示居中 Empty。`<=1080px` MUST 单列。Agent 明细卡 MUST 保留身份、状态、任务、步骤、今日/本周活跃、Skill、MCP、质量、Shim、最近活跃和问题数量，并通过层级与间距压缩重复空白；整卡继续键盘可达并下钻 `/agent/:key`。

#### Scenario: Compact cards preserve governance facts

- **WHEN** 任意 Agent 卡片显示在列表中
- **THEN** 既有任务、活跃、治理和下钻事实全部可访问
- **AND** 卡片不因压缩而隐藏 Shim 三态或问题数量

### Requirement: Agents mobile priority

在 `<=600px`，Agents 内容 MUST 按控制摘要 → 问题线索 → Agent 明细 → 时间窗变化八卡网格 → 排行 → 趋势呈现。八卡 MUST 为 2×4。视觉顺序与 DOM/键盘焦点顺序 MUST 一致，不得只用 CSS `order` 重排交互区块；Agents 页面根 MUST 不产生横向滚动。

#### Scenario: Mobile exposes decisions before directory depth

- **WHEN** 用户以 375×812 打开 `/agents`
- **THEN** 问题线索之后先出现可行动的 Agent 明细，不被 KPI、排行或趋势挤到后面
- **AND** 时间窗变化区只出现一个 2×4 KPI 网格，不再出现第二组摘要卡
- **AND** 页面根宽度不超过视口宽度

## NON-GOALS

本 change MUST NOT 修改 `/skills` 页面结构、Skills 组件、Skills 数据请求、Skills 专用 CSS 行为或 `docs/wireframes/pages/skills.md`。`/skills` 仅作为视觉参照与回归基线。
