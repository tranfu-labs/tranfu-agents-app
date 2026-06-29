# 规格 delta：ingest 规则 12 补校验 + 可验证行为

## 规则 12（在归档 `2026-06-25-claude-slash-skill-usage-from-transcript` 重写后的版本上**追加**两个否定条件）

替换 [openspec/specs/ingest/spec.md](../../../specs/ingest/spec.md) 现规则 12，在「shim 侧（`tf_hook.py`）必须在 `Stop` 和 `SessionEnd` 事件中读 hook payload 携带的 `transcript_path`，扫描其中的 `<command-name>/?<name></command-name>` 标记……」之后、约束列表之前，插入以下两段：

> 扫描时必须做**位置校验**：行级 JSON 解码 transcript jsonl，仅当某行满足 `type == "user"` 且 `message.content`（支持 string 与 list-of-blocks 两种形态，list 形态取首个 `type=text` 块的 `text`）`lstrip()` 后**以 `<command-name>` 起头，或以 `<command-message>` 起头且紧跟 `<command-name>`**时，才取其首个 `<command-name>` 标记作为候选 skill 名。位置不在 user-message 起头斜杠命令三件套中的标记（含 assistant 文本、tool_result content、subagent prompt、文档/代码 fixture 引用等）一律忽略，不得上报——这类匹配在历史上是误报的主要来源。
>
> 扫描时还必须做**命名空间校验**：候选 skill 名归一化（去前导 `/`，按 `:` 切首段以折叠子命令）后，若落入 Claude Code 内置斜杠命令集合（含但不限于 `clear / compact / context / cost / config / agents / doctor / exit / quit / help / login / logout / memory / model / permissions / hooks / status / usage / mcp / vim / bug / release-notes / pr-comments / terminal-setup / add-dir / resume / migrate-installer / ide / bashes / output-style / microphone / fast`），不得上报。该集合由 shim 侧维护，Anthropic 未来扩展内置命令时同步追加。

约束列表（`TF_REPORT_SKILLS=0` 可关、`TF_RUNTIME != claude-code` 不触发、静默失败、服务端去重等）保持不变。

## 可验证行为（追加 2 条）

在 [openspec/specs/ingest/spec.md](../../../specs/ingest/spec.md) 「可验证行为（示例）」节末尾追加：

- `Stop` 事件 + transcript 内某行 `type=user` 且 `message.content` `lstrip()` 起头 `<command-message>clear</command-message>` 并紧跟 `<command-name>/clear</command-name>` → 命中内置命令黑名单，**不附加** `skill` 字段、`skill_uses` 表无新增。
- `Stop` 事件 + transcript 内某 `type=assistant` / `tool_result` content 含 `<command-name>verify</command-name>` 子串、但全文件无任何 `type=user` content 起头斜杠命令三件套记录 → 位置守门拒收，**不附加** `skill` 字段、`skill_uses` 表无新增。
- `Stop` 事件 + transcript 内某行 `type=user` 且 `message.content` `lstrip()` 起头 `<command-name>/output-style:new</command-name>` 或等价 `<command-message>` 三件套 → 归一化为 `output-style` 命中黑名单，**不附加** `skill` 字段。
- `Stop` 事件 + transcript 内某行 `type=user` 且 `message.content` 是 list-of-blocks `[{"type":"text","text":"<command-name>/foo-bar</command-name>..."}]` → 抓 `foo-bar` 上报一次。
