# 设计：validate-claude-slash-skill-names

## 方案

`shims/tf_hook.py` `scan_claude_skills` 改写为「行级 JSON 解码 + 位置守门 + 名字归一化 + 黑名单过滤」四步：

### 1. 行级 JSON 解码

之前是按文本行 finditer 扫整行，现在每行 `json.loads`。解析失败 → 跳过该行（与之前 `errors='replace'` 的容错口径一致，不阻塞）。

### 2. 位置守门（拒 fixture）

只承认真实斜杠命令展开形态：

- 仅看 `type == "user"` 的记录。其余 `assistant` / `tool_result` / `summary` / `subagent_*` 等一律忽略。
- 取 `message.content`，**兼容两种形态**：
  - 字符串：直接看本身。
  - list-of-blocks（Claude API 兼容形态）：取首个 `type=text` 块的 `text` 字段。
- `lstrip()` 后必须**以真实斜杠命令三件套起头**：接受 `<command-name>` 起头，也接受真实 transcript 中常见的 `<command-message>...</command-message>` 后紧跟 `<command-name>`。
- 仅抓**首个** `<command-name>` 标记。后续标记一律忽略——防 message 后续粘连其他 fixture。

### 3. 名字归一化

抓到原始名后：

- `lstrip("/")` 去前导斜杠。
- 按 `:` 切首段（`output-style:new` → `output-style`，`output-style:edit` → `output-style`），其余字段不动。
- 现有的「数字 / 首尾 `-_` / `--` / 空」过滤保留。

### 4. 内置命令黑名单过滤

硬编码常量 `_CLAUDE_BUILTIN_SLASH`（frozenset）：

```
clear, compact, context, cost, config, agents, doctor, exit, quit, help,
login, logout, memory, model, permissions, hooks, status, usage, mcp, vim,
bug, release-notes, pr-comments, pr_comments, terminal-setup, add-dir,
resume, migrate-installer, ide, bashes, output-style, microphone, fast
```

归一化后的名字 `in` 黑名单 → 跳过；否则进入既有的 `_run_report` 上报路径。

## 权衡

### 黑名单 vs 白名单

**选黑名单**：实现单文件常量、维护成本低；新增 / 卸载自定义 skill 立即生效；与 spec 规则 12 现行口径「用户自定义 skill 都上报」一致。

**不选白名单**：要扫 `~/.claude/skills/`、项目 `.claude/skills/`、各插件 `<plugin>/skills/`、还要照顾 plugin 注册表读法——实现复杂；且新装 skill 在 hook 刷新前会**首跑漏报**，与"装上立刻能跑"的体感冲突。代价：Anthropic 未来新增内置命令需要补黑名单——可接受，节奏低且与 hook 升级一起走自更新链路。

### 黑名单只列「纯客户端 UI 命令」，不列同名 skill

Anthropic 把一些功能既做成内置 skill（`anthropic-skills:init`、`verify`、`review`、`security-review`、`release`、`code-review`、`simplify`、`run`、`loop`、`schedule`、`claude-api`、`update-config`、`keybindings-help`、`fewer-permission-prompts` 等），用户敲 `/init`、`/verify` 时**确实**是 skill 调用，应该上报。这些**不放黑名单**。

黑名单只收**纯客户端 UI 命令**——即不存在对应 skill、由 Claude Code 客户端自行处理的命令（`/clear / compact / login / model / memory / usage / help / cost / status / config / agents / doctor / hooks / permissions / exit / quit / vim / mcp / output-style / add-dir / resume / ide / bashes / microphone / fast / bug / release-notes / pr-comments / terminal-setup / migrate-installer`）。判定方法：用户敲它**不会**触发任何 SKILL.md 加载——纯 CLI 内部行为。

冲突场景（用户错装了自己的同名 skill `clear`）的优先级：**黑名单优先**。代价是用户给 skill 起名时应避开内置 UI 命令——这本就是合理约束。

### 位置守门用「起头三件套」而不是整行扫

实测真实 user message 的斜杠展开总在 user-message 起头位置，但三件套顺序可能是
`<command-name>` → `<command-message>`，也可能是 `<command-message>` → `<command-name>`。因此只守
「user-message 起头的斜杠命令三件套」并取首个 `<command-name>`：fixture/引用不会处在这个位置，
tool_result / assistant 文本也先被 `type` 与 block 类型排除。

### list-of-blocks 形态兜底

Claude Code transcript 主流是 `content: string`，但已知有少量 list-of-blocks 形态（来自更早版本 / 特定客户端）。多花 5 行兼容 vs 漏报某些客户端的真实斜杠命令——兼容更稳。

## 风险

- **黑名单不全 → 漏过某个内置命令**：影响是某个内置命令名错入 `skill_uses`。可观测、可补——上线后看 SKILLS 看板若出现陌生短名，加进黑名单即可。
- **未来 Claude Code 把斜杠命令的 transcript 格式改了**：会让 Layer 1 起头校验失效（变成"不上报任何斜杠 skill"）。比之前"乱上报"安全。可通过端到端用例发现，再适配。
- **回滚**：单 commit 改 `shims/tf_hook.py` + `tests/test_hook.py` + `openspec/specs/ingest/spec.md` 三个文件，回滚 = revert 即可，无 schema 迁移。

## 不在本次范围

- 历史脏数据清理（`skill_uses` / `skills_seen` 已被错记的内置命令 / fixture 名）。本次只堵源。要清单独起 change，仿 `archive/admin-data-cleanup` 写一个一次性 SQL 迁移 + 后台触发任务。
- 服务端 `(session_id, skill, mode)` 唯一约束不动——客户端少送脏数据后服务端自然干净。
- Codex 链路 (`scan_codex_skills`) 不在影响面——Codex 走 `tf_rollout_scan.scan_session` 直接读 SKILL.md 路径，本就有天然白名单。
