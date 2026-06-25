# 规格 delta：ingest 规则 12 重写

替换 [openspec/specs/ingest/spec.md](../../../specs/ingest/spec.md) 现规则 12。

## 旧规则 12（待删）

> **Claude Code 斜杠命令也算 skill 调用。** Claude Code 把用户手敲的 `/<skill-name>` 写进 `UserPromptSubmit` 事件的 prompt 内容,标记为 `<command-name>/?<name></command-name>`。shim 侧(`tf_hook.py`)必须在 `UserPromptSubmit` 事件 prompt 头部解析此标记,命中时按 `skill` 字段上报;与既有 `PreToolUse + Skill` 工具调用同口径(会话×skill 去重,`TF_REPORT_SKILLS=0` 可关,skill 名提取失败不附加且不报错)。命中的事件其 `current_step` 必须改为 `skill: <name>`,与 `scan_codex_skills` 输出格式对齐。

旧规则的前置假设——"hook 收到的 prompt 含 `<command-name>` markup"——已在 2026-06-24 的实测中证伪：hook stdin 上的 `prompt` 字段是裸文本 `/openspec-driven-development ...`，markup 是 Claude Desktop 在 hook 调完之后才贴上去再写进 jsonl 的。

## 新规则 12

> **Claude Code 斜杠命令也算 skill 调用。**
>
> Claude Code（Desktop / CLI / IDE 入口下）在 hook 之后才把用户手敲的 `/<skill-name>` 展开成三件套
> ```
> <command-message>...</command-message>
> <command-name>/<name></command-name>
> <command-args>...</command-args>
> ```
> 写进 transcript jsonl（`~/.claude/projects/*.jsonl`）。**`UserPromptSubmit` hook 收到的 `prompt` 字段是裸文本，不含任何 markup**——所以不能从 `UserPromptSubmit` 解析，必须等 transcript 落盘后再扫。
>
> shim 侧（`tf_hook.py`）必须在 `Stop` 和 `SessionEnd` 事件中读 hook payload 携带的 `transcript_path`，扫描其中的 `<command-name>/?<name></command-name>` 标记，对每个唯一 skill 名按 `skill` 字段上报一次（`current_step` 为 `skill: <name>`，与 `scan_codex_skills` 输出对齐）。
>
> 约束与既有 `PreToolUse + Skill 工具` 同口径：
> - 会话×skill 去重（服务端 `(session_id, skill, mode)` 唯一约束兜底，客户端不持状态）
> - `TF_REPORT_SKILLS=0` 可关
> - `TF_RUNTIME != claude-code` 不触发
> - skill 名提取失败、jsonl 缺失 / 不可读、`transcript_path` 字段缺失 → 静默退出，不附加 skill、不阻塞主线程、不报错
> - 同会话内 Stop 多次触发产生的重复上报由服务端去重吞掉，是预期行为
