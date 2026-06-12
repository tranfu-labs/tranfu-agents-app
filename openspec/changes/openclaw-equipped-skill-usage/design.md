# 设计:openclaw-equipped-skill-usage

## 信源声明

本设计以**官方文档**为准,**不以本仓库既有注释为准**——本仓库对 OpenClaw「跑 Codex runtime、读 SKILL.md」
的旧注释已被证伪(ADR-0016 / `tf_rollout_scan.py` / `tf_profile.py` 注释),本变更含纠错项。依据:

- 技能机制:[Skills · OpenClaw](https://docs.openclaw.ai/tools/skills)——合格 skill 编译成 XML 块**注入 system prompt**,无 skill 工具、不读 SKILL.md。
- 钩子机制:[Hooks · OpenClaw](https://docs.openclaw.ai/automation/hooks) / [Plugin hooks · OpenClaw](https://docs.openclaw.ai/plugins/hooks)
  ——内部钩子是进程内 JS 回调;插件 SDK 钩子有 `llm_input`(观察 system prompt/prompt/history)、`before_tool_call`、`session_end`;
  **无任何 skill 匹配/注入钩子**。
- 插件机制:[Building plugins](https://docs.openclaw.ai/plugins/building-plugins) / [Plugin manifest](https://docs.openclaw.ai/plugins/manifest)
  ——原生插件带 `openclaw.plugin.json` 清单;`definePluginEntry({id,name,register})`;`api.on(...)` 注册钩子;`api.pluginConfig` 拿清单校验过的配置。

## 已确认的决策

1. **采「装备态」而非「使用态」**:OpenClaw 无「使用」边界,唯一可观测的是「这个 skill 被判定相关、编译进了 prompt」。
   这是相关性代理信号,不是调用计数。**必须分语义,不可混入 used 排行。**
2. **唯一观测点是 `llm_input`**:注入的 `<skill>` 块在 system prompt 里。无 skill 钩子,只能从 prompt 解析。
3. **采集物是 OpenClaw 原生插件**(进程内 JS),不是 Python shell hook——OpenClaw 钩子无 shell-out、且注入集只在进程内可见。
4. **语义维度贯通全栈**:事件 `skill_mode` → `skill_uses.mode` → 排行按 mode 分语义 → 前端标识。默认 `used` 向后兼容。
5. **回填**:不回填,从上线起算(与 ADR-0016/0017 一致,排行是趋势工具)。
6. **隐私**:只报 skill 名 + 结构事实;**不报** prompt 正文/skill 描述/参数/输出。沿用 `TF_REPORT_SKILLS=0` 全局关。
7. **调试日志早期默认常开**:链路易碎,常开本地日志 + 漂移自检,不设开关(待稳定后再议加门)。

## 为什么是「插件解析 prompt」,不是别的路

| 路子 | 为什么不行 |
|---|---|
| 照搬 Codex rollout 扫描 | OpenClaw 不读 SKILL.md、不产生 `function_call`,**无文件信号** |
| `before_tool_call` 抓 skill(同 Hermes) | skill 不是工具,`toolName` 里永远没有 skill;只能抓到 slash 命令显式触发那一小撮,召回极低 |
| shell/CLI 钩子托管 Python reporter | 即便有 shell 钩子层,事件 JSON 里**没有注入的 skill 集**;注入集只在进程内 `llm_input` 可见 |
| 测「使用」 | 架构上无此信号。强行推断(注入后 agent 调了哪些工具→反推哪个 skill)归属模糊、误报高,放弃 |

故:进程内插件 hook `llm_input`,解析注入块,是「最强可得信号」。代价是依赖注入块的私有格式(靠宽容解析 + 漂移自检 + 失败静默兜底)。

## 数据流

```
OpenClaw 把合格 skill 编译成 <skill> XML 块,注入 system prompt
→ 插件 api.on('llm_input'): 取 system prompt 文本 → skill-extract(text)
     → 返回 {names:Set, blockSeen:bool} → 并入「按 session_id 维护的去重 set」
→ 插件 api.on('session_end'): 对该会话累积的 names,逐个排入后台 POST 队列,hook 立即返回
     POST /v1/events  { skill:<名>, skill_mode:"equipped", session_id, status:"done",
                        current_step:"skill(equipped): <名>", + 身份 }
     后台 POST 完成后写一行 session_end 汇总日志(postOk/postFail)
→ 既有 ingest:事件带 skill+session_id → INSERT OR IGNORE skill_uses(session_id, skill, mode='equipped')
→ skill_usage(conn): GROUP BY skill, mode → 排行条目带 mode
→ dashboard: equipped 条目加标识;同名 used/equipped 为两条,不相加
```

## 改动文件与职责

### 新增 `shims/openclaw/`(仓库首个非 Python shim)

- `openclaw.plugin.json`——清单:`id`、`name`、config JSON Schema(TRANFU `server` url、`key`、`operator`/`agent`/`role` 身份)。
  OpenClaw 据此校验配置而不执行代码。
- 插件入口(`index.js`/`.ts`)——`definePluginEntry({id,name,register})`;`register(api)` 里:
  - 从 `api.pluginConfig`(或环境兜底)解析身份/server/key,缺失则本会话不上报但落日志(断点 6)。
  - `api.on('llm_input', ...)`:取 system prompt 字符串 → `skill-extract` → 把新名并入会话 set;**只在出现新名时更新**,
    避免每轮重复整段解析。
  - `api.on('session_end', ...)`:对会话 set 逐个 fire-and-forget POST(带 `skill_mode=equipped`),hook 不等待网络;
    后台任务完成后落汇总日志行。单测可调用 reporter 暴露的 `flush()` 等后台任务,生产插件不使用它。
  - 全程 try/catch 包裹,**任何异常都吞掉**——telemetry 绝不能让宿主 agent 崩。
- `skill-extract`(纯函数,单独文件便于单测)——输入 system prompt 文本,输出 `{names, blockSeen}`:
  `blockSeen` = 注入块标记是否出现(用于区分「无块=合法空」与「有块 0 名=疑似漂移」)。**宽容解析**:任何异常返回 `{names:∅, blockSeen:false}`。

### 调试日志(常开,落 `~/.tranfu/logs/openclaw-skill.log`)

要能区分 6 个静默断点:

| # | 断点 | 落什么 |
|---|---|---|
| 1 | `llm_input` 没触发 / 触发几次 | 会话内计数,汇总行 |
| 2 | 拿不到可读 system prompt | 标志位,汇总行 |
| 3 | prompt 无注入块(**合法空**) | `blockSeen=false`,汇总行 |
| 4 | **有块、0 名(疑似格式漂移)** | 发现即**立即**落 WARN(块长度 + 提取数,**无原文**),并进汇总行 |
| 5 | `session_end` 攒 N 名、POST 成功/失败几个 | 汇总行(成功/失败计数) |
| 6 | 身份/server/key 没解析到 | 标志位,汇总行 |

约束(常开后更要收紧):
- **隐私**:每行只含 UTC 时间 + session_id + 事件 + 结构化计数/标志 + skill 名;**绝不含** prompt 正文/skill 描述/参数/输出。
  漂移取证只靠「块在否 + 块长度 + 提取数」,不落原文(不留 verbose 口子,因为没有开关)。
- **不刷屏 / 文件不涨爆**:不每条 `llm_input` 落行;会话内攒计数,`session_end` 落**一行汇总**;文件超阈值截断/轮转(留尾部)。
- **崩溃留痕**:漂移 WARN 即时落(不等 session_end);`session_start`(若有钩子)落一行「开始采集」,使被杀进程的会话仍有迹。

### 服务端 `server/app.py`

- `skill_uses` 加列 `mode TEXT NOT NULL DEFAULT 'used'`;主键 `(session_id, skill)` → `(session_id, skill, mode)`。
  既有库迁移:`ALTER TABLE ADD COLUMN`(SQLite 加列带默认即可),旧行 `mode='used'`。
- ingest:读事件 `skill_mode`(白名单 `{used, equipped}`,非法/缺省→`used`),写入 `skill_uses.mode`。
- `skill_usage(conn)`:`GROUP BY skill, mode`,每条带 `mode` 字段返回。排序口径不变(按近 30 天会话数)。
  **used 的排行数值与现状逐字节一致**(旧行全是 used,新增 used 走老路径);equipped 作为带标条目并列,不与 used 相加。

### 前端 `frontend/`

- 排行项读 `mode`;`equipped` 加一个小标识(如「装备」角标),`used` 不变。
- 同一 skill 名若同时有 used 与 equipped(不同 runtime)→ 两条独立条目,各自带标,**不合并求和**。
- 跑 `npm --prefix frontend run build` 校验。

### 安装 / 文档 / 纠错

- `install.sh`:分发 `shims/openclaw/` 到本地,并注册进 OpenClaw 配置 `plugins.entries.<id>`(具体落盘位置待真机确认)。
  依赖尽量零(只用运行时全局能力,不引 npm 依赖树)。
- `PROTOCOL.md`:§4 加 `skill_mode`;§5 注明 OpenClaw 下 skill 名取自注入块;§6 落库规则加 mode。
- `openspec/specs/ingest/spec.md`:见本变更 `specs/ingest/spec.md` delta。
- `docs/adr/0018-*` 成文 + 登记 `README.md`;`module-map.md` 加 `shims/openclaw` 边界。
- 纠错 ADR-0016 / `tf_rollout_scan.py` / `tf_profile.py` 的 OpenClaw 旧注释。

## 口径细节:什么算 OpenClaw「装备了一个 skill」

| `llm_input` 观测 | 是否计入 equipped | 原因 |
|---|---|---|
| system prompt 含 `<skill name="x">…` 注入块 | ✅(x 计入装备态) | 框架判定 x 与本任务相关、编译进了 prompt |
| prompt 无注入块 | ❌ | 合法空,本会话未装备任何 skill |
| 有注入块标记但解析不出名 | ❌(但落漂移 WARN) | 疑似格式漂移,不猜测、不误计,只告警 |
| agent 装备了 x 但实际没按它执行 | ✅(仍计装备态) | 接受:装备态本就是「相关/在场」语义,非执行计数 |
| slash 命令显式触发(`command-dispatch: tool`) | 由 `llm_input` 是否含该块决定 | 不单独走 `before_tool_call`;统一以注入块为准,避免双计 |

## 已知边界(默认决策,可推翻)

- **装备 ≠ 使用**:这是与其它三家最大的口径差异,靠 `mode=equipped` 显式标注与隔离;读侧/前端不得把两者相加或混排成一个数。
- **依赖注入块私有格式**:OpenClaw 改注入格式 → `skill-extract` 可能失真。靠宽容解析 + 漂移自检(断点 4)+ 单测锁格式兜底。
- **插件未装 = 无数据**:仅当用户 OpenClaw 配置注册了本插件时才产生数据;未注册 = 该 runtime 无数据,不报错。
- **上报不阻塞宿主**:`session_end` 只安排后台 POST 并立刻返回;如果宿主进程马上退出/被杀,少量 queued POST 可能来不及发出。
  接受这个风险,优先保证 telemetry 不影响 agent 主流程。
- **子代理独立 session_id**:OpenClaw 有 `subagent_*` 钩子,子代理装备态在其自身会话计;与 ADR-0015 一致,未来读侧按 parent 归并。
- **多 agent / 多 home**:OpenClaw 每 agent 一套配置;插件按其所在 agent 进程的 `session_id` 上报,身份由该 agent 的 `pluginConfig` 决定。

## 分发线:上线后数据何时开始产生

需先把 `shims/openclaw/` 部署到服务端 `shims/`,队友重跑 `install.sh` 注册插件后,其 OpenClaw 会话才开始产生装备态数据。
服务端需先完成 `skill_uses.mode` 迁移(加列默认 `used`),再接收带 `skill_mode=equipped` 的事件;
旧服务端(无 mode 列)收到 `skill_mode` 会忽略该未知字段、按 `(session_id, skill)` 落成 used——可接受但**不应**在迁移前放量
(否则 OpenClaw 装备态会被错记成 used)。故部署顺序:**先服务端迁移,后分发插件**。

## 验证计划(实现后据此填结果)

1. **插件提取单测(JS)**:含 `<skill>` 块 → 出正确名集合且 `blockSeen=true`;无块 → 空且 `blockSeen=false`;
   畸形/改格式块 → 空且不抛错(漂移分支:`blockSeen=true`、`names=∅`);同 session 多轮同名 → 去重只一次。
2. **日志单测**:常开下 6 类断点各进汇总行;漂移即时落 WARN 且**不含原文**;文件超阈值被截断。
3. **协议/服务端测(Python,对齐 `tests/test_skill_usage.py` 风格)**:
   `skill_mode=equipped` → `skill_uses` 落 `mode='equipped'`;同 session 重发同 skill equipped → 幂等;
   同 session 另发同 skill 的 used → 两行共存(主键含 mode);非法 `skill_mode` → 落 `used`;
   缺省 `skill_mode` → `used`(回归:旧客户端行为不变);`/api/state.skills` 里 equipped/used 分条不相加。
4. **前端**:排行渲染 equipped 标识;同名 used/equipped 两条不合并;`npm --prefix frontend run build` 过。
5. **端到端手验**:真机 OpenClaw 跑一个会触发某 skill 注入的任务 → 远端排行出现该 skill 的 **equipped 条目**且不混进 used;
   本地日志汇总行可见 llm_input 次数/提取名/POST 结果。
