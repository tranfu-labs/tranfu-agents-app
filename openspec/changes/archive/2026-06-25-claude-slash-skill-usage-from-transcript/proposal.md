# 提案：claude-slash-skill-usage-from-transcript（Claude Code 斜杠 skill 改走 transcript 扫描）

- 状态：Draft（2026-06-24）
- 替代/纠偏：[archive/2026-06-23-claude-code-slash-skill-usage-from-prompt](../archive/2026-06-23-claude-code-slash-skill-usage-from-prompt/proposal.md)。实测推翻其前置假设，方向回滚 + 重定向。
- 关联：track-skill-usage、codex-skill-usage-from-rollout、ADR-0015（skill 按会话去重）、PROTOCOL.md §5、`openspec/specs/ingest/spec.md` 规则 12

## 背景

archive 那条 change 假设 Claude Code 把 `<command-name>/<skill>` 标记放进 `UserPromptSubmit` hook 的 `prompt` 字段，于是在 [shims/tf_hook.py](../../../shims/tf_hook.py) 加 regex 抓那个标记。**24 条单测全绿，线上 100% 漏报**——其中 Wing 一条手敲 `/openspec-driven-development` 的会话 `af071332` 服务端零记录。

2026-06-24 通过 `TF_DEBUG_HOOK=1` 一次性捕获 Claude Desktop 真实 hook payload，证伪了原假设：

| 数据源 | 时刻 | 内容 |
|---|---|---|
| jsonl 存档 `013ddf1d.jsonl` | 07:01:12.181Z | `<command-message>...</command-message>\n<command-name>/openspec-driven-development</command-name>\n<command-args>测试一下 debug 捕获</command-args>` |
| hook 进程 stdin | 07:01:12.332Z | `/openspec-driven-development  测试一下 debug 捕获`（**裸文本**，无任何 markup） |

同一次用户操作、151ms 时差，形态完全不同。Claude Desktop 是在 hook 调完之后才做 slash 展开 + 落盘 + 喂 LLM，hook 永远拿不到 markup。**hook 代码没问题**，错的是 archive change 当初的前置假设；那 24 条单测全是用手编的"伪 payload"喂的，没有端到端验过真实 desktop stdin。

放弃方向："改 regex 抓 prompt 开头的裸 `/<name>`"。误识风险高（`/api/foo`、`/etc/passwd`、`/根目录` 起头的普通消息会被识别成 skill），且跟 Codex 维护成本翻倍。

## 提案

走 **`Stop` / `SessionEnd` hook + 扫 transcript jsonl** 路径，沿用 [scan_codex_skills](../../../shims/tf_hook.py) 已经被验证过的同款模式：

- jsonl 到 Stop 时一定已完整落盘（Claude Desktop 内部展开 + 持久化都在 hook 之前完成）
- 直接读 `transcript_path` 字段指向的 jsonl，扫 `<command-name>/?<name></command-name>` markup 拿 skill 名
- 一个会话×skill 算一次（与 [ADR-0015] 同口径），服务端 `(session_id, skill, mode)` 唯一约束自动吞掉同 turn 重复扫描产生的重复上报
- archive change 加进去的 `_skill_from_slash_prompt` / `_SLASH_CMD_RE` / `_skill_name` 的 `UserPromptSubmit` 分支 / `resolve` 的 `UserPromptSubmit` step 改写——**全部死代码，整段删**
- 既有 `PreToolUse + Skill 工具` 分支保留（实时上报、模型 invoke 情况下生效；Stop 扫到的会重复但服务端去重，无害）

## 非目标

- 不回填历史漏报数据（数据源在用户本地 `~/.claude/projects/*.jsonl`，远端服务端拿不到；与上次决定一致）
- 不动 Codex `scan_codex_skills` 现有路径
- 不动 Hermes、OpenClaw、MCP 链路
- 不改协议字段表、`skill_uses` 表结构、服务端 ingest 代码

## 影响

| 模块 | 影响 |
|---|---|
| [shims/tf_hook.py](../../../shims/tf_hook.py) | + `CLAUDE_SCAN_EVENTS`、`_CLAUDE_SLASH_RE`、`scan_claude_skills(d)`；`main()` 尾部追加调用；删 `_SLASH_CMD_RE` / `_SLASH_PROMPT_HEAD` / `_skill_from_slash_prompt`；`_skill_name` 删 `UserPromptSubmit` 分支；`resolve()` 删 `UserPromptSubmit` 改 step 那段 |
| [tests/test_hook.py](../../../tests/test_hook.py) | 删 6 条 archive 时加的 `<command-name>` 假定 UserPromptSubmit 用例（前提错）；新增 6 条 `scan_claude_skills` 用例（用真实 desktop fixture jsonl + 真实裸文本 hook payload） |
| [openspec/specs/ingest/spec.md](../../../openspec/specs/ingest/spec.md) 规则 12 | 重写：Claude Code 斜杠 skill 来自 transcript jsonl 扫描，不是 prompt 头部 markup 解析 |
| 数据看板 | 升级后斜杠命令开始正常计入（行为对用户而言与 archive 那条目标一致，实现路径不同） |
| 服务端 / 协议 / DB | 零改动 |
