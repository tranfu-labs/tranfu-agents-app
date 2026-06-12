# ADR-0018 OpenClaw skill 采集——装备态 `equipped`

- 状态:Proposed
- 关联:ADR-0015(skill 按会话去重)、ADR-0016(Codex 从源文件补采)、ADR-0017(Hermes 从 `skill_view` 采集)、
  ADR-0002(无 token/成本)、PROTOCOL.md §4 §5 §6、openspec/changes/openclaw-equipped-skill-usage

## 背景 / 问题

Claude Code / Codex / Hermes 三条采集链路都拿得到一次「agent 跨过工具边界把 skill 拉进来」的强信号
(分别是 `Skill` 工具调用、rollout 里读 SKILL.md 的 `function_call`、`skill_view` 工具调用)。

OpenClaw 不同:据官方文档,合格 skill 被**编译成一段 XML 块注入 system prompt**,没有 skill 工具、不读 SKILL.md。
即 OpenClaw **架构上没有「使用某 skill」这个边界**。本仓库早期注释把 OpenClaw 当成「跑 Codex runtime、读 SKILL.md」
是错的(本 ADR 含纠错项)。因此三条现有路径对 OpenClaw 全部失效:rollout 无信号、`before_tool_call` 看不到 skill、
OpenClaw 内部钩子也没有任何 skill 匹配/注入钩子。

唯一能观测到「本会话装备了哪些 skill」的点,是插件 `llm_input` 钩子拿到的 system prompt 里那段注入块。

## 决策

- **采「装备态」而非「使用态」**:OpenClaw 无使用边界,只采「skill 被判定相关、编译进 prompt」这一相关性代理信号。
  它**不是调用计数**,必须显式标注、与 `used` 隔离。
- **语义维度贯通全栈**:事件加可选 `skill_mode ∈ {used(默认), equipped}`;`skill_uses` 加 `mode` 列、主键扩为
  `(session_id, skill, mode)`;`/api/state.skills` 按 `(skill, mode)` 聚合,同名不同 mode 是两条独立条目,
  **`equipped` 与 `used` 数值永不相加**;前端给 equipped 条目加标识。默认 `used` 保证向后兼容、旧排行数值不变。
- **采集物是 OpenClaw 原生插件**(进程内 JS,仓库首个非 Python shim):`api.on('llm_input')` 解析注入的 `<skill>` 块 →
  会话级去重;`api.on('session_end')` 把累积的名逐个按 `tf_report.py` 事件契约直接 POST
  (`skill` + `skill_mode=equipped`)。POST 在后台 fire-and-forget,hook 立即返回。
  不走 Codex 式源文件扫描(无信号),不走 shell 钩子(拿不到注入集)。
- **早期版本默认常开本地调试日志 + 格式漂移自检**:链路依赖注入块私有格式、易随版本漂移,fail-silent 会让故障表现为「无数据」。
  常开日志区分 6 个静默断点,尤其把「无块=合法空」与「有块 0 名=疑似漂移」分开,漂移即时落 WARN。不设开关(待稳定再议)。
- **隐私照旧**:只报/只记 skill 名 + 结构事实,不报 prompt 正文/skill 描述/参数/输出;沿用 `TF_REPORT_SKILLS=0` 全局关。
- **不回填**:从上线起算(与 ADR-0016/0017 一致)。

## 后果

- ✅ OpenClaw 会话装备过的 skill 进入团队排行,且作为独立语义不污染其它三家的「使用」口径。
- ✅ `used` 排行数值与现状逐字节一致(迁移默认 `used`,新增 used 走老路径)。
- ✅ 失败静默:`llm_input` 缺字段、注入格式变化、POST 超时/失败只表现为该会话无/少数据,绝不打断宿主 agent;
  常开日志使「无数据」可被诊断。
- ⚠️ **装备 ≠ 使用**:这是与 ADR-0015/0016/0017 的根本口径差异,靠 `mode=equipped` 隔离;读侧/前端不得相加或混排。
- ⚠️ 依赖注入块**私有格式**(需真机锚定),OpenClaw 升级可能破解析——靠宽容解析 + 漂移自检 + 单测锁定 + 失败静默兜底。
- ⚠️ `session_end` 不等待网络请求完成;极端情况下宿主进程在后台 POST 完成前被杀,该会话的 equipped 数据可能丢失。
  这是为保证宿主 agent 不被 telemetry 阻塞而接受的取舍。
- ⚠️ 引入仓库**首个非 Python、非 shell-stdin 集成物**(OpenClaw JS 插件),分发/注册/维护是新面;依赖尽量零以降成本。
- ⚠️ 需服务端 schema 迁移(`skill_uses` 加 `mode` 列、主键变);部署须**先迁移后放量**,否则装备态被错记成 used。
- ⚠️ 子代理独立 `session_id` → 装备态独立计数,与 ADR-0015 同;未来读侧按 parent 归并。

## 纠错(本变更顺带)

将 ADR-0016、`shims/tf_rollout_scan.py`、`shims/tf_profile.py`、`tests/test_profile.py` 中「OpenClaw 跑 Codex runtime、
可扫 rollout / 读 SKILL.md」一类旧表述改正为本 ADR 的事实(skill 注入 prompt、无工具边界)。`tf_profile.py` 对
OpenClaw **安装态** skill 的目录探测(精度顺序与官方一致)和后端配置探测是 profile 能力,不是 skill 使用采集,
予以保留。
