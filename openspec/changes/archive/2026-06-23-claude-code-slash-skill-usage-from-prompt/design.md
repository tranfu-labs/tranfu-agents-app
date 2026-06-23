# 设计：claude-code-slash-skill-usage-from-prompt

## 方案

### `_skill_name(d, ev, tool)` 拆 case split

现有逻辑（[shims/tf_hook.py:66-77](../../../shims/tf_hook.py)）把"PRE_TOOL + Skill 工具"作为唯一入口，UserPromptSubmit 直接早退。改成显式分支：

```
if TF_REPORT_SKILLS == "0": return ""
if ev == "UserPromptSubmit":
    return _skill_from_slash_prompt(d.get("prompt"))
if ev in PRE_TOOL and str(tool).casefold() in SKILL_TOOLS:
    return _skill_from_tool_input(d)   # 原 _name_from(payload) 逻辑搬过来
return ""
```

两条路径的输入形态、置信度、后续扩展（Codex / Hermes 各自的斜杠格式可能不同）完全不同，case split 比 `or` 拼接清晰且方便扩展。

### `_skill_from_slash_prompt(prompt)` 新增函数

- 输入：`prompt` 可能是 str / None / dict / 其他；非 str 直接返回 `""`。
- 截取**前 1024 字节**（Claude Code 把 `<command-name>` 标记塞在 prompt 头部；限位置防异常 payload 误触发）。
- `re.search(r"<command-name>/?([\w-]{2,80})</command-name>", head)` 抽 skill 名。
- 二次校验：拒绝纯数字、首尾不能是 `-` 或 `_`、不能包含连续 `--`（保守的合规名校验）。
- 返回字符串（命中）或 `""`（未命中）。

### `resolve()` UserPromptSubmit 分支改 step

现状：UserPromptSubmit 进 `resolve()` 后，因为 `ev not in PRE_TOOL` 也 `not in POST_TOOL`，step 保持 MAP 里的默认值 `"prompt"`。

改动：在 `_skill_name(...)` 返回非空时（且 `ev == "UserPromptSubmit"`），把 step 改成 `f"skill: {name}"`——格式与 [`scan_codex_skills` 第 178 行](../../../shims/tf_hook.py)对齐。

```
skill = _skill_name(d, ev, tool)
if skill and ev == "UserPromptSubmit":
    step = f"skill: {skill}"
# 后续 args 拼装不变
```

这一改让事件层面也能直接看出"这条 prompt 是个 skill 调用"，而不是光秃秃的 `current_step='prompt'`。

## 权衡

### 为什么不加 `--skill-source slash|tool` 区分来源

讨论中提出过给上报加 source 字段区分"用户手敲"和"模型 invoke"。用户决定不区分——两者本质都是 skill 调用，分开统计反而让 dashboard 复杂。如果以后真有需要（如评估 skill 描述质量），从 step 字符串（`skill:` 来自斜杠 / `tool: Skill` 来自模型）也能间接反推，不必现在加字段。

### 为什么不一并修 Codex 斜杠命令

Codex 走 `scan_codex_skills` 兜底（[shims/tf_hook.py:159-179](../../../shims/tf_hook.py)），扫的是 rollout transcript 里的 `function_call`。Codex 斜杠命令的 transcript 格式与 Claude Code 完全不同，需要先抓真实样本验证。混在这个 change 里会拖慢交付，留下一个 change。

### 为什么不做历史回填

回填的源头是用户本地 `~/.claude/projects/*.jsonl`，远端 server（Coolify docker）看不到这份数据。任何"服务端按钮"都做不到回填，只能走"用户本地 CLI / Claude Code 跑脚本"路径。用户决定不做（漏报已修复，趋势统计向前看更重要）。

### regex 边界：为什么限前 1024 字节 + 名字校验

`<command-name>` 标记几乎一定出现在 prompt 头部（Claude Code 系统模板加在最前面）。限前 1024 字节防御两件事：

1. 用户在 prompt 正文里"复述" `<command-name>` 字面量被误识别。
2. 异常长 prompt（贴大块代码）的 regex 性能退化。

名字校验是配合后端 `MAX_SKILL_NAME = 160`（[server/app.py:79](../../../server/app.py)）的客户端预过滤，把明显异常的（纯数字、超长、连续连字符）挡在上报前。

## 风险

| 风险 | 缓解 |
|---|---|
| 用户在 prompt 正文里写 `<command-name>` 字面量被误识别 | 限前 1024 字节 + 名字校验；真实场景中正文出现这串字符的概率极低 |
| 短期内 dashboard 数值"突然变大"被误读为统计 bug | 在 commit message + AGENTS.md 简要说明：升级后斜杠 skill 调用开始正常计入 |
| Hermes 或未来其他 runtime 也走 `UserPromptSubmit` 但格式不同 | 当前只针对 `UserPromptSubmit` 事件且只识别 `<command-name>` 标记；Hermes 走 `pre_llm_call`，不在本次扩展分支命中范围 |

## 回滚

改动局限在 `shims/tf_hook.py` 单文件。回滚 = 还原该文件 + 触发一次 self-update 覆盖本地 `~/.tranfu/tf_hook.py`。无数据迁移、无服务端动作、无 `skill_uses` 表脏数据（INSERT 走原有去重路径）。
