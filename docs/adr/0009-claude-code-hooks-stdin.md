# ADR-0009 Claude Code 钩子用 stdin 分发器,不依赖环境变量取上下文

- 状态:Accepted
## 背景
Claude Code 钩子把事件以 **JSON 经 stdin** 传给命令(含 `session_id`、`hook_event_name`、`tool_name`);
早期设想用 `$CLAUDE_SESSION_ID`/`$CLAUDE_USER_PROMPT` 是错误的。
## 决策
提供 `shims/tf_hook.py`:读 stdin 事件 JSON → 按 `hook_event_name` 映射状态
(SessionStart→started+profile、UserPromptSubmit→running、PreToolUse→running(tool: 名)、Stop/SessionEnd→done)→
用事件里的 `session_id` 调 `tf_report.py`。在 `~/.claude/settings.json` 的 5 个事件上都挂这一个脚本。
身份/密钥从启动 claude 的 shell 环境继承(`TF_*`),不写进 settings.json。钩子绝不阻塞会话。
## 后果
- ✅ 自动上报实时步骤;同会话事件共享 session_id → 一张卡。
- ⚠️ 若从非终端方式启动 claude 取不到 `TF_*`,需用 settings.json 的 `env` 块兜底。
- 约束:禁止回退到用环境变量取钩子上下文。
