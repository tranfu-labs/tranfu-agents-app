# 提案：validate-claude-slash-skill-names

## 背景

2026-06-25 归档的 `claude-slash-skill-usage-from-transcript` 把 Claude Code 斜杠命令的 skill 采集改成「Stop / SessionEnd 时扫 transcript jsonl 抓 `<command-name>` 标记」。**采得到了，但没做任何校验**——任何字符串里出现的 `<command-name>X</command-name>` 子串都被当真实斜杠命令上报。

实测两类误报混进了上报：

1. **fixture / 文档引用文本**：本仓库 `tests/test_hook.py` 自己写的 `<command-name>verify</command-name>` 等 fixture，在 agent 编辑该文件时整段文本进了 transcript 的 user message / tool_result，被 hook 自己倒扫了一遍。grep 本机 tranfu-agents-app 项目 transcript：`verify`（无前导 `/`）出现 24 次，全部来自测试 fixture。
2. **Claude Code 内置斜杠命令**：`/clear、/compact、/context、/login、/model、/memory、/usage、/help` 等。客户端在 hook 之后展开内置命令也会写成 `<command-name>` 三件套塞进 transcript。它们不是 skill，但被一并上报到 `skill_uses`，污染 SKILLS 看板。用户报例：`usage`、`verify`。

证据（真实 transcript 的斜杠命令长这样）：

```jsonl
{"type":"user","message":{"content":"<command-name>/clear</command-name>\n            <command-message>clear</command-message>\n            <command-args></command-args>"}, ...}
```

`type=user`，`message.content` 字符串 `lstrip()` 后位于**行首斜杠命令三件套**中；真实 transcript 存在
`<command-name>` 起头和 `<command-message>` 起头后紧跟 `<command-name>` 两种顺序。其余位置的
`<command-name>` 都是引用 / fixture / 工具输出。

## 提案

给 `scan_claude_skills` 加两层校验：

- **位置校验**：行级 JSON 解码，只在 `type=user` 且 `message.content`（兼容 string / list-of-blocks）`lstrip()` 后以真实斜杠命令三件套起头的字符串里抓**首个**标记。
- **命名空间校验**：维护 Claude Code 内置斜杠命令黑名单，归一化（去前导 `/`、按 `:` 切首段）后命中即不上报。

`openspec/specs/ingest/spec.md` 规则 12 同步补两个否定条件，新增 2 条「可验证行为」覆盖这两类否定例。

## 影响

- **ingest 域**：`shims/tf_hook.py` `scan_claude_skills` 改写；行为变更见 `spec-delta/ingest.md`。
- **客户端**：内置命令与 fixture 不再上报，真实自定义 skill 上报路径不变。
- **服务端**：不动，规则 4 的 `(session_id, skill, mode)` 唯一约束兜底足够。
- **历史数据**：已被错记入库的 `skill_uses` / `skills_seen`（如 `verify`、`usage`、`clear`、`model` 等）**本次只堵源、不回滚**——要清单独起 change，仿 `admin-data-cleanup` 先例。
- **关联归档**：`archive/2026-06-25-claude-slash-skill-usage-from-transcript/`（建立 transcript 扫法），本次给那条加上"校验层"。
