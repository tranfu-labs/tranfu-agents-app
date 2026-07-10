# spec-delta：ingest

## 新增规则：Codex rollout 双格式 Skill 使用补采

Codex shim MUST 在 `Stop` / `SessionEnd` 时按 `session_id` 定位本机会话 rollout，并从真实 shell
读取已安装 `SKILL.md` 的强信号中提取 Skill 名。解析 MUST 同时支持以下已知格式：

- 旧格式：`payload.type == "function_call"` 且 `payload.name == "exec_command"`；只检查
  可解码 `arguments` object 的字符串 `cmd` 字段。
- 新格式：`payload.type == "custom_tool_call"` 且 `payload.name == "exec"`；只检查
  `input` 中代码态、语法边界完整的 `tools.exec_command(...)` 调用，并只匹配其中可静态确认的字符串
  `cmd` 字段；不得扫描整个外层输入或 `workdir`、`justification` 等其它字段。

两种格式 MUST 复用同一已安装路径口径：直接位于 `.codex/skills/<name>/SKILL.md` 或
`.claude/skills/<name>/SKILL.md` 的路径。developer/user message、工具输出、`apply_patch`、非 shell
function call、作者仓库散落的 `SKILL.md` 和未知格式 MUST NOT 被计为 Skill 使用。
字符串或注释中的伪 `tools.exec_command(...)`、动态变量形式的 `cmd` 也 MUST NOT 被猜测为真实命令。

提取失败、rollout 缺失、JSON/调用边界破损或格式未知时 MUST 静默跳过，不得抛错或阻塞宿主。
现有 `TF_REPORT_SKILLS=0`、文件大小上限、Skill 名长度上限、文件内去重与服务端
`(session_id, skill, mode)` 幂等规则保持不变。

## 新增规则：无批量历史回填

该兼容修复 MUST NOT 提供或执行批量历史回填，也不得主动遍历未被当前 hook 事件指向的历史 session。
旧会话被续聊后，因正常 `Stop` / `SessionEnd` 对其完整 rollout 重扫而识别到此前 Skill 读取，属于允许的
当前会话自然补记；无需为排除该行为引入持久化游标、升级截止时间或额外本地状态。

## 可验证行为

- 旧 `function_call + exec_command` 读取 `.codex/skills/alpha/SKILL.md` → 提取 `alpha`。
- 新 `custom_tool_call + exec` 的 `tools.exec_command(...)` 读取同一路径 → 提取 `alpha`。
- 同一 rollout 用两种格式读取 `alpha` → 本地结果一个名字，服务端同一 session 仍只一条 used 记录。
- 新 `exec` 的 `tools.apply_patch(...)` 改写 `.codex/skills/edited/SKILL.md`，且无 shell 读取 → 不提取。
- 新 `exec` 同时包含读取 `alpha` 的 `tools.exec_command(...)` 和改写 `edited` 的
  `tools.apply_patch(...)` → 只提取 `alpha`。
- 新 `exec` 的字符串/注释伪造 `tools.exec_command(...)`，或真实调用仅在非 `cmd` 字段中含安装路径 → 不提取。
- 非 `exec_command` 的旧 function call 参数、developer catalog 或工具输出含安装路径 → 不提取。
- 未闭合的新格式调用、畸形 JSON、rollout 不存在或超过读取上限 → 静默返回已有安全结果或空结果。
- 部署后不运行任何批量历史扫描；没有再次活动的旧 session 不产生新记录，续聊旧 session 可在下一次
  正常结束事件中自然补记。
