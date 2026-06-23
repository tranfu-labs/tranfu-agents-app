# 提案：claude-code-slash-skill-usage-from-prompt（Claude Code 斜杠命令 skill 使用——从 prompt 补采）

- 状态：Accepted（已实现并通过 24 条 hook 契约测试，2026-06-23）
- 关联：track-skill-usage、codex-skill-usage-from-rollout、ADR-0015（skill 按会话去重）、PROTOCOL.md §5
- 后续：Codex 路径的斜杠命令漏报修复留下一个 change

## 背景

track-skill-usage 打通的 Claude Code 采集链路只在一种情况上报：`PreToolUse` 事件里 `tool_name == "Skill"`、`tool_input` 带 skill 名。这是**模型主动 invoke** 一个 skill 时的形态。

但 Claude Code 还有另一条触发路径：**用户手敲 `/<skill-name>` 斜杠命令**。这条路径走的是 `UserPromptSubmit` 事件，skill 标识夹在 prompt 内容里的 `<command-name>/?<name></command-name>` 标记，**根本不会触发 `Skill` 工具调用**，所以 `_skill_name()`（[shims/tf_hook.py:66-77](../../../shims/tf_hook.py)）永远返回空字符串。

实证：用户报告昨天手敲 `/openspec-driven-development` 22 次 + 模型 invoke `Skill` 工具 3 次 = 共 25 次，dashboard 上只显示 3 次。22 条全数漏报。`MAP["UserPromptSubmit"]` 虽已在监听（上报 `status=running, current_step=prompt`），但没顺手抽 skill 名。

## 提案

让 **Claude Code 斜杠命令** 进入既有的会话×skill 统计，口径与 [ADR-0015] 完全一致（一个会话×skill 算一次、永久保留、`TF_REPORT_SKILLS=0` 可关）。

- **零服务端 / 零协议改动**：复用既有 `skill` 事件字段与 `skill_uses` 落库规则。
- **零新链路**：直接扩展 `tf_hook.py` 现有 `_skill_name` + `resolve()`，加一个分支处理 `UserPromptSubmit`。
- 不区分「斜杠 invoke」与「Skill 工具 invoke」的来源，都按 skill 调用统计。

## 非目标

- 不回填历史漏报数据（数据源在用户本地 `~/.claude/projects/*.jsonl`，远端服务器看不到；与用户讨论后决定不做回填工具）。
- 不动 Codex `scan_codex_skills` 兜底逻辑（Codex 自身斜杠命令是否同样漏报留下个 change）。
- 不动 Hermes / OpenClaw 链路。
- 不动协议字段表、`skill_uses` 表结构、服务端 ingest 任何代码。

## 影响

| 模块 | 影响 |
|---|---|
| `shims/tf_hook.py` | `_skill_name` 拆 case split + 新增 `_skill_from_slash_prompt`；`resolve()` 在命中时把 step 从 `"prompt"` 改成 `f"skill: <name>"` |
| `tests/test_hook.py` | 新增 6 条用例覆盖斜杠命令解析、异常名拒绝、`TF_REPORT_SKILLS=0` 仍生效、PreToolUse 不回归 |
| `openspec/specs/ingest/spec.md` | 加一条规则：Claude Code skill 采集还包括 UserPromptSubmit + `<command-name>` 解析 |
| 服务端 / 协议 / 数据库 | 零改动 |
| Dashboard | 立竿见影：升级 hook 后斜杠命令直接进 `skill_uses`，排行/统计不再低估 |
