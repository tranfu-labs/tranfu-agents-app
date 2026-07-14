# 设计：agents-duration-by-agent-dashboard

字符图见 `wireframes.md`，行为增量见 `spec-delta/board/spec.md`。

## 方案

### 1. 固定 Agent × 运行时长口径

Agents 页继续以服务端已经按 `operator + agent||runtime` 合并的身份卡片为统计基数，不把 session 当成 Agent，也不跨身份重新合并同名 Agent。页面内部为每个身份生成稳定的 Agent segment key 和展示标签；同名时追加稳定短标识，避免时长串账，同时不回退展示操作员或运行终端字段。

`AgentFilters` 删除 `rank/rt/op`，默认排序从 `recent` 改为 `window_time`。解析旧 URL 时不再把这三个参数放入筛选模型；组件首次挂载时用 replace 规范化为仍有效的 `q/status/signal/w/wstart/wend/sort` 参数。

### 2. Agent 排行

排行直接消费窗口明细行，而不是 `AgentOverview.runtime/operator`。每行展示 Agent 名、同起点时长进度条、窗口运行时长以及活跃天数/当前状态；进度条以窗口最大 Agent 时长为 100%。

排行点击不再回填筛选，而是使用与 Agent 明细相同的 identity key 下钻 `/agent/:key`。零时长 Agent 不进入排行，但仍保留在 Agent 明细中。

### 3. 固定时长图表与扇形图

`buildAgentDailyBreakdown` 按稳定 Agent identity 生成逐日时长分段，`buildAgentTrendModel` 继续负责 Top 8 + 其他。图表删除 metric state 和切换器，所有模式判定、锚点、滚动、柱高、扇区面积和 tooltip 主值固定读取 `active_seconds`。

- 单日正值：环形扇形图的每个扇区代表一个 Agent 的运行时长占比，中心显示全部 Agent 总时长；上方保留活跃 Agent 数作为辅助事实。
- 多日正值：每天的柱体总高等于全部 Agent 当日总运行时长，分段等于各 Agent 当日运行时长。
- 全窗零值：继续显示 Empty，不绘制空扇形、坐标轴或零高度柱。

图表 tooltip 同时展示当日总运行时长、活跃 Agent 数和各 Agent 时长；键盘与 pointer 行为沿用现有逻辑。

### 4. 控制条、八卡和明细

控制条只保留搜索、状态、时间窗、自定义时间和排序；标题右侧显示固定口径。搜索候选只包含 Agent 名、任务、步骤和 model，不包含已隐藏的操作员/运行终端。

八卡顺序改为：窗口总时长、平均时长/活跃 Agent、窗口活跃 Agent、Agent 总数、当前在线、本周时长、累计运行质量、待处理 Agent。平均时长只有窗口完整可用且存在活跃 Agent 时才计算；否则显示 `—`。前三张窗口指标展示上一同长度窗口与 delta，其余保持快照语义。

明细表删除操作员和运行终端列，头像文字与颜色改由 Agent identity 生成；其余任务、窗口时长/天数、累计质量、资源、Shim、最近活跃与整行下钻保持不变。手机真实 DOM 顺序继续为控制摘要 → 问题线索 → Agent 明细 → 八卡 → 排行 → 趋势。

## 测试

### 单元测试

- URL 解析忽略 `rank/rt/op`，序列化不再输出它们，默认排序为 `window_time`，其它有效参数保持稳定。
- 搜索不匹配仅存在于操作员/运行终端的文本，仍匹配 Agent、任务、步骤和 model。
- Agent 排行按窗口时长降序，零时长不进入排行，同名 identity 不串账。
- Agent 逐日分段之和等于当日总运行时长；Top 8 + 其他不丢失时长。
- 单日扇区只按 `active_seconds` 计算，比例之和为 1，中心总值等于扇区原值之和。
- 平均运行时长 KPI 的当前值、上期值、零活跃和窗口不完整边界正确。
- 既有窗口完整性、日期锚点、长窗滚动和手机 DOM 顺序回归通过。

### AI / 浏览器验证

- 1440×900：控制条无操作员/运行终端控件，八卡一行，Agent 排行与扇形/趋势近等宽且底边对齐。
- 768×1024：控制条紧凑换行，八卡 4×2，排行和图表单列，表格仅自身横滚。
- 375×812：真实顺序为摘要、线索、明细、八卡、排行、图表，根节点无横向滚动。
- `today` 正值显示 Agent 环形扇形图；`7d` 显示铺满的 Agent 时长堆叠柱；`30d` 只在图表盒内横滚。
- 浅色、深色、system 三态下扇区、图例、tooltip、焦点态可读；键盘 Tab 只有一个日期停靠点，方向键和 Escape 有效。
- 旧 `/agents?rank=runtime&rt=codex&op=alice` 打开后不产生隐藏筛选，URL 被规范化。

## 权衡

- 不删除服务端 `agent_overview.runtime/operator`：它们可能仍服务其它视图；本次只是 Agents 列表页的展示口径变化。
- 不保留单选“Agent”按钮：只有一个选项的切换控件会制造虚假可操作性，改用静态口径说明。
- 不把多日图改为单一总量折线：按 Agent 堆叠既能看到团队总时长，也能保留各 Agent 的贡献构成，并与单日扇形保持同一颜色语义。

## 风险

- 同名 Agent 隐藏了操作员/运行终端后可能难以区分；使用稳定短标识消歧，并保留详情下钻。
- 旧链接中的隐藏参数若只忽略不清理会误导用户；首次渲染必须 replace 为规范 URL，且避免 replace 循环。
- 固定时长后图表代码会减少一个指标分支，但现有 tooltip 与键盘状态依赖 metric；实现时需同步收口 key、锚点与 reset 依赖，避免残留状态。

## 实现后反思

- 实现与提案一致：列表页只保留 Agent 口径，排行、单日扇形、多日堆叠和明细都消费同一批身份卡片与窗口日；服务端 runtime/operator 聚合仍保留为兼容数据，没有扩大改动边界。
- 同名 Agent 通过 identity 排序生成稳定序号，排行、图例和明细共享同一标签算法，既不串账也不重新暴露操作员或运行终端。
- 旧参数规范化采用幂等 query 序列化，浏览器验证 `/agents?rank=runtime&rt=codex&op=alice` 会 replace 到 `/agents`，未出现导航循环。
- 1440、768、375 三档以及 today/7d/30d 已验证：页面根无横向滚动，平板明细和长窗图只在自身容器滚动；浅色、深色、system 均可切换。全仓 lint 仍有 5 个既存错误，改动文件的定向 lint 通过。
