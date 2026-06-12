# ADR-0017 Hermes skill 使用从 `skill_view` 工具调用采集

- 状态:Accepted
- 关联:ADR-0009(钩子 stdin)、ADR-0015(skill 按会话去重)、ADR-0016(Codex 从源文件补采)、
  PROTOCOL.md §5、openspec/changes/hermes-skill-usage-from-skill-view

## 背景 / 问题

Claude Code 的 skill 使用可以从 `PreToolUse` 的 `Skill` 工具调用采集;Codex 不暴露 skill 工具调用,
因此只能在轮末解析本机会话 rollout。Hermes 不同:它的 skill 渐进式披露通过 `skill_view(name)`
加载正文,且 `pre_tool_call` 钩子在工具执行前提供 `tool_name` 与 `tool_input`。

如果不识别这条强信号,Hermes 会话用过的 skill 不会进入团队 Skill 使用排行。

## 决策

- Hermes skill 使用在钩子内识别,不走 Codex 式源文件扫描。
- `tf_hook.py` 只在 `pre_tool_call` / `PreToolUse` 上统计 skill,并只认可工具名
  `skill` 与 `skill_view`。
- Hermes 下从 `tool_input.name` 等既有名称字段提取 skill 名,经 `tf_report.py --skill` 复用现有
  `skill` 事件字段和服务端 `(session_id, skill)` 幂等落库。
- 不计 `skills_list`。列目录只是发现可用 skill,不是使用。
- 不计 `skill_manage`。它代表编写/维护 skill,不是加载使用。
- 沿用 `TF_REPORT_SKILLS=0` 关闭开关;不得上报 skill 参数、prompt、代码、输出或正文。

## 后果

- ✅ Hermes 与 Claude Code 共用同一条钩子内采集路径,服务端和协议无需新增字段。
- ✅ `skill_view(name, path)` 读取引用文件时仍只上报同一个 skill 名,服务端按会话去重不会放大计数。
- ✅ 失败静默:字段缺失或工具名变化只表现为该次无法识别 skill,不得影响宿主 agent。
- ⚠️ 依赖 Hermes `pre_tool_call` payload 中工具名为 `skill_view` 且 skill 名在工具输入里;若未来版本改名,
  只需扩展 `tf_hook.py` 的认可工具名集合或名称提取键。
- ⚠️ 如果某些 Hermes slash command 在框架层直接注入 skill 正文而不触发 `skill_view`,本口径不会采集,
  需另行评估新的强信号来源。
