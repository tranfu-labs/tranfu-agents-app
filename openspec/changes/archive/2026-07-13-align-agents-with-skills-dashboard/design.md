# 设计：align-agents-with-skills-dashboard

本文件只描述实现与权衡。字符线框见 `wireframes.md`，任务拆解见 `tasks.md`，行为增量见 `spec-delta/board/spec.md`。

## 方案

### 1. 对齐 Skills 的视觉语法，不修改 Skills

Agents 参照 Skills 的控制条、八卡 KPI 网格、问题条、排行轨道、分析面板和断点节奏，但只改 Agents markup、Agents 子组件和 `.agents-*` CSS：

- 不改 `Skills.tsx` 或 `components/skills/*`；
- 不改变 `.skills-*` 现有表现；
- 若需要共用已有 token，只读取 `--bg/--elev/--line/--muted/--brand/--info` 等全局变量，不向 Skills 添加新分支逻辑；
- 不创建同时理解 Agent/Skill 两套数据模型的复合组件。

控制区 frame 标题改为与 Skills 一致的 `//控制条`，右侧短句随 `rank=runtime|operator` 切换为当前视角说明；“Agents 列表”身份已经由顶栏选中态表达，不再在同一 frame 重复渲染页面名称和总数。手机仍只显示折叠摘要。

### 2. Skills 同款八卡时间窗变化网格

删除独立的 `agents-kpi-frame` 和五卡 `.agent-kpis`。`AgentWindowBar` 像 Skills `KpiStrip` 一样在单一 frame 内渲染八张同构 `.stat` 卡：

1. 窗口活跃 Agent：当前值、上期值、delta；
2. 窗口活跃时长：当前值、上期值、delta；
3. Agent 总数：当前可见身份总量，detail 显示“当前可见 / 全部身份”，delta 为“快照”；
4. 操作员数：当前可见身份中的去重操作员总量，delta 为“快照”；
5. 当前在线 / 运行中：当前 live 数，detail 为 `live / agents`，delta 为“快照”；
6. 本周活跃：主值显示本周活跃时长，detail 保留今日活跃时长，delta 为“快照”；
7. 运行质量：成功率，detail 显示 `success / runs`，delta 为“快照”；
8. 待处理 Agent：待处理身份数，detail 显示错误 / 阻塞，delta 为“快照”。

八卡使用与 Skills KPI 一致的“数值 + 右上角入口 / label / 短结论 / delta”四层结构和间距。桌面为 8×1，平板 4×2，手机 2×4；不再存在事实带、次级行或第二个摘要 frame。第 6 卡以本周为主值、今日为 detail，避免默认 `today` 时和第 2 卡出现两个相同主值。

右上角入口必须落到真实目标，不能只为“像 Skills”放装饰图标：

- 窗口活跃 Agent / 活跃时长 → 聚焦当前趋势面板；
- Agent 总数 → 聚焦当前 Agent 明细；
- 操作员数 → 切换 `rank=operator` 并聚焦排行；
- 当前在线 → 写入 `status=live`、清除冲突的 `signal` 并聚焦 Agent 明细；
- 本周活跃 → 写入 `sort=week` 并聚焦 Agent 明细；
- 运行质量 → 写入 `sort=success` 并聚焦 Agent 明细；
- 待处理 Agent → 写入 `status=attention`、清除具体 `signal` 并聚焦 Agent 明细。

入口默认浅灰，hover / `focus-visible` 才高亮；每个入口使用与目标一致的 `aria-label`。筛选型入口保留现有 `q/w/rt/op` 等观察范围，只更新该入口负责的参数及与它直接冲突的 `signal`。

### 3. 问题线索与主分析

问题线索保持异常/阻塞、Shim 不一致、14 天未活跃、成功率偏低四项，点击仍回填 `status=attention&signal=...`。视觉参照 Skills health bar：默认低权重、选中/hover 提升，不渲染成四张大卡。

主分析继续使用 Agents 独立组件：

- 左侧 `AgentRankPanel` 展示当前窗口 Runtime/操作员排行；
- 右侧 `AgentActivityChart` 展示当前窗口活跃趋势；
- 桌面列宽从当前 `.75fr / 1.25fr` 调整到 Skills 短窗同级的 `.95fr / 1.05fr`，避免 chart 吃掉过多宽度；
- 两张面板都使用 `//标题 + cnt` 的同构 header，趋势指标切换仍放在右侧但不得把标题挤成两行；
- 排行行沿用 Agents 的 Runtime/操作员语义，但对齐 Skills 的行高、内边距、轨道厚度、数值列和 hover/focus 反馈；
- 排行无当前窗口聚合时显示居中的标题 + hint Empty，不把“暂无聚合数据”孤零零放在左上角；
- `<=1080px` 单列；桌面两面板底边对齐。

不会复用 Skill 的 source badge、evidence link 或 `sel` 状态。

### 4. 对齐 Skills chart 的几何和交互

`AgentActivityChart` 不再维护 `Math.max(760, days * 20)`、最大 10px 柱宽的独立几何。它直接消费现有 `resolveSkillsChartLayout(dayCount, contentWidth)`，但不修改该 helper 或 `StackedSkillChart`：

- 使用 `ResizeObserver` 测量 chart-box 内容宽度；
- `1..14` 天按 Skills 规则铺满可视宽度，柱宽上限为同一常量；
- `>14` 天使用同一日槽宽，在 chart-box 内横滚并自动定位最新日期；
- 多日窗口使用相同的轴线位置、220px chart viewBox、日期抽样密度、今日斜纹和 hover 降权语言；
- 增加覆盖整日柱槽的透明 hit rect，hover、click 与键盘 focus 显示自定义浮层；tooltip 同时列出该日活跃 Agent 数和活跃时长，并在且仅在窗口右端等于 `today` 时标记“今日进行中”；
- hit rect 必须有逐日 `aria-label`，但 90 天不得产生 90 个顺序 Tab 停靠点；使用 roving `tabIndex`，左右方向键切换日期，Escape/blur 关闭。移动端点列显示浮层，点空白或横向滚动关闭；键盘与 pointer 共享同一个 tooltip model；
- 保留“活跃 Agent / 活跃时长”切换，柱高使用当前选择的单一量纲，避免把人数和秒数错误堆叠。

`today` 仍只有一个真实统计日：有正值时使用紧凑单日 plot（约 160px 绘图区）、受控柱宽、今日斜纹和 tooltip，并在图表上方直显当天两个事实；不得伪造小时级序列。全窗没有正值时复用 Skills 的 Empty 语言，不绘制坐标轴、日期或零高度柱。SVG JSX 只消费布局结果，不再自行判断断点和宽度。

### 5. Agent 卡片密度

AgentCard 继续保留既有业务事实和整卡下钻，只调整层级：

1. 身份、Runtime/操作员、状态；
2. 当前任务与步骤；
3. 今日/本周、Skill/MCP 四项事实；
4. 质量、Shim、最近活跃、问题数。

桌面仍为两列，平板/手机单列；手机将质量、Shim 和最近活跃压成两行以内，避免每张卡出现大片低信息空白。

### 6. Agents 手机顺序

不改全局 TopBar。`<=600px` 仅调整 `.agents-page` 子区块顺序：

1. 控制摘要；
2. 问题线索；
3. Agent 明细；
4. 时间窗变化八卡网格；
5. 排行；
6. today 状态/窗口趋势。

这不是机械复制 Skills 的 section 名称，而是复制它在手机上的“先判断、再行动、最后补充统计”优先级：Agents 没有治理待办 row，最接近可行动名单的是 Agent 明细。移动端不能只用 CSS `order` 把带交互的 KPI、列表和图表换位，因为 Tab 仍会按桌面 DOM 顺序移动。实现应按 `matchMedia('(max-width: 600px)')` 选择 section 数组顺序，并给 section 稳定 key，使视觉顺序与 DOM/焦点顺序一致；跨断点切换时不得复制交互节点或丢失 URL 状态。Agents 根页面不得横向滚动，长图只在图表盒内滚动。

### 7. 可测性

可测逻辑放在 `frontend/src/lib/agentsDashboard.ts` 或独立 Agent helper：

- 八张 KPI 卡的值、detail 与 delta/snapshot 模型；
- 八张 KPI 卡的真实入口动作与保留参数；
- Agent daily tooltip 模型和当前指标值；
- today 紧凑 plot / 全零 Empty / 多日 plot 的显示模式；
- 既有窗口解析、delta、信号筛选继续回归。

`Agents.tsx`、`AgentActivityChart.tsx` 和 `AgentRankPanel.tsx` 只组合展示与事件。

预计 `frontend/src/styles.css` 中 Agents 专用 diff 可能超过 200 行，但属于纯 CSS，豁免单测，以三断点截图、面板尺寸和根溢出断言验证。任一 TypeScript 单文件实际 diff 若超过 200 行，实施前先拆组件/纯函数，不能把新判断堆在页面 JSX。

## 权衡

- 操作员数原本只是 Agent 总数的 detail；提升为独立卡是为了匹配当前页面已有 Runtime/操作员双视角，并填补第 8 个不重复的治理事实。Agent 总数不再重复显示操作员数。
- today 不伪造小时趋势，单日视觉动态仍弱于 7d；用紧凑 plot、当天双事实和真实 Empty 区分“单日有数据”与“全窗无数据”。
- 不修改全局 TopBar，意味着本 change 不解决所有页面共同的手机头部问题；这是为了严格兑现“Skills 不变”。
- 不复用 Skills 业务组件，少量 CSS 结构可能重复，但能保持数据语义和变更范围清晰。

## 风险

- 八卡在 1440px 可能拥挤：严格复用 Skills KPI 的字号、截断和 gap，平板/手机按 4×2、2×4 降列，不使用更小字体强塞。
- today 与 7d 趋势的数据密度不同：外框仍与同排排行底边对齐，但 plot 自身按单日/多日切换高度；不得为了外框等高重新塞回大块空坐标区。
- Agents 专用 CSS 必须避免宽泛选择器，以免意外改变 Skills；实施后用 `git diff` 与两页截图确认 Skills 无视觉/代码变更。

## 回滚

本变更无服务端与数据迁移。Agents 页面、Agent 子组件和 Agents 专用 CSS 可独立回退，不影响 Skills 或其它路由。
