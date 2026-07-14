# 设计：agents-operator-default-rank-alignment

字符图见 `wireframes.md`，任务见 `tasks.md`，行为增量见 `spec-delta/board/spec.md`。

## 方案

### 1. 默认视角与 URL 契约

`parseAgentFilters` 在缺失或收到非法 `rank` 时返回 `operator`。`agentFiltersQuery` 把 `operator` 视为默认值而省略，把 `runtime` 显式写为 `rank=runtime`。这样 `/agents` 与 `/agents?w=last_week` 默认进入操作员视角，而切到运行终端后 URL 可复制、刷新和前进后退恢复。

KPI“操作员数”的排行入口仍写 `rank=operator`；序列化后回到默认无参数 URL，不改变动作语义。

### 2. 中文显示名称与切换顺序

复用现有 i18n key，不重命名内部类型：中文 `agentRuntimeFilter`、`agentRankRuntime`、`agentRank` 与 runtime hint 改为“运行终端”语义，英文继续使用 Runtime。控制条 DOM 顺序先操作员、后运行终端，键盘焦点顺序与视觉顺序一致。

### 3. 排行榜列对齐

桌面/平板行使用四列稳定轨道：固定范围的名称列、弹性进度条列、固定数量列、固定窗口元信息列。手机行使用三列稳定轨道，并让元信息独占下一行。所有行不再由各自行内 `auto` 内容决定轨道宽度，因此进度条起点一致。

### 4. 可测性

- URL 默认值和序列化属于纯逻辑，必须补单测：空参数、非法参数、显式 runtime、默认 operator 不冗余写 URL。
- 文案、切换顺序与 CSS 对齐属于展示层，不增加组件单测；使用浏览器在 1440×900、768×1024、375×812 读取选中态和每行进度条 `getBoundingClientRect().x`，并检查页面根无横向滚动。

## 风险与权衡

- 旧链接未带 `rank` 时会从 Runtime 视角变为操作员视角，这是本次明确要求；显式 `rank=runtime` 不受影响。
- 中文界面只改展示名称，不改 runtime 数据字段，避免扩散到协议和服务端。
- 固定辅助列宽可能压缩长操作员名；名称列保留省略号和 title，进度条优先保持可比较性。
