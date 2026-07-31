# spec delta:board（humanize-agent-steps）

> 合入后并入 `openspec/specs/board/spec.md`。本 delta 只修改看板读侧的步骤来源与展示，
> 不修改 TATP 上报协议、事件 schema、质量/时长计算或 Skill 统计口径。

## 接口（修改）

- `GET /api/state` 返回的 `sessions[].current_step` 对身份卡使用“当前可解释步骤”来源：
  同一 `operator + runtime + agent||runtime + session_id` 内，取最新事件的步骤；若该最新事件是
  `status=done` 且 `current_step` 以 `skill:` 开头的 Skill 扫描标记，则取同 session 最近一条
  非扫描事件的 `current_step`，没有则返回空值。
- `/api/agents` 与 `/api/agent/{key}` 继续消费同一身份卡步骤来源，不得各自复制另一套选择逻辑。
- `feed[]` 仍保留真实事件流和原始事件时间/状态；前端展示步骤时必须经过统一步骤展示函数，
  不得直接拼接 `current_step`。
- `_snapshot` 必须在单次 SQL 查询中完成 latest identity 行与 session 最近非扫描步骤候选的连接；
  不得在卡片循环中执行逐身份/逐 session 子查询形成 N+1。

## 规则（MUST）

- Skill 扫描事件的识别仅为既有兼容标记：`status=done` 且 `trim(current_step)` 以 `skill:` 开头。
  该规则只影响身份卡的步骤来源；扫描事件仍保留在 `events`，`skill_uses` 仍照常写入、去重和统计。
- 生命周期步骤 `session start`、`turn end`、`session end` 不进入前端步骤行；页面使用现有状态文案表达
  启动、完成或空闲。大小写与首尾空白不应导致生命周期标记漏出。
- 工具步骤按生产库 `events.current_step` 查询中已真实出现的 runtime + 精确工具键转换；Claude Code
  官方自家工具与历史别名可作为安全兼容例外收录，未命中时仍原文回退。本次已收到的 Claude Code
  精确键为：`Bash`、`Read`、`Edit`、`Write`、`TaskUpdate`、`ToolSearch`、
  `Agent`、`Task`、`WebFetch`、`WebSearch`、`Skill`、`AskUserQuestion`、`TaskCreate`、`ScheduleWakeup`、
  `Glob`、`Grep`、`TodoWrite`、`NotebookEdit`。其中 `Task` 是历史版本兼容别名，命不中时原文回退。
- 本次已收到的 Codex 精确键为：`Bash`、`apply_patch`、`update_plan`、`view_image`、`webrun`、
  `request_user_input`、`spawn_agent`、`get_goal`、`image_genimagegen`、
  `collaborationwait_agent`、`collaborationsend_message`、`collaborationlist_agents`、
  `collaborationspawn_agent`、`collaborationfollowup_task`、`collaborationinterrupt_agent`、
  `multi_agent_v1wait_agent`、`multi_agent_v1close_agent`、`codex_appload_workspace_dependencies`、
  `codex_appread_thread`、`list_mcp_resources`。键必须保持上报原形，不能把 `webrun` 修正成 `web.run`。
- 已真实出现的 MCP 键按 `mcp__<server>__<tool>` 解析，包含 Claude Code 的
  `mcp__Claude_Browser__computer`、`mcp__Claude_Browser__javascript_tool`、
  `mcp__Claude_Browser__navigate`、`mcp__chrome-devtools__evaluate_script`、
  `mcp__chrome-devtools__navigate_page`、`mcp__chrome-devtools__take_screenshot`、
  `mcp__chrome-devtools__resize_page`、`mcp__Claude_Preview__preview_eval`、
  `mcp__Claude_Preview__preview_screenshot`，以及 Codex 的
  `mcp__node_repl__js`、`mcp__node_repl__js_add_node_module_dir`、
  `mcp__chrome_devtools__evaluate_script`、`mcp__chrome_devtools__navigate_page`、
  `mcp__chrome_devtools__take_screenshot`、`mcp__context7__query_docs`、
  `mcp__context7__resolve_library_id`、`mcp__computer_use__get_app_state`。
- Claude 官方[工具参考](https://code.claude.com/docs/en/tools-reference)与[Hook 参考](https://code.claude.com/docs/en/hooks)
  作为 Claude 名称与 `PreToolUse.tool_name` 形态的辅助依据；生产查询是是否进入本 change 映射表的
  决定性证据。Claude Desktop 的 MCP reporter、Hermes 与 OpenClaw 本轮不纳入映射，除非全量结果与
  真实 hook 来源另行确认。
- `web.run`、`image_gen`、未出现在真实结果中的 `exec_command`、Hermes `terminal` 与未知非 MCP
  工具不得猜译，按原文回退；`view_image` 与 `image_genimagegen` 因已真实出现而分别进入 Codex 映射。
- `tool: <known>` 的展示必须是当前动作的人话（例如 Claude `WebSearch` →“正在联网搜索”，
  `Read` →“正在读取文件”）；`tool done: <known>` 使用相同动作的完成式。中英文都必须有对应文案。
- 当卡片 `status=done` 但服务端步骤来源是同 session 回退的历史 `tool: <known>` 时，同样必须使用
  完成式（例如 `tool: view_image` →“已完成查看图片”），不得因为 canonical 步骤仍是 `tool:` 就显示“正在…”。
- SQL 内部的 `display_current_step` 不属于 API 契约；`/api/state.sessions[]`、`/api/agents.agents[]` 和详情
  消费的卡片对象只保留 canonical 字段 `current_step`。
- 未知但符合 `mcp__<server>__<tool>` 结构的工具显示结构化的“正在使用 {server} 的 {tool}”，
  未知非 MCP 工具、未列入白名单的私有工具和未来工具名保留原始 `tool: <name>` 或
  `tool done: <name>` 文本；普通非工具自定义步骤也保留原文。
- 只展示工具名对应的动作，不展示工具参数、文件路径、命令、URL、prompt、代码或输出。
- `Bash` 当前只携带工具名，不得从事件中推断具体命令；命令级白名单与 shim 改造不属于本 delta。
- Pods 卡片、右侧活动流、Agent 详情头部和 Agents 明细表必须调用同一个纯步骤展示函数；
  步骤展示层不得改变 URL、筛选、状态枚举、主题或本地存储规则。

## 可验证行为（新增）

- 真实结果中的 `claude-code` `current_step="tool: WebSearch"` 打开 `/` 后，卡片步骤显示
  “正在联网搜索”，不显示 `▸ tool: WebSearch`。
- 真实结果中的 `claude-code` `current_step="tool: Read"` 打开 `/`、`/agents` 和 `/agent/:key`，
  三处均显示“正在读取文件”；切换英文后三处均显示 “Reading a file”。
- 对真实结果中的 Codex `tool: Bash`、`tool: apply_patch`、`tool: update_plan`、`tool: webrun`、
  `tool: view_image`，打开 `/` 或 `/agents` 时分别显示“正在执行命令/正在修改文件/正在更新计划/
  正在联网搜索/正在查看图片”，不得把 `webrun` 改显示为 `web.run`。
- 对真实结果中的 `mcp__Claude_Browser__navigate`、`mcp__chrome-devtools__take_screenshot` 与
  `mcp__chrome_devtools__take_screenshot`，打开页面时显示“正在打开网页/正在截图”；服务器原始
  连字符与下划线保留在 canonical 键中。
- 在真实已安装 hook 的 Claude Code Agent 中自然读取一个仓库文件后，打开 `/`，真实 `PreToolUse`
  产生的 `tool: Read` 必须显示“正在读取文件”；不能用手工 POST 替代该验收。
- 对未出现在查询结果中的非 MCP 工具，打开 `/` 与 `/agents`，页面显示原始工具文本，不出现错误中文；
  对未知但符合 MCP 结构的工具，页面显示“正在使用 {server} 的 {tool}”，不猜测具体动作。
- 同一 session 依次写入 `tool: Read`、`done/turn end`、`done/skill: demo` 后，打开 `/`、
  `/agents` 和 `/agent/:key`，步骤行不显示 `turn end`、`session end` 或 `skill: demo`，卡片状态显示“完成”。
- 右侧活动流不把 `turn end`、`session end` 或 Skill 扫描标记展示为步骤；普通工具事件仍可见。
- Skill 扫描后 `/skills` 仍能看到对应 Skill 使用记录，且身份卡的步骤来源没有被扫描行覆盖。
- 无前置非扫描步骤时，扫描行不会制造虚假步骤；卡片仍显示完成状态和空步骤回退。
- 对 `tool: Bash`，页面只显示“正在执行命令”，不展示或推断命令正文；命令级细分需要另一个 shim change。
