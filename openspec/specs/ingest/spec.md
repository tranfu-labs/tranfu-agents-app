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
2. **去重**:`status` 或 `current_step` 相对该身份上一行发生变化时落新行;二者相同且距上一条已确认心跳
   `<= STALE_SECONDS=180` 秒时视为纯心跳,响应 `{"heartbeat": true}`,且不进活动流。二者相同但间隔
   `> 180` 秒时必须落一条内部 `heartbeat_resume` 行作为新连续段起点,不得覆盖旧行 `last_seen`;
   最新卡片与活跃时长必须读取恢复行,活动流不得读取它。上一条已确认心跳必须同时考虑 SQLite `last_seen`
   与 pending map 中尚未 flush 的最新值,并取两者较新的有效时间;旧 pending 不得回退 SQLite 时间。
   同状态/同步骤的即时语义写入须淘汰已被覆盖的旧 pending;插入同一 session 的任何新事件行前须把上一行
   尚未落库且较新的 pending 末点固化到 SQLite。纯心跳 `last_seen` 默认可进入进程内 batch:
   当事件无其它即时写入语义时,服务端可以不立即 `UPDATE events.last_seen`,而是将最新 `last_seen` 放入 pending map,
   由后台 flush 按 `TF_HEARTBEAT_BATCH_SECONDS` 间隔用一个 SQLite 事务批量写入。batch flush 成功后必须通知 board 域
   state dirty,以便 SSE / cache 后续展示最新 liveness。服务进程异常退出时,允许丢失最多一个 batch 窗口内的纯心跳
   liveness 刷新;状态变化事件不得丢。flush 与 ingest 必须原子协调,pending 不得在对应 SQLite commit 前
   暂时不可见;SQLite 写入失败时 pending 必须保留以供重试。`TF_HEARTBEAT_BATCH_SECONDS=0` 时禁用 batch,
   恢复每次纯心跳即时更新。同一事件 id 的 pending 时间必须单调不减,并发请求中后取得写锁的较旧
   `recv` 不得覆盖较新 pending;后台 flush 的单轮普通运行时异常不得终止循环,必须在后续间隔自动重试
   保留的 pending。
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
    收到与当前 sticky 值相同的非空 `shim_version` 时不得重复更新 `agent_shim_versions.updated`;首次收到或收到不同非空版本时必须即时写入。
    为兼容旧 shim,通过 profile 字段携带 `shim_version` 的旧路径仍允许(`tf_profile.collect()` 顶层导出,
    服务端读 payload 顶层一次即覆盖两种来源)。
12. **Claude Code 斜杠命令也算 skill 调用。** Claude Code(Desktop / CLI / IDE 入口下)在 hook 之后才把用户手敲的 `/<skill-name>` 展开成 `<command-message>...</command-message>` + `<command-name>/<name></command-name>` + `<command-args>...</command-args>` 三件套写进 transcript jsonl(`~/.claude/projects/*.jsonl`)。**`UserPromptSubmit` hook 收到的 `prompt` 字段是裸文本,不含任何 markup**——所以不能从 `UserPromptSubmit` 解析,必须等 transcript 落盘后再扫。shim 侧(`tf_hook.py`)必须在 `Stop` 和 `SessionEnd` 事件中读 hook payload 携带的 `transcript_path`,扫描其中的 `<command-name>/?<name></command-name>` 标记,对每个唯一 skill 名按 `skill` 字段上报一次(`current_step` 为 `skill: <name>`,与 `scan_codex_skills` 输出对齐)。
    扫描时必须做**位置校验**:行级 JSON 解码 transcript jsonl,仅当某行满足 `type == "user"` 且 `message.content`(支持 string 与 list-of-blocks 两种形态,list 形态取首个 `type=text` 块的 `text`)`lstrip()` 后**以 `<command-name>` 起头,或以 `<command-message>` 起头且紧跟 `<command-name>`**时,才取首个 `<command-name>` 标记作为候选 skill 名。位置不在 user-message 起头斜杠命令三件套中的标记(含 assistant 文本、tool_result content、subagent prompt、文档/代码 fixture 引用等)一律忽略,不得上报。
    扫描时还必须做**命名空间校验**:候选 skill 名归一化(去前导 `/`,按 `:` 切首段以折叠子命令)后,若落入 Claude Code 内置斜杠命令集合(含但不限于 `clear / compact / context / cost / config / agents / doctor / exit / quit / help / login / logout / memory / model / permissions / hooks / status / usage / mcp / vim / bug / release-notes / pr-comments / terminal-setup / add-dir / resume / migrate-installer / ide / bashes / output-style / microphone / fast`),不得上报。该集合由 shim 侧维护,Anthropic 未来扩展内置命令时同步追加。
    约束与既有 `PreToolUse + Skill` 工具调用同口径:会话×skill 去重(服务端 `(session_id, skill, mode)` 唯一约束兜底,客户端不持状态)、`TF_REPORT_SKILLS=0` 可关、`TF_RUNTIME != claude-code` 不触发、skill 名提取失败或 jsonl 缺失/不可读/`transcript_path` 缺失时静默退出且不阻塞主线程、同会话内 Stop 多次触发产生的重复上报由服务端去重吞掉。
13. **Codex rollout Skill 补采必须兼容旧/新命令容器。** Codex shim 在 `Stop` / `SessionEnd` 时按
    `session_id` 定位本机会话 rollout,并从真实 shell 读取已安装 `SKILL.md` 的强信号中提取 Skill 名。
    旧格式只接受 `payload.type=="function_call" && name=="exec_command"`,并只检查可解码
    `arguments` object 的字符串 `cmd`;Desktop 新格式只接受
    `payload.type=="custom_tool_call" && name=="exec"`,并只检查 `input` 中代码态、边界完整的
    `tools.exec_command(...)` 调用内可静态确认的字符串 `cmd`。两种格式复用直接位于
    `.codex/skills/<name>/SKILL.md` 或 `.claude/skills/<name>/SKILL.md` 的路径口径。
    developer/user message、工具输出、字符串/注释伪调用、动态 `cmd`、非命令字段、`apply_patch`、
    非 shell function call、作者仓库散落的 `SKILL.md` 与未知格式不得计入。提取失败、rollout 缺失、
    JSON/调用边界破损或超过读取上限时必须静默跳过;现有开关、长度、去重与失败静默规则保持不变。
    该链路不得提供或执行批量历史回填,也不得主动遍历未被当前 hook 指向的历史 session;旧会话被续聊后
    因正常结束事件重扫完整 rollout 而自然补记属于允许行为,无需引入持久化游标或升级截止点。

## 签发端点防爆破(SHOULD)
- `POST /v1/enroll`(凭 `TF_KEY` 签发持久 per-operator token)应纳入与管理接口同类的按 IP 速率限制
  (同一退避机制,独立计数桶),遏制对写侧钥匙的在线猜测;触发封锁返回 `429 + Retry-After`。
- `POST /v1/events` 高频上报路径不纳入该限流(豁免),避免误伤正常心跳。

## 配置

- `TF_HEARTBEAT_BATCH_SECONDS`:纯心跳 `last_seen` 批量写入间隔,秒,float 或 int;默认 `15`。
  设为 `0` 时禁用 batch,恢复每次纯心跳即时更新 `events.last_seen`。状态/步骤变化、终态切换、profile 更新、
  新 skill usage、首次或变化的非空 `shim_version` 仍必须即时处理。

## 不变量
- 不存在任何 token / 成本字段(见 ADR-0002)。
- 上报失败不得影响使用者 agent(客户端侧静默,见 ADR-0005)。
- `skills_seen.first_day` 在普通采集时记录 skill 首见统计日;当后台清理或恢复导致某 skill 的
  `skill_uses` 引用增减时,必须按剩余引用重算(取剩余最早 `Asia/Shanghai` 统计日;无引用则删除该行)。
- profile 自动探测读取每个 `SKILL.md` 时保留 `name`，并 best-effort 读取可选
  `display_name/display_name_zh`；解析或读取失败 MUST 静默降级且不得阻塞宿主 agent。
  `name` 仍是 Skill identity，显示字段仅供读侧呈现；旧 Skill 未定义显示名时仍必须正常上报。

## 可验证行为(示例)
- 连发两条相同 `status+current_step` → 第二条返回 `heartbeat:true`,活动流不增。
- 同状态/同步骤距最后确认心跳超过 180 秒后恢复 → 插入 `heartbeat_resume` 新段,旧行 `last_seen`
  保持最后确认心跳,最新卡片可见恢复状态,活动流不新增伪状态变化。
- pending map 中存在比 DB 更新的最后确认心跳 → 断档阈值以 pending 时间计算;确需切段时先固化该时间。
- pending 早于 DB `last_seen` → 断档阈值取 DB 时间,后续 flush 不得造成时间回退或虚假恢复行。
- pending 后发生即时 skill/profile/shim 写入 → DB 推进到当前 `recv` 并淘汰旧 pending。
- pending 后发生状态/步骤变化 → 新行插入前旧行 `last_seen` 固化为 pending 末点。
- flush 与 ingest 并发 → ingest 只能观察 flush 前 pending 或 flush 后 DB;flush 失败则 pending 保留重试。
- 同一事件 pending 先入队 `00:02`、后入队 `00:01` → pending 仍为 `00:02`,不得因请求入锁乱序制造虚假断档。
- 后台 flush 第一次因瞬时 SQLite 异常失败、第二次恢复 → flush 线程继续运行,同一 pending 自动写入并在
  commit 成功后清除。
- 连发两条相同 `status+current_step` 的纯心跳,且 `TF_HEARTBEAT_BATCH_SECONDS > 0` → 第二条返回 `heartbeat:true`;
  flush 前 DB 中上一事件行 `last_seen` 不变;flush 后 `last_seen` 变为最新接收时间。
- `TF_HEARTBEAT_BATCH_SECONDS=0` 时,纯心跳立即更新 `events.last_seen`,保持旧行为。
- 连续相同心跳中第二条携带新 skill 或 profile 更新时,相关写入必须即时发生,不得被 batch 短路吞掉。
- 带 `skills` 的事件后,`/api/state` 该身份 session 含 `skills`,且 leverage 资产数随之增加。
- 带顶层 `shim_version` 的事件后,`/api/state` 该身份 session 含同值 `shim_version`。
- 三连事件 `{shim_version: A}` → `{}`(无该字段)→ `{shim_version: B}` 后,/api/state 该身份的 `shim_version`
  依次为 A、A(sticky)、B。
- 连续发送相同非空 `shim_version` 时,`agent_shim_versions.updated` 不应随每次心跳变化;发送不同版本时必须立即更新。
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
- Codex 旧 `function_call + exec_command` 与 Desktop 新 `custom_tool_call + exec + tools.exec_command(...)`
  分别以静态 `cmd` 读取 `.codex/skills/alpha/SKILL.md` → 均提取 `alpha`;同一 rollout 两种格式并存仍只返回一个名字。
- Desktop `exec` 同时包含读取 `alpha` 的 `tools.exec_command(...)` 与改写 `edited` 的
  `tools.apply_patch(...)` → 只提取 `alpha`;字符串/注释伪调用、动态 `cmd` 或仅非 `cmd` 字段含路径 → 不提取。
- 部署后不运行批量历史扫描;没有再次活动的旧 session 不产生新记录,续聊旧 session 可在下一次正常
  `Stop` / `SessionEnd` 中自然补记。
