# ADR-0016 Codex skill 使用从会话文件补采

- 状态:Accepted
- 关联:ADR-0009(钩子 stdin)、ADR-0015(skill 按会话去重)、PROTOCOL.md §5 §6、
  openspec/changes/codex-skill-usage-from-rollout、
  openspec/changes/archive/2026-07-10-fix-codex-rollout-skill-scan

## 背景 / 问题

ADR-0015 / track-skill-usage 的采集只覆盖 Claude Code:`PreToolUse` 里 `tool_name=="Skill"`
带 skill 名。Codex **不把 skill 触发暴露成 `Skill` 工具调用**,其公开 hooks 支持范围明确不含
非 shell / 非 MCP 工具,因此 Codex 会话用过的 skill 永远进不了排行。需要一条不依赖
"skill=工具调用"假设的 Codex 采集路径。

## 决策

- **从源文件补采,而非 hook 内识别命令**:Codex 把每个会话写成磁盘 rollout
  (`$CODEX_HOME/sessions/…/rollout-*-<sid>.jsonl`);在 `Stop`/`SessionEnd` 钩子里解析该文件。
  理由:rollout 是 Codex 落盘的完整事实,轮次结束时读取必已 flush,一次扫描覆盖整轮,
  且为未来从源文件提取更多信号留同一入口。
- **兼容已知 rollout 格式族,只认静态 shell 强信号**:旧 `codex_exec 0.135` 形态只取
  `payload.type=="function_call" && name=="exec_command"` 的 `arguments.cmd`;Codex Desktop
  `0.144` 形态只取 `payload.type=="custom_tool_call" && name=="exec"` 中代码态真实
  `tools.exec_command(...)` 调用的静态字符串 `cmd` 字段。两者再匹配已装目录
  (`.codex/` 或 `.claude/` 点目录前缀)下 `skills/<名>/SKILL.md`。提示词点名、技能目录注入、
  工具输出回显、字符串/注释伪调用、动态 `cmd`、非命令字段、`apply_patch` 改写、作者仓库散落的
  SKILL.md 一律不计。宁缺毋错,与现有统计口径一致。
- **复用既有契约,零服务端 / 零协议改动**:提取到的 skill 名经 `tf_report.py --skill` 走既有事件
  与 `skill_uses` 落库;口径、幂等、永久保留、`TF_REPORT_SKILLS=0` 开关全部沿用 ADR-0015。
- **每轮重扫,靠服务端去重**:同一增长中的 rollout 每轮被重扫,`(session_id, skill)` 唯一键保证不重复计数。
- **不做批量历史回填**:不提供或执行批量历史扫描,排行从部署后自然增长。旧会话被续聊并产生正常
  `Stop`/`SessionEnd` 时,完整 rollout 重扫可能自然补记此前读取;不为排除该行为增加本地游标或升级截止点。

## 后果

- ✅ Codex 会话用过的 skill 进入与 Claude Code 同一套排行,口径一致、无需服务端改动。
- ✅ 失败静默:rollout 格式变化 / 文件缺失只表现为"该 runtime 无数据",绝不打断宿主会话。
- ⚠️ 依赖 Codex rollout 私有格式(已锁定旧 `codex_exec 0.135` 与 Codex Desktop `0.144`),升级仍可能
  破解析——靠按版本脱敏 fixture、保守解析、真实 `--print` 验证与失败静默兜底。
- ⚠️ shim 在 Codex 下会本地读取会话文件以提取 skill 名(仍只上报名,不上报参数 / prompt / 代码 /
  输出);已在 PROTOCOL.md §5 注明。
- ⚠️ 每轮重扫有重复读盘开销;`MAX_BYTES` 上限避免超大会话拖过 hook 5s 超时。
- ⚠️ 子代理独立 `session_id` → skill 独立计数,与 ADR-0015 同;未来读侧按 parent 链归并。
