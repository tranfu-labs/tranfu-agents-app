# 规格:ingest(事件采集域)

事实来源:`server/routes/ingest.py`(`POST /v1/events` 与 `POST /v1/enroll`)、`server/identity.py`(`canon_operator` / `verify_operator` — 身份归一化与 token 校验)、共用模块 `server/db.py`(写路径 + 全局 `_lock`)、`server/security.py`(写侧鉴权)、以及 `PROTOCOL.md`(TATP v0.1)。

## 身份与字段
- 身份 = `operator` + (`agent` 若有,否则 `runtime`)。
- 必填:`operator`、`runtime`、`session_id`、`status`。
- 可选:`agent`(用途标签)、`task`、`current_step`、`skill`、`skill_mode`、`ts`、`model`、`input`/`output`(opt-in)、`meta`。
- `status` 枚举:`started / running / waiting / blocked / done / error / idle`。
- 可选 profile 字段(任意子集):`models, config, mcp, skills, integrations, about, tips, cf, instructions, memory`。
- 事件顶层独立可选字段:`shim_version`(本机 `~/.tranfu/manifest.json` 的 `version`);
  客户端 SHOULD 在每次心跳都附带,而不是只在 `SessionStart` 通过 profile 上报。

## 规则(MUST)
1. 写入须带请求头 `X-TF-Key`,且等于服务端 `TF_KEY`(`TF_KEY` 为空时仅限本地开发)。比较须用常量时间
   比较(`hmac.compare_digest`),与管理钥匙一致、不得短路。
2. **去重**:仅当 `status` 或 `current_step` 相对该身份的上一行发生变化时才落新行;
   否则视为心跳,仅更新 `last_seen`,响应 `{"heartbeat": true}`,且不进活动流。
3. 收到含 profile 字段的事件时,按身份**更新该身份最新 profile**(`profiles` 表);技能名首次出现记入 `skills_seen.first_day`。
4. 事件同时具备 `skill` 与 `session_id` 时,服务端记录"该会话用过/装备过该 skill",
   以 `(session_id, skill, mode)` 幂等。`mode` 取自可选 `skill_mode ∈ {used,equipped}`,
   缺省或非法值必须按 `used` 处理。同会话同 skill 同 mode 重复投递(含 spool 重试)不得产生第二条记录;
   同 skill 的 `used` 与 `equipped` 必须为两条独立记录。该记录保留 `session_id`、`operator`、`runtime`、
   `mode`、首见 `Asia/Shanghai` 统计日,且不受 events 90 天保留窗口影响。
5. 即使事件命中心跳去重(status/step 无变化仅刷新 last_seen),`skill` 字段仍必须被处理。
   事件无 `session_id` 时,`skill` 字段忽略:不落库、不报错、正常返回。
6. shim/plugin 侧:`TF_REPORT_SKILLS=0` 时不得附加 `skill` / `skill_mode` 字段;默认(未设置或非 0)附加。
   skill 名提取失败时不附加该字段,不得阻塞或报错。
7. OpenClaw 下 `skill_mode=equipped` 只表示框架把 skill 编译进 prompt(装备态),不代表 agent 实际跨工具边界使用;
   上报与日志只允许包含 skill 名和结构事实,不得包含 prompt 正文、skill 描述、参数或输出。
8. 具体时间戳一律保存 UTC instant;`events.day`、`skill_uses.day` 与 `skills_seen.first_day`
   取服务端接收时间在 `Asia/Shanghai` 下的统计日期。
9. 云端运行时 `{manus, mulerun, chatgpt}` 标记 `fidelity = coarse`,其余 `full`。
10. `input`/`output`(内容)与 `instructions`/`memory`(敏感)默认不应被上报,仅在使用者显式开启时携带。
11. `shim_version` 只记录本机 `~/.tranfu/manifest.json` 的内容版本,用于看板判断本地 shim 是否过期。
    服务端按 `(operator, agent_key, runtime)` 粒度独立 sticky 存储:**收到非空值更新,缺失时保留旧值**;
    profile 全量替换不得触碰该字段,后续不带 `shim_version` 的心跳不得清掉它。
    为兼容旧 shim,通过 profile 字段携带 `shim_version` 的旧路径仍允许(`tf_profile.collect()` 顶层导出,
    服务端读 payload 顶层一次即覆盖两种来源)。
12. **Claude Code 斜杠命令也算 skill 调用。** Claude Code(Desktop / CLI / IDE 入口下)在 hook 之后才把用户手敲的 `/<skill-name>` 展开成 `<command-message>...</command-message>` + `<command-name>/<name></command-name>` + `<command-args>...</command-args>` 三件套写进 transcript jsonl(`~/.claude/projects/*.jsonl`)。**`UserPromptSubmit` hook 收到的 `prompt` 字段是裸文本,不含任何 markup**——所以不能从 `UserPromptSubmit` 解析,必须等 transcript 落盘后再扫。shim 侧(`tf_hook.py`)必须在 `Stop` 和 `SessionEnd` 事件中读 hook payload 携带的 `transcript_path`,扫描其中的 `<command-name>/?<name></command-name>` 标记,对每个唯一 skill 名按 `skill` 字段上报一次(`current_step` 为 `skill: <name>`,与 `scan_codex_skills` 输出对齐)。
    扫描时必须做**位置校验**:行级 JSON 解码 transcript jsonl,仅当某行满足 `type == "user"` 且 `message.content`(支持 string 与 list-of-blocks 两种形态,list 形态取首个 `type=text` 块的 `text`)`lstrip()` 后**以 `<command-name>` 起头,或以 `<command-message>` 起头且紧跟 `<command-name>`**时,才取首个 `<command-name>` 标记作为候选 skill 名。位置不在 user-message 起头斜杠命令三件套中的标记(含 assistant 文本、tool_result content、subagent prompt、文档/代码 fixture 引用等)一律忽略,不得上报。
    扫描时还必须做**命名空间校验**:候选 skill 名归一化(去前导 `/`,按 `:` 切首段以折叠子命令)后,若落入 Claude Code 内置斜杠命令集合(含但不限于 `clear / compact / context / cost / config / agents / doctor / exit / quit / help / login / logout / memory / model / permissions / hooks / status / usage / mcp / vim / bug / release-notes / pr-comments / terminal-setup / add-dir / resume / migrate-installer / ide / bashes / output-style / microphone / fast`),不得上报。该集合由 shim 侧维护,Anthropic 未来扩展内置命令时同步追加。
    约束与既有 `PreToolUse + Skill` 工具调用同口径:会话×skill 去重(服务端 `(session_id, skill, mode)` 唯一约束兜底,客户端不持状态)、`TF_REPORT_SKILLS=0` 可关、`TF_RUNTIME != claude-code` 不触发、skill 名提取失败或 jsonl 缺失/不可读/`transcript_path` 缺失时静默退出且不阻塞主线程、同会话内 Stop 多次触发产生的重复上报由服务端去重吞掉。

## 签发端点防爆破(SHOULD)
- `POST /v1/enroll`(凭 `TF_KEY` 签发持久 per-operator token)应纳入与管理接口同类的按 IP 速率限制
  (同一退避机制,独立计数桶),遏制对写侧钥匙的在线猜测;触发封锁返回 `429 + Retry-After`。
- `POST /v1/events` 高频上报路径不纳入该限流(豁免),避免误伤正常心跳。

## 不变量
- 不存在任何 token / 成本字段(见 ADR-0002)。
- 上报失败不得影响使用者 agent(客户端侧静默,见 ADR-0005)。
- `skills_seen.first_day` 在普通采集时记录 skill 首见统计日;当后台清理或恢复导致某 skill 的
  `skill_uses` 引用增减时,必须按剩余引用重算(取剩余最早 `Asia/Shanghai` 统计日;无引用则删除该行)。

## 可验证行为(示例)
- 连发两条相同 `status+current_step` → 第二条返回 `heartbeat:true`,活动流不增。
- 带 `skills` 的事件后,`/api/state` 该身份 session 含 `skills`,且 leverage 资产数随之增加。
- 带顶层 `shim_version` 的事件后,`/api/state` 该身份 session 含同值 `shim_version`。
- 三连事件 `{shim_version: A}` → `{}`(无该字段)→ `{shim_version: B}` 后,/api/state 该身份的 `shim_version`
  依次为 A、A(sticky)、B。
- 从未上报过 `shim_version` 的 agent → `/api/state` 该 card 的 `shim_version` 为 null/缺失,
  让前端走 unknown 灰态(不得在服务端"猜"成最新或最旧)。
- OpenClaw 上报 payload 必须包含 `shim_version` 顶层字段(只要本机 manifest 可读)。
- 同一 session_id + 同一 skill + 同一 mode 投递两次 → skill 使用记录 1 行;第二次响应仍 200。
- 同一 session_id + 同一 skill 分别以 `used` 与 `equipped` 投递 → skill 使用记录 2 行。
- 带 `skill_mode=equipped` → skill 使用记录 `mode` 为 `equipped`;非法/缺省 `skill_mode` → `used`。
- 两个不同 session_id 各报同一 skill → skill 使用记录 2 行。
- 带 skill 但无 session_id 的事件 → 200,skill 使用记录 0 行。
- 连续两个相同 status/step 的事件中第二个带 skill → 第二个命中心跳路径,skill 使用记录仍产生 1 行。
- `Stop` 事件 + `transcript_path` 指向的 jsonl 含 `<command-name>/openspec-driven-development</command-name>` → 触发一次上报含 `skill=openspec-driven-development`、`current_step=skill: openspec-driven-development`、`status=done`。
- `UserPromptSubmit` 事件 + prompt 是裸 `/openspec-driven-development …`(无 markup) → 不附加 `skill` 字段,`current_step` 保持 `prompt`(改在 Stop 时由 `scan_claude_skills` 补)。
- `Stop` + `TF_REPORT_SKILLS=0` → transcript 内即使有 `<command-name>` 标记也不附加 `skill`。
- `Stop` + `TF_RUNTIME != claude-code` → 不读 transcript、不上报。
- `Stop` + `transcript_path` 字段缺失或路径不存在 → 静默退出,不报错、不上报。
- 同一 session 内 Stop 触发多次,transcript 内同一个 `<command-name>` 始终在 → 每次 Stop 都会重发一次,服务端 `(session_id, skill, mode)` 唯一约束兜底,`skill_uses` 表仍只 1 行。
- 同一会话内:用户先手敲 `/foo` 触发 Stop 上报、随后模型 invoke `Skill` 工具 `foo` 触发 PreToolUse → `skill_uses` 表仍只有 `(session, foo, used)` 1 行(既有去重规则未变)。
- 服务端当前 UTC 时间为 `2026-06-12T16:05:00+00:00` 时,新事件落库 `events.day=2026-06-13`;
  同一事件带 `skill=alpha` 时,新 `skill_uses.day=2026-06-13`,对应 `skills_seen.first_day=2026-06-13`。
- `Stop` 事件 + transcript 内某行 `type=user` 且 `message.content` `lstrip()` 起头 `<command-message>clear</command-message>` 并紧跟 `<command-name>/clear</command-name>` → 命中内置命令黑名单,不附加 `skill` 字段,`skill_uses` 表无新增。
- `Stop` 事件 + transcript 内某 `type=assistant` / `tool_result` content 含 `<command-name>verify</command-name>` 子串、但全文件无任何 `type=user` content 起头斜杠命令三件套记录 → 位置守门拒收,不附加 `skill` 字段,`skill_uses` 表无新增。
- `Stop` 事件 + transcript 内某行 `type=user` 且 `message.content` `lstrip()` 起头 `<command-name>/output-style:new</command-name>` 或等价 `<command-message>` 三件套 → 归一化为 `output-style` 命中黑名单,不附加 `skill` 字段。
- `Stop` 事件 + transcript 内某行 `type=user` 且 `message.content` 是 list-of-blocks `[{"type":"text","text":"<command-name>/foo-bar</command-name>..."}]` → 抓 `foo-bar` 上报一次。
