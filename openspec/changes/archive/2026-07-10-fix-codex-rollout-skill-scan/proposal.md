# 变更提案：fix-codex-rollout-skill-scan

- 状态：Accepted（已实现并验证，2026-07-10）
- 关联：ADR-0015（Skill 使用按会话去重）、ADR-0016（Codex 从 rollout 补采）、`codex-skill-usage-from-rollout`

## 背景 / 问题

Codex Skill 使用补采当前只识别 rollout 中的旧格式：
`payload.type == "function_call"`，并从 `arguments` 中匹配读取
`.codex/skills/<name>/SKILL.md` 或 `.claude/skills/<name>/SKILL.md` 的记录。

Codex Desktop `0.144.0-alpha.4` 已把常规工具编排写成
`payload.type == "custom_tool_call"`、`name == "exec"`，真实 shell 调用位于
`input` 内的 `tools.exec_command(...)`。现有扫描器会跳过整条记录，因此 Desktop 主会话即使
实际读取并遵循了 Skill，也不会进入 `skill_uses`；旧 `codex_exec 0.135.0` 仍写
`function_call + exec_command`，所以形成“旧执行器能统计、Desktop 主会话漏报”的分裂口径。

## 目标

- 同时兼容旧 `function_call + exec_command` 与新
  `custom_tool_call + exec + tools.exec_command(...)` rollout 格式。
- 两种格式复用同一套已安装 Skill 路径识别、名称截断、文件内去重和会话级幂等口径。
- 新格式只检查真实 `tools.exec_command(...)` 调用片段，不因外层 `exec` 中的
  `apply_patch`、普通字符串、工具输出或技能目录清单而误报。
- 保持 shim 失败静默、标准库限定、`TF_REPORT_SKILLS=0`、`MAX_BYTES` 与现有上报协议不变。

## 非目标

- 不提供、不执行批量历史回填，也不新增历史扫描或补发命令。
- 不阻止旧会话在被续聊后，由正常 `Stop` / `SessionEnd` 重扫而自然补记。
- 不改变“一个 `session_id × skill × mode` 只计一次”的服务端口径。
- 不扩展 Skill 安装路径口径；本次仍只认直接位于 `.codex/skills/` 或
  `.claude/skills/` 下的 `SKILL.md`，不顺带接入插件缓存等其它目录。
- 不改 Claude Code、Hermes、OpenClaw 的 Skill 采集链路，不改服务端、数据库、协议字段或前端。

## 提案

在 `shims/tf_rollout_scan.py` 增加一层保守的“命令片段提取”：

1. 旧格式仅从 `function_call` 且工具名为 `exec_command` 的 `arguments.cmd` 提取命令。
2. 新格式仅从 `custom_tool_call` 且工具名为 `exec` 的 `input` 中，提取语法边界完整的
   `tools.exec_command(...)` 调用，再只取其中可静态确认的字符串 `cmd` 字段；其它字段与嵌套工具调用一律忽略。
3. 将提取出的命令片段统一交给现有 `SKILL_RE`，结果继续用集合去重并排序返回。
4. 解析失败或格式未知时返回空结果，不向宿主抛错。

## 影响

- `shims/tf_rollout_scan.py`：增加旧/新格式命令片段提取与统一匹配。
- `tests/test_rollout_scan.py`：加入 Codex Desktop `0.144` 脱敏 fixture、兼容与误报回归测试。
- `openspec/specs/ingest/spec.md`：归档时补充 Codex rollout 双格式采集规则与无批量回填边界。
- `docs/adr/0016-codex-skill-usage-from-rollout.md`：把旧版单格式决策更新为兼容格式族，并记录新格式的严格守门。
- `docs/architecture/module-map.md`、根 `AGENTS.md`：实现时按需同步 shim 职责说明。

无 UI 或页面流转变化，不创建 `wireframes.md`。
