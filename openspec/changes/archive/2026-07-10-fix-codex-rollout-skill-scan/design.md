# 设计：fix-codex-rollout-skill-scan

## 已确认决策

1. **格式兼容**：旧 `function_call` 与新 `custom_tool_call` 必须同时保留，不能用新格式替换旧格式。
2. **强信号不放宽**：只有 shell 命令实际引用直接安装目录下的 `SKILL.md` 才算使用；消息、输出、改写动作不算。
3. **无批量回填**：不新增、不执行批量历史扫描；续聊旧会话触发正常完整重扫时允许自然补记。
4. **契约不变**：只改本地 rollout 解析；上报、服务端幂等、统计和隐私边界不变。

## 数据流

```text
Stop / SessionEnd
  → scan_session(session_id)
  → skills_in_file(rollout)
  → cheap filter: line contains "SKILL.md"
  → parse JSON line and inspect payload
      ├─ old: function_call + exec_command
      │    → JSON-decode arguments → take string cmd
      └─ new: custom_tool_call + exec
           → scan input → locate real tools.exec_command(...) calls
           → take only statically extractable string cmd fields
  → common SKILL_RE over extracted command strings
  → set dedupe + sorted names
  → existing tf_report.py --skill
  → existing server (session_id, skill, mode) idempotency
```

## 旧格式提取

旧格式只接受：

- `payload.type == "function_call"`
- `payload.name == "exec_command"`
- `payload.arguments` 是可解码为 object 的 JSON 字符串
- object 的 `cmd` 是字符串

扫描 `arguments` 全文虽然兼容现状，但会让协作类 `function_call`、`workdir` 或其它字段中的
Skill 路径也成为候选。改为只取 `exec_command.arguments.cmd`，保留已知真实格式，同时收紧误报面。
格式缺字段或 JSON 破损时不降级扫描原文，遵循“宁缺毋错”。

## 新格式提取

新格式只接受：

- `payload.type == "custom_tool_call"`
- `payload.name == "exec"`
- `payload.input` 是字符串

外层 `exec` 是 JavaScript 编排容器，内部可能同时调用 `tools.exec_command`、`tools.apply_patch`
或其它工具，因此不能直接对整个 `input` 跑 `SKILL_RE`。

实现一个小型、只读的词法扫描器：

1. 在 JavaScript 代码态查找词法 token `tools.exec_command`，忽略字符串、模板字符串、行注释和块注释
   中的同名文本，并确认 token 后是调用左括号。
2. 从左括号开始按深度寻找配对右括号；识别单引号、双引号、模板字符串与反斜杠转义，
   同时跳过行注释与块注释，使其内容中的括号不会提前结束区域。
3. 对每个边界完整的调用，只接受内联 object 中可静态确认的 `cmd` 字符串字面量；
   `workdir`、`justification` 等其它字段不参与 Skill 匹配。
4. 同一个 `exec` 可返回多个命令字符串，覆盖串行和 `Promise.all`。
5. 未闭合、异常、`cmd` 非字符串字面量或动态构造到无法确认的调用直接跳过；不执行 JavaScript、
   不猜测变量值、不引入第三方解析器。

`tools.apply_patch(...)` 的参数即使包含 `.codex/skills/x/SKILL.md`，也不会计入。如果一个外层 `exec`
同时包含 `exec_command` 与 `apply_patch`，只有前者的 `cmd` 字符串参加匹配。即使
`exec_command.workdir` 或 `justification` 含 Skill 路径，也不得计入。

## 公共 Skill 路径匹配

两种格式提取出的命令区域继续复用：

```text
[/\\]\.(?:codex|claude)[/\\]skills[/\\]([^/\\]+)[/\\]SKILL\.md
```

保持以下性质：

- 只认点目录下直接安装的 Skill；作者仓库散落的 `skills/.../SKILL.md` 不算。
- Skill 名按 `MAX_SKILL_NAME` 截断。
- 同一文件、同一 session 多次读取同一 Skill 只返回一次。
- developer message、user message、`function_call_output`、`custom_tool_call_output` 不进入命令提取。

## 回填边界

本变更不提供回填入口，也不遍历未被 hook 指向的历史 session。部署后：

- 新会话在正常 `Stop` / `SessionEnd` 时开始按新解析器统计。
- 没有再次活动的旧会话不会新增记录。
- 旧会话若被恢复并产生新的 `Stop` / `SessionEnd`，现有“每轮重扫完整 rollout”机制可能识别其
  早先已经落盘的 Skill 读取；这是当前会话的正常实时采集，不是批量回填。

不为排除这种自然补记增加时间游标、升级时间戳或本地状态文件，因为那会破坏当前无状态重扫、
服务端幂等的简单模型，并新增状态迁移与失败恢复问题。

## 测试设计

### 单文件 diff > 200 行可测性复核

实现后 `shims/tf_rollout_scan.py` 单文件 diff 超过 200 行，逐块评估如下：

| 代码块 | 是否可测 / 是否必须测 | 覆盖方式 |
|---|---|---|
| JavaScript 字符串、注释与调用边界扫描 | 纯函数、必须测 | 字符串/模板、转义、行/块注释、括号嵌套、未闭合输入 |
| 内联 object 静态 `cmd` 提取 | 纯函数、必须测 | bare/quoted key、静态字符串、动态变量、非 `cmd` 字段 |
| 旧/新 payload → 命令归一化 | 纯数据转换、必须测 | 0.135 function call、0.144 custom exec、未知/畸形 payload |
| 命令 → Skill 名与去重 | 既有纯逻辑、必须回归 | `.codex`/`.claude` 正例、输出/编辑/散落路径负例、双格式去重 |
| rollout 文件查找、大小上限与异常静默 | 既有 IO 边界、已有测试并补回归 | 临时目录 fixture、无文件、错误格式、读取上限 |
| 上报与 hook 守门 | 既有跨文件契约、必须回归 | mock subprocess、Stop/SessionEnd、runtime 与开关守门 |

所有新增解析块均可在无网络、无真实用户数据的 fixture 上直接验证；不存在“应该测试但因耦合无法测试”的块，
因此不为测试额外拆分运行模块。若实现中出现必须依赖执行 JavaScript、真实 Codex 进程或网络才能验证的分支，
则方案视为失效，应回到设计拆分，而不是豁免单测。

### 单元测试

- 旧 `function_call + exec_command` 继续识别 `.codex` / `.claude` Skill。
- 新 `custom_tool_call + exec` 内单个和多个 `tools.exec_command(...)` 均能识别。
- 同一 rollout 同时含旧、新格式并读取同一 Skill，只返回一个名字。
- 新 `exec` 只含 `tools.apply_patch(...)` 时不计入。
- 新 `exec` 同时含 `exec_command` 与 `apply_patch` 时，只计命令区域里的 Skill。
- 新 `exec` 的字符串/注释中伪造 `tools.exec_command(...)` 时不计入；真实调用的非 `cmd` 字段含 Skill 路径也不计入。
- 非 `exec_command` 的旧 `function_call` 即使参数含安装路径也不计入。
- developer catalog、用户点名、工具输出、非点目录路径继续不计入。
- 括号嵌套、引号/转义、行/块注释、多个调用、未闭合调用、动态 `cmd` 与畸形 JSON 不抛错。
- Skill 名截断、文件/session 去重、`TF_REPORT_SKILLS=0` 和 hook 事件守门不回归。

### AI 验证流程

1. `pytest tests/test_rollout_scan.py`。
2. 对一份旧 `codex_exec 0.135` rollout 执行
   `python3 shims/tf_rollout_scan.py --session <sid> --print`，结果保持原 Skill 集合。
3. 对一份脱敏或本机真实的 Codex Desktop `0.144` rollout执行同一 `--print`，应识别
   `openspec-driven-development`；`--print` 不 POST，不形成回填。
4. `python -m py_compile server/*.py server/routes/*.py shims/*.py`。
5. `pytest tests/`，随后运行项目覆盖率门槛命令并确认 `server/**/*.py` 总体行覆盖率仍不低于 95%。

## 权衡

- **只扫描真实调用的静态 `cmd` 字段**：实现略复杂，但能守住 apply-patch、普通文本和非命令字段不误报的既有承诺。
- **不引入完整 JavaScript parser**：保持 shim 纯标准库和体积可控；代价是动态构造的命令可能漏报，符合宁缺毋错。
- **收紧旧格式到 `arguments.cmd`**：降低非 shell function call 误报；若未来旧格式出现其它 shell 工具名，需以真实 fixture 明确扩展。
- **不扩安装路径**：避免把 rollout 格式兼容与插件 Skill 目录识别混成一次变更。

## 风险与回滚

- Codex 的私有 rollout 格式仍可能继续变化；用按版本脱敏 fixture 锁定已知格式，未知格式静默为空。
- 轻量调用区域扫描器可能漏掉高度动态的 JavaScript；不执行代码、不猜测边界，避免安全与误报风险。
- 每轮仍重扫完整文件，但 `SKILL.md` 子串预过滤和 `MAX_BYTES` 不变，新增解析只发生在少量候选行。
- 回滚只需恢复旧 `tf_rollout_scan.py`；服务端、数据库和协议没有迁移或兼容负担。

## 验证结果（2026-07-10）

- 定向测试：`tests/test_rollout_scan.py` 22 项全过；`shims/tf_rollout_scan.py` 定向行覆盖率 86%。
- 全量测试：343 项全过。
- 服务端覆盖率：`server/**/*.py` 总体行覆盖率 96%，满足 ≥95% 门槛。
- 编译检查：`server/*.py`、`server/routes/*.py`、`shims/*.py` 通过 `py_compile`。
- 旧真实 rollout：`codex_exec 0.135` session `019f4a25-…` 仍识别
  `openspec-driven-development`。
- 新真实 rollout：Codex Desktop `0.144` session `019f4b43-…` 识别
  `openspec-driven-development`；session `019f4b48-…` 识别
  `openspec-driven-development` 与 `visual-pipeline`。
- 上述真实验证全部使用 `--print`，未 POST、未执行批量历史回填。
