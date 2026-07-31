# 任务：humanize-agent-steps

## 方案与实现任务

- [x] 在 `server/routes/board.py` 为 `_snapshot` 增加同 identity + session 的最近非扫描步骤来源，
      仅排除 `status=done` 且 `current_step` 以 `skill:` 开头的 Skill 扫描行；通过同一条 SQL 的
      CTE/window function 一次选出各 session 最近非扫描行，禁止按卡片循环查询；不改事件写入、统计、时长和 schema。
- [x] 新增前端纯展示模块 `frontend/src/lib/agentStep.ts`（或同职责文件）：
      按 runtime 分区只映射生产库查询已真实出现的 Claude Code / Codex 精确工具键；Codex 键必须
      按入库原形登记（例如 `webrun`、`image_genimagegen`、`collaborationwait_agent`），不得改写成
      带点号的推测名称；MCP 按 `mcp__<server>__<tool>` 结构化处理，保留服务器原始连字符/下划线；
      未出现的 runtime/工具、Hermes 候选和未知非 MCP 工具走原文回退。
- [x] 将纯函数接入 `Board.tsx` 的 Agent 卡片与 Feed、`AgentDetail.tsx`、
      `AgentDirectoryTable.tsx`；所有步骤入口只走同一个展示函数，状态 fallback 保持现有 i18n。
- [x] 在 `tests/test_board.py` 增加扫描行覆盖：单个扫描行、连续扫描行、无前置可展示步骤，
      并断言 Skill 统计和完成状态不受影响。
- [x] 新增 `frontend/src/lib/agentStep.test.ts`，覆盖生产结果中的 Claude/Codex 精确键、MCP 两种
      `chrome-devtools` 服务器拼写、未知 MCP 结构化回退、Hermes/未出现工具原文回退、完成式、生命周期、
      `skill:` 扫描标记、普通自定义步骤和 zh/en。
- [x] 在前端单测入口注册新测试，并增加入口契约断言，防止展示入口漏接或各自实现映射。
- [x] 修复完成态卡片回退历史工具步骤仍显示“正在…”的问题；已知工具在 `status=done` 时显示完成式，
      并移除 API 响应中的 SQL 临时字段 `display_current_step`。
- [x] 证据记录：把生产库 `events.current_step` 分布查询中已收到的结果落入本 change 审计记录；全量
      结果作为并行长尾审计项，不阻塞实现。Claude 官方自家工具
      `Glob` / `Grep` / `TodoWrite` / `NotebookEdit` 与历史别名 `Task` 一并收录，未命中时原文回退；
      明确 `tf_hook.py` / `tf_report.py` / `ingest.py` 不做 Codex 分隔符清洗，不把 `cf.terminal` 或
      Hermes `terminal` 当作工具证据。

## 文档与事实源

- [x] 新增 `spec-delta/board/spec.md`，记录服务端步骤来源、前端统一展示、runtime 映射白名单和回退规则。
- [x] 更新 `openspec/specs/board/spec.md`、`docs/architecture/module-map.md`、根 `AGENTS.md` 的对应展示约束；
      明确“不改协议、不展示工具对象内容”。
- [x] 更新 `docs/wireframes/pages/board.md` 与 `docs/wireframes/pages/agent-detail.md` 中的步骤说明，
      把 `current_step` 标成“人话化步骤/未知原文回退”，不改变页面结构或路由。

## 自动化验证

- [x] `python -m py_compile server/*.py server/routes/*.py`。
- [x] `python -m pytest -q tests/test_board.py tests/test_agents_dashboard.py`（51 passed）。
- [x] `npm --prefix frontend run test:unit`（94 passed）。
- [x] `npm --prefix frontend run build`。
- [x] `python -m pytest -q` 全量回归（412 passed），并按仓库要求运行 coverage（server 总覆盖 96%）。

## 真实运行验收

- [x] 本地启动 FastAPI/生产 SPA；真实已安装 hook 的 Claude Code Agent 自然读取仓库文件后，真实打开 `/`：
      活动流观察到 `PreToolUse` 的 `tool: Read` 显示“正在读取文件”，随后真实 `PostToolUse` 的卡片显示
      “已完成读取文件”，全程不显示 `▸ tool: Read`。
- [x] 真实打开 `/agents` 和 `/agent/:key`：同一真实 Agent 的步骤文案均显示“已完成读取文件”，与 `/` 一致。
- [x] QA 在隔离 SQLite + 真实生产分布工具键的 SPA 验收中确认 Codex `tool: Bash`、`tool: apply_patch`、
      `tool: update_plan`、`tool: webrun`、`tool: view_image` 均显示对应人话，且 `webrun` 未被改写成 `web.run`。
- [x] QA 在真实页面中确认 `mcp__Claude_Browser__navigate`、`mcp__chrome-devtools__take_screenshot` 与
      `mcp__chrome_devtools__take_screenshot` 的语义一致，canonical 连字符/下划线保留。
- [x] `WebSearch` 条件项由纯函数中英文测试覆盖；本次 QA 自然运行未触发该工具，因此没有把手工事件冒充
      Claude Code 自然触发证据。
- [x] QA 确认未知非 MCP 工具保留原文，未知 MCP 工具显示结构化“正在使用 {server} 的 {tool}”。
- [x] QA 与本次隔离 SPA 回归均确认 `done + skill:` 后 `/`、`/agents`、`/agent/:key` 不展示生命周期或
      Skill 扫描标记；本次补充确认历史工具步骤显示完成式“已完成查看图片”。
- [x] 检查右侧活动流：真实 `session end` 只显示完成状态，普通 `tool: Read` 事件显示“正在读取文件”。
- [x] 切换中英文重复观察真实 Claude `Read` 事件：中文显示“已完成读取文件”，英文显示 “Finished reading a file”。
- [x] QA 触发 Skill 扫描后确认 `/skills` 仍有 `qa-skill` 记录，且卡片步骤未被扫描标记覆盖。
- [x] QA 确认 `tool: Bash` 仅显示“正在执行命令”，不包含命令正文；命令级细分与白名单另开 shim
      变更，不在本 change 内实现。

## 反思与收尾

- [x] 对照本 change 的非目标逐条确认：未改 `shims/`、协议、schema、终态语义、质量和活跃时长。
- [x] 将通过实现和验证的 spec delta 合并回 `openspec/specs/board/spec.md`。
- [x] QA 已复核本次 `done + 历史工具步骤` 修复；按项目流程归档 change。
