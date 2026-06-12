# 变更提案:openclaw-equipped-skill-usage(OpenClaw skill 采集——装备态 `equipped`)

- 状态:Proposed(待真机抓 `llm_input` 注入块原文 + 确认插件出站/装载方式后实现)
- 关联:ADR-0015(skill 按会话去重)、ADR-0016(Codex 从源文件补采)、ADR-0017(Hermes 从 `skill_view` 采集)、
  PROTOCOL.md §5 §6、openspec/specs/ingest/spec.md
- 后续:**有 spec delta**(本变更修改 ingest 的 skill 落库规则,见 `specs/ingest/spec.md`)

## 背景 / 问题

skill 使用排行已接通三条采集链路,共同点是都能拿到一次「agent 跨过工具边界把某 skill 拉进来」的强信号:

- Claude Code:`PreToolUse` 的 `Skill` 工具调用(ADR-0015)。
- Codex:不暴露工具调用,轮末扫 rollout 源文件(ADR-0016)。
- Hermes:`pre_tool_call` 的 `skill_view(name)` 工具调用(ADR-0017)。

**OpenClaw 一条都接不上,而且和前三者有本质区别。** 据官方文档([Skills · OpenClaw](https://docs.openclaw.ai/tools/skills)):

> "Eligible skills are compiled into a compact XML block and injected into the system prompt."
> —— 合格 skill 被编译成一段 XML 注入 system prompt,**没有专门的 skill 工具,agent 也不会用 shell 去读 SKILL.md**。

也就是说 OpenClaw **架构上没有「使用某 skill」这个边界**:skill 按 trigger/description 匹配后直接成了 prompt 的一部分。
因此:

- rollout 扫描无信号可扫(不产生「读 SKILL.md」的 `function_call`);
- `before_tool_call` 看不到 skill(skill 不是工具);
- OpenClaw 内部钩子是进程内 JS 回调,且**没有任何 skill 匹配/注入钩子**([Plugin hooks · OpenClaw](https://docs.openclaw.ai/plugins/hooks))。

全局唯一能观测到「本会话装备了哪些 skill」的地方,是 `llm_input` 钩子拿到的 system prompt——那段注入的 `<skill>` 块就在里面。

## 目标

- 让 OpenClaw 会话**装备过(被编译进 prompt)的 skill** 进入团队排行,但**明确标成「装备态」而非「使用态」**,
  不污染 Claude/Codex/Hermes 的「使用」口径。
- 端到端把语义维度打通:事件加可选 `skill_mode`,服务端 `skill_uses` 加 `mode` 列,排行读侧按 mode 分语义。
- 采集物是 OpenClaw 原生插件(进程内 JS),通过 `llm_input` 解析注入块、`session_end` 去重上报。
- 因链路易碎(解析 prompt 内 XML、格式随版本漂移),**早期版本默认常开本地调试日志 + 格式漂移自检**。

## 非目标

- 不假装能测「OpenClaw 用过某 skill」——架构上没有该信号,只采「装备态」这一可观测代理。
- 不改 Claude Code / Codex / Hermes 既有链路与口径(一行不动)。
- 不把装备态计入既有「使用」排行数值(`equipped` 与 `used` 永不相加)。
- 不引入 Codex 式 rollout 扫描(OpenClaw 无此信号)。
- 不上报 prompt 正文 / skill 描述 / 参数 / 输出——只报 skill 名 + 结构事实(日志亦然)。

## 方案概述(详见 design.md)

两条线:

1. **语义贯通**(协议 / 服务端 / 前端):事件加可选 `skill_mode ∈ {used(默认), equipped}`;
   `skill_uses` 加 `mode` 列、主键扩为 `(session_id, skill, mode)`;`/api/state.skills` 按 `(skill, mode)`
   聚合,同名不同 mode 是两条独立条目、不相加;前端给 `equipped` 条目加标识(排行页已存在,只加标)。
2. **OpenClaw 采集插件**(新增 `shims/openclaw/`,仓库第一个非 Python shim):`api.on('llm_input')`
   解析注入的 `<skill>` 块 → 会话级去重 set;`api.on('session_end')` 把累积的名按事件契约逐个后台 POST
   (`skill=<名>` + `skill_mode=equipped`)。失败静默、不阻断宿主、只报名。

## 影响

- **新增** `shims/openclaw/`:`openclaw.plugin.json`(清单 + config schema)、插件入口、`skill-extract`
  纯函数(便于单测、并返回「块是否出现」以支撑漂移自检)。仓库首个 JS 集成,依赖尽量零。
- `server/app.py`:`skill_uses` 加 `mode TEXT NOT NULL DEFAULT 'used'`,主键 `(session_id, skill)` →
  `(session_id, skill, mode)`;ingest 读取事件 `skill_mode`(缺省 `used`)写入;`skill_usage()` 聚合带 mode。
  现有行迁移默认 `used`,旧排行数值不变。
- `dashboard/index.html`:排行项渲染 `equipped` 标识;同名 used/equipped 为两条,不合并。
- `PROTOCOL.md`:§4 事件加可选 `skill_mode`;§5 注明 OpenClaw 下 skill 名取自注入块(只报名);§6 落库规则加 mode 维度。
- `openspec/specs/ingest/spec.md`:skill 落库规则加 `mode`(见本变更 `specs/ingest/spec.md` delta)。
- `install.sh`:分发 `shims/openclaw/` 并把插件注册进 OpenClaw 配置(`plugins.entries.<id>`)——新装载方式,与 Python shim 不同。
- 新增 `docs/adr/0018-openclaw-equipped-skill-usage.md`;登记 `docs/adr/README.md`;`docs/architecture/module-map.md`
  加 `shims/openclaw` 边界。
- **纠错**:把 ADR-0016 / `tf_rollout_scan.py` / `tf_profile.py` 里「OpenClaw 跑 Codex runtime、rollout 可扫」的
  旧注释改正(profile 的安装态 skill 探测是对的,保留)。

## 待确认(实现前的前置,官方文档未覆盖)

1. 注入的 `<skill>` 块**确切格式**(标签名 / 字段)——解析靶子,需真机抓一段 system prompt。
2. `llm_input` 把 system prompt 以何字段/形态交出(可正则的字符串?)。
3. 插件**出站 HTTP** 怎么发(运行时是否有全局 `fetch`)、身份/server/key 从 `api.pluginConfig` 还是环境读、是否有 `fs` 写日志。
4. 插件**安装注册**进 OpenClaw 配置的具体落盘位置与清单字段。
