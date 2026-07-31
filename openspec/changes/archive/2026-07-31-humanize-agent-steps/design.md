# 设计：humanize-agent-steps

## 方案

### 1. 服务端保住操作步骤来源

改动点限定在 `server/routes/board.py::_snapshot` 的读侧卡片组装：

- 身份卡仍按现有 `(operator, agent || runtime)` 合并，状态、`last_seen`、任务、质量、
  活跃时长、Skill/Profile/Shim 仍来自现有快照逻辑。
- 查询身份最新事件时，额外为该最新事件计算 `display_current_step`：在同一
  `operator + runtime + agent||runtime + session_id` 内，取 `id` 不晚于当前最新行的最近事件，
  但排除同时满足以下条件的行：`status=done` 且 `current_step` 去首尾空白后以 `skill:` 开头。
- 最新行不是扫描行时，`display_current_step` 就是该最新行的原步骤；最新行是一个或多个 Skill
  扫描行时，沿用同一 session 的上一个非扫描步骤。没有可用步骤则返回空值，由前端回退到状态文案。
- 该排除规则只针对既有扫描链路的稳定标记。因为当前 `events` 没有单独的 Skill 扫描 source，
  不新增字段、不猜测其它 `skill` 事件，也不改写历史数据。
- 查询必须一次完成：在现有 latest identity CTE 的同一条 SQL 中增加按
  `operator + runtime + COALESCE(agent,runtime) + session_id` 分区的非扫描候选 CTE，
  用 SQLite `ROW_NUMBER() OVER (... ORDER BY id DESC)`（或等价单次聚合）选每个 session 最近候选，
  再一次 `LEFT JOIN` 到 latest identity 行。禁止在 Python 卡片循环中按卡片/身份执行子查询，避免 N+1。
- `skill_uses` 写入、会话去重、质量 `done` 计数、活跃区间、`feed[]` 的事件行数量均不变；
  `/api/agents` 和 `/api/agent/{key}` 继续消费同一份 state 卡片，因此不会复制另一套步骤选择逻辑。

这样，`Stop → done/turn end → Skill 扫描` 的顺序下，卡片不会显示 `skill: <name>`；前端随后
会隐藏 `turn end`，最终以“完成”状态表达会话结束。

### 2. 前端纯函数展示层

新增 `frontend/src/lib/agentStep.ts`（名称可在实现时保持同职责）作为唯一的步骤展示入口：

```text
formatAgentStep(runtime, current_step, status, lang) -> string | null
```

规则顺序：

1. 空值返回 `null`。
2. `status=done` 且步骤匹配 `skill: <name>` 时返回 `null`，防止补采标记穿透到活动流或卡片。
3. `session start`、`turn end`、`session end`（大小写与首尾空白宽容）返回 `null`。
4. 对 `tool: <name>` 和 `tool done: <name>` 做严格前缀解析；runtime 与工具名大小写归一化只用于查表，
   不改写未知工具的原文。
5. 命中映射时返回当前动作的人话；`tool done:` 使用“已完成/Finished …”语义。
   当 `status=done` 的卡片沿用历史 `tool: <name>` 步骤时也使用完成式，避免“完成 · 正在…”冲突。
6. 未命中映射时原样返回 `tool: <name>` 或 `tool done: <name>`；其它自定义步骤原样返回。

所有组件只在 `formatAgentStep(...)` 返回非空时显示步骤，否则使用既有 `statusName(lang, status)`
或已有任务回退。后端 API 中用于搜索的 canonical `current_step` 不改成人话，搜索仍按原始步骤字段匹配。

### 3. 映射覆盖、证据边界与回退

映射表的首要事实源改为生产库 `events.current_step` 的真实分布，而不是 rollout 文件、官方工具
列表或推测。查询为：

```sql
SELECT runtime, current_step, COUNT(*) c FROM events
WHERE current_step LIKE 'tool%'
GROUP BY 1,2 ORDER BY c DESC;
```

当前上下文收到的是该查询的部分输出；本地工作树没有 `/data/tf.db`，`docker compose ps` 也没有
运行中的服务，因此全量结果作为并行审计项补取，不阻塞本 change。生产数据决定真实键的优先级；
Claude 官方文档列明的自家工具即使暂未出现在片段中也可安全收录，未命中时只会原文回退。

证据边界与命名规则：

- `current_step` 中的键按实际入库字符串登记。Codex 的 `webrun`、`image_genimagegen`、
  `collaborationwait_agent` 等粘连形态来自上游；`shims/tf_hook.py`、`tf_report.py`、
  `server/routes/ingest.py` 没有做字符清洗，后续不得擅自改写成 `web.run`、`image_gen.imagegen`
  或 `collaboration.wait_agent`，否则无法命中历史数据。
- 查询实际出现的精确键是 Codex/Hermes 等 runtime 白名单的准入依据；Claude Code 的官方自家工具
  `Glob`、`Grep`、`TodoWrite`、`NotebookEdit` 与历史别名 `Task` 属于安全兼容例外，一并收录，
  未命中时仍原文回退，不会产生错误中文。
- MCP 键按 `mcp__<server>__<tool>` 结构解析。服务器显示名只做安全的大小写、连字符和下划线
  排版；工具语义只对本次真实结果中的高频键翻译，未知 MCP 工具显示“正在使用 {server} 的
  {tool}”，不凭名字猜测具体动作。
- Claude Code 官方[工具参考](https://code.claude.com/docs/en/tools-reference)与
  [Hook 参考](https://code.claude.com/docs/en/hooks)仍作为协议形态辅助依据，但不替代生产库
  实际入库证据。Claude Desktop 的 MCP reporter 只接收普通 `step`，本轮不纳入工具映射。
- Hermes、OpenClaw 本次没有出现在已贴的查询结果中，继续保持无可见映射；若全量结果出现它们，
  仍需先确认真实 hook 事件来源再扩展。

当前可据已贴真实查询结果登记的精确映射如下；全量结果补齐后只能追加同样有证据的行，不能
把未出现的工具名提前写进表。

#### Claude Code

| 实际 `current_step` 工具键 | 中文动作 | English action |
|---|---|---|
| `Bash` | 正在执行命令 | Running a command |
| `Read` | 正在读取文件 | Reading a file |
| `Edit` | 正在修改文件 | Editing a file |
| `Write` | 正在写入文件 | Writing a file |
| `TaskUpdate` | 正在更新任务 | Updating a task |
| `ToolSearch` | 正在查找工具 | Searching for a tool |
| `Agent` | 正在调用子 Agent | Running a sub-agent |
| `Task` | 正在调用子 Agent | Running a sub-agent | 历史版本兼容别名 |
| `WebFetch` | 正在读取网页 | Fetching a webpage |
| `WebSearch` | 正在联网搜索 | Searching the web |
| `Skill` | 正在加载 Skill | Loading a skill |
| `AskUserQuestion` | 正在等待用户回答 | Waiting for a user answer |
| `TaskCreate` | 正在创建任务 | Creating a task |
| `ScheduleWakeup` | 正在安排唤醒 | Scheduling a wakeup |
| `Glob` | 正在查找文件 | Finding files |
| `Grep` | 正在搜索文件内容 | Searching file contents |
| `TodoWrite` | 正在更新任务清单 | Updating the task list |
| `NotebookEdit` | 正在修改 Notebook | Editing a notebook |

#### Codex

| 实际 `current_step` 工具键 | 中文动作 | English action |
|---|---|---|
| `Bash` | 正在执行命令 | Running a command |
| `apply_patch` | 正在修改文件 | Editing files |
| `update_plan` | 正在更新计划 | Updating the plan |
| `view_image` | 正在查看图片 | Viewing an image |
| `webrun` | 正在联网搜索 | Searching the web |
| `request_user_input` | 正在等待用户输入 | Waiting for user input |
| `spawn_agent` | 正在创建子 Agent | Spawning a sub-agent |
| `get_goal` | 正在读取任务目标 | Reading the task goal |
| `image_genimagegen` | 正在生成图片 | Generating an image |
| `collaborationwait_agent` | 正在等待协作者 | Waiting for a collaborator |
| `collaborationsend_message` | 正在发送协作消息 | Sending a collaboration message |
| `collaborationlist_agents` | 正在查看协作者 | Listing collaborators |
| `collaborationspawn_agent` | 正在创建协作者 | Spawning a collaborator |
| `collaborationfollowup_task` | 正在跟进协作任务 | Following up on a collaboration task |
| `collaborationinterrupt_agent` | 正在中断协作者 | Interrupting a collaborator |
| `multi_agent_v1wait_agent` | 正在等待多 Agent 协作 | Waiting for multi-agent work |
| `multi_agent_v1close_agent` | 正在结束多 Agent 协作 | Closing multi-agent work |
| `codex_appload_workspace_dependencies` | 正在加载工作区依赖 | Loading workspace dependencies |
| `codex_appread_thread` | 正在读取会话线程 | Reading the conversation thread |
| `list_mcp_resources` | 正在查看 MCP 资源 | Listing MCP resources |

#### 已在真实结果中出现的 MCP 键

这些行的服务器与工具部分必须按原始键保存；同一服务器的连字符/下划线差异不合并成另一个
键，只在显示层使用同一人话标签。

| runtime | 实际 MCP 键 | 中文动作 | English action |
|---|---|---|---|
| `claude-code` | `mcp__Claude_Browser__computer` | 正在操作浏览器 | Controlling the browser |
| `claude-code` | `mcp__Claude_Browser__javascript_tool` | 正在执行浏览器脚本 | Running browser JavaScript |
| `claude-code` | `mcp__Claude_Browser__navigate` | 正在打开网页 | Navigating to a webpage |
| `claude-code` | `mcp__chrome-devtools__evaluate_script` | 正在执行浏览器脚本 | Running browser JavaScript |
| `claude-code` | `mcp__chrome-devtools__navigate_page` | 正在打开网页 | Navigating to a webpage |
| `claude-code` | `mcp__chrome-devtools__take_screenshot` | 正在截图 | Capturing a screenshot |
| `claude-code` | `mcp__chrome-devtools__resize_page` | 正在调整页面大小 | Resizing the page |
| `claude-code` | `mcp__Claude_Preview__preview_eval` | 正在预览执行页面脚本 | Evaluating a preview |
| `claude-code` | `mcp__Claude_Preview__preview_screenshot` | 正在预览截图 | Capturing a preview screenshot |
| `codex` | `mcp__node_repl__js` | 正在执行 JavaScript | Running JavaScript |
| `codex` | `mcp__node_repl__js_add_node_module_dir` | 正在加载 Node 模块 | Loading a Node module |
| `codex` | `mcp__chrome_devtools__evaluate_script` | 正在执行浏览器脚本 | Running browser JavaScript |
| `codex` | `mcp__chrome_devtools__navigate_page` | 正在打开网页 | Navigating to a webpage |
| `codex` | `mcp__chrome_devtools__take_screenshot` | 正在截图 | Capturing a screenshot |
| `codex` | `mcp__context7__query_docs` | 正在查询文档 | Querying documentation |
| `codex` | `mcp__context7__resolve_library_id` | 正在查找库文档 | Resolving library documentation |
| `codex` | `mcp__computer_use__get_app_state` | 正在读取应用状态 | Reading application state |

MCP 的未知键仍按同一结构显示“正在使用 {server} 的 {tool}”；不把 `web.run`、`image_gen` 或其它
未出现在真实结果中的名称改写成带点号的推测原形。
`tool done:` 复用同一动作词但改为完成式，例如 `tool done: Read` → “已完成读取文件”。当前
Claude Code / Codex 模板只安装 `PreToolUse`，没有安装 `PostToolUse`，所以主力链路目前只会
产生 `tool:`；仓库现有能产生完成式步骤的唯一 hook 事件路径是 Hermes `post_tool_call`。但本 change
没有 Hermes 真实样本且不纳入 Hermes 候选映射，因此首版页面不承诺出现“已完成……”事件；纯函数只
覆盖完成式解析与未知回退，未来取得真实 Hermes 样本后再单独确认其映射。不能把当前 fixture 当作
真实页面验收证据。

以下情况不做猜译：`web.run`、`image_gen`、未出现在真实结果中的 `exec_command`、Hermes `terminal`、
runtime 私有或未来新增的非 MCP 工具名，以及没有 `tool:` 前缀的自定义步骤。未识别的非 MCP 工具
保留原始文本；未识别但符合 `mcp__<server>__<tool>` 结构的 MCP 工具使用上面的通用 MCP 文案，
不把它擅自改成另一种带点号的原形。

### 4. 接入展示入口

- `frontend/src/views/Board.tsx`：Agent 卡片步骤行与右侧 Feed 子行。
- `frontend/src/views/AgentDetail.tsx`：详情头部任务/步骤行。
- `frontend/src/components/agents/AgentDirectoryTable.tsx`：Agents 明细表步骤摘要及 title。
- 不修改图表、搜索字段、状态枚举、卡片跳转、URL、主题或本地存储规则。

### 5. 测试与真实验收

#### 自动化测试

- `tests/test_board.py`：
  - 普通 `tool: Read` 后追加 `done/skill: foo` 扫描行，`/api/state` 卡片步骤不是 `skill: foo`；
  - 扫描行前有 `turn end` 时，API 步骤来源为同 session 的最近非扫描行，前端仍按生命周期规则隐藏；
  - 多个连续扫描行仍只回退到同一 session 最近非扫描行；
  - 没有非扫描步骤时返回空值，不影响 `status=done` 和 Skill 统计。
- `frontend/src/lib/agentStep.test.ts`：
  - 覆盖已贴生产结果中的 Claude Code / Codex 精确键及 Claude 官方兼容工具，尤其是 `Bash`、`apply_patch`、`update_plan`、
    `view_image`、`webrun`、`Agent`、`TaskUpdate`、`TaskCreate`、`ToolSearch`、`ScheduleWakeup`；
  - 覆盖 `mcp__chrome-devtools__...` 与 `mcp__chrome_devtools__...` 两种原始服务器键，及未知 MCP
    的结构化回退；未出现的非 MCP 工具和 Hermes 候选仍原文回退；`tool done:` 完成式；
  - `turn end`、`session end`、`session start` 与扫描态 `skill: ...` 返回空；
  - 普通自定义步骤保持原文，中英文输出互不串语。
- 入口契约测试：确认 Board、AgentDetail、AgentDirectoryTable、Feed 均调用同一个展示函数，
  防止只改卡片而遗漏详情或列表。

#### 用户可见的真实运行验收清单

每条都在本地服务真实打开页面观察，不以单测或静态源码替代：

1. 在真实已安装 hook 的 Claude Code Agent 中自然执行一次读取仓库文件的任务，打开 `/`；
   从真实 `PreToolUse` 事件产生的卡片观察 `Read` 显示“正在读取文件”（若真实任务自然触发
   `WebSearch`，同样观察“正在联网搜索”），不使用手工 POST 代替这条验收。
2. 用生产结果中真实出现的 Codex `tool: Bash`、`tool: apply_patch` 和 `tool: update_plan` 各触发一次
   页面更新，分别观察“正在执行命令”“正在修改文件”“正在更新计划”；页面不显示点号修正后的
   `web.run` 或其它推测名称。
3. 在 `/agents` 和 `/agent/:key` 打开同一 Agent；同一实际工具键的步骤摘要与 Pods 卡片使用同一
   人话文案，不出现一处中文、一处 raw 工具前缀的分裂。
4. 用真实结果中的 `mcp__Claude_Browser__navigate`、`mcp__chrome-devtools__take_screenshot` 和
   `mcp__chrome_devtools__take_screenshot` 观察“正在打开网页/正在截图”；两个 chrome-devtools
   服务器键保留各自原始拼写但显示语义一致。
5. 让同一 session 依次产生 `tool: Read`、`done/turn end`、`done/skill: demo`，打开 `/`、`/agents`
   和 `/agent/:key`；步骤行不出现 `turn end`、`session end` 或 `skill: demo`，卡片状态明确显示“完成”。
6. 在右侧活动流观察同一生命周期数据；活动流不把 `turn end` / `session end` / Skill 扫描标记
   当作可读步骤展示，状态仍显示完成，普通工具事件仍可见。
7. 切换中英文后重复观察真实 Claude/Codex 事件对应的已知工具；中文显示对应动作，英文显示对应
   action，未识别的非 MCP 工具仍保持原始工具名。
8. 触发一次 Claude/Codex Skill 扫描后，打开 `/skills`；Skill 使用仍能出现在统计数据里，
   但 Pods/Agents 卡片不被 `skill: <name>` 覆盖；这证明展示修复没有吞掉 Skill 记录。
9. 对当前真实数据只含工具名、不含命令正文的 `tool: Bash`，页面保持“正在执行命令”；不把命令、
   路径、参数或 URL 猜进步骤。命令级白名单需另立 shim 变更，不作为本 change 的验收。

## 权衡

- 选择“服务端保留同一 session 最近非扫描步骤 + 前端统一翻译”而不是只在前端过滤：只过滤会让
  扫描行覆盖掉上一条真正步骤，最终只能显示空步骤或错误的 Skill 名；服务端选择能保留最后一个
  可解释的操作。
- 不新增 `event_kind` / `source` 字段：当前扫描标记已经是既有稳定格式，新增协议字段会扩大到 shim、
  安装、自更新和兼容路径，超出本轮第一档目标。代价是实现必须把 `done + skill:` 作为保守约定，
  并在测试中锁定。
- 采用按 runtime 的白名单而不是全局同名映射：少翻译一些工具，但不会把 MCP 或不同 runtime
  的私有工具误译成错误动作。未知回退原文，后续可按真实样本增补。
- 只显示工具名对应的动作，不显示对象内容：牺牲“正在读取哪个文件”的具体性，换取不改变隐私边界、
  不触碰协议和不把命令/路径带入看板。

## 风险

- 未来新增 Skill 扫描格式若不再使用 `done + skill:`，服务端可能再次把扫描行当作步骤；回滚方式是
  恢复原 `_snapshot` 查询，增量修复方式是更新单一扫描标记判定与测试，不需要改表。
- 工具名可能因 runtime 版本变动；未命中时显示原文，不会产生错误中文。回滚方式是移除前端映射接入，
  保留 API 的步骤来源修复。
- `tool done:` 的显示依赖当前事件仍使用 running 状态，若未来终止语义改造需另立 change；本轮不改变
  状态枚举或 hook 映射。
- 前端若漏接一个入口，会出现页面间文案不一致；由入口契约测试和真实 `/`、`/agents`、`/agent/:key`
  验收共同兜底。
- SQL 结果中的 `display_current_step` 只是内部计算列；组装卡片时立即移除，避免无意扩展 API 字段。
