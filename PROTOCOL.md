# Tranfu Agent Telemetry Protocol (TATP) v0.1

一个小而中立的协议，让团队能实时看到每个人的 AI agent 正在做什么 ——
无论它跑在 Claude Code、Codex、Open Claw、Hermes、Manus、MuleRun、ChatGPT 还是别的工具上。

TATP 是**完全原创**的。它只借鉴了"先发标识/操作名、内容载荷按需开启"这一类通用可观测性
思路，但**不依赖、也不声称兼容任何第三方语义约定**。字段、状态机、鉴权与隐私规则都在本文件里
自洽定义；要往别的后端转发时，自己写一层映射即可。

---

## 1. 事件（the event）

每个 agent 在状态变化时发出一个小 JSON 事件：开始、换步骤、完成、出错、或卡住等待输入。
**一次状态变化 = 一个 `POST`。**

```
POST {SERVER}/v1/events
Content-Type: application/json
X-TF-Key:   <团队写入密钥>     // 团队级写入闸门（粗粒度）
X-TF-Token: <operator 令牌>    // 可选；开启强制归因时必填（见 §4）
```

```jsonc
{
  "v":          "0.1",              // REQUIRED. 协议版本，便于服务端兼容路由
  "operator":   "bob",              // REQUIRED. 哪个队友（人）。组织语义，非身份凭证（见 §4）
  "agent":      "copy",             // optional. 这个人的命名 agent/lane: "copy" / "code" / "research"
  "runtime":    "open-claw",        // REQUIRED. claude-code | codex | open-claw | hermes | manus | mulerun | chatgpt ...
  "session_id": "ab12cd34",         // REQUIRED. 每个 run 稳定；在该 agent 生命周期内复用
  "parent_session_id": "root-77",   // optional. 父 run 的 session_id；子 agent 用它挂到父 run 下，形成 agent 树
  "status":     "running",          // REQUIRED. 见下方枚举
  "task":       "重构支付模块",       // 人类可读目标。组织语义
  "current_step": "editing payments.py",   // 此刻在做什么
  "skill":      "openai-docs",      // optional. 本次工具调用用到/被装备的 skill 名；不含参数或内容
  "skill_mode": "used",             // optional. used(默认) | equipped(OpenClaw 装备态)
  "ts":         "2026-05-29T10:03:00Z",     // optional. 客户端本地时间，RFC3339；仅供展示，省略由服务端补

  // --- 可选内容（反馈闭环载荷），仅当内容捕获开启时发送，见 §5 ---
  "input":  "完整 prompt 文本 ...",
  "output": "模型输出 / diff ...",

  // --- 可选自由字段 ---
  "meta": { "repo": "payments-svc", "branch": "feat/x" }
}
```

> **时间口径（重要）。** 客户端 `ts` 只用于展示。所有时长/活跃度计算一律用**服务端落库时间**
> （`recv`），不受跨机时钟漂移影响。客户端无需 NTP 同步也不会污染看板指标。

### `status` 枚举
| value     | 含义                                   | 计入活跃时间 | 终态 |
|-----------|----------------------------------------|:-----------:|:----:|
| `started` | session 开始                            | ✓ | |
| `running` | 正在干活                                | ✓ | |
| `waiting` | 等待人工输入 / 审批                       | ✓ | |
| `blocked` | 卡住（限流、过不去的错误，需要人介入）        | ✓ | |
| `done`    | 成功结束                                | | ✓ |
| `error`   | 失败                                    | | ✓ |
| `idle`    | 存活但无事可做                            | | |

> **`blocked` 的归属（明确定义）。** `blocked` 视为**存活态**：它确实占用着一个 run，因此
> 计入活跃时间、且不会被判成 `idle`。同时服务端在质量统计里**单列** `blocked` 计数，便于治理
> 快速看到"谁卡住了、需要人介入"。简言之：既计活跃、又单列。

### 心跳与判活
- 长时间停留在 `running`/`started`/`waiting`/`blocked` 的 agent，**推荐每 60s 发一次心跳**
  （重复同一 status/step 即可）。
- 服务端判活阈值 = **180s**（3 个心跳周期）。超过未见心跳的存活态会被显示为 `idle`。
- 重复心跳不产生新历史行，只刷新存活时间（见 §6 去重）。

## 身份模型 —— 一个人，多个 agent

三层标识，让"一个队友同时跑多个 agent"成为最自然的情形：

| 字段         | 范围         | 例子              | 设置位置 |
|--------------|--------------|------------------|-----------|
| `operator`   | 人           | `bob`            | 全局（shell profile） |
| `agent`      | 命名 lane    | `copy`、`code`   | **每个 run**（wrapper `--agent`） |
| `runtime`    | 工具         | `open-claw`、`codex` | **每个 run** |
| `session_id` | 一次 run     | `copy-1717…`     | 自动 |

所以 Bob 的两个 agent 就是 `operator=bob` 下的两条流：Open Claw 上的 `bob/copy` 和
Codex 上的 `bob/code`。看板把它们显示为 Bob 名下的两张卡片。`agent` 可省略 —— 省略时看板回退到用
`runtime` 区分，这在"每个 agent 是不同工具"时已经够用。只有当同一 `runtime` 跑多个实例
（例如两个 Codex，一个写代码一个写文档）才**需要** `agent` 来区分。

> `operator` / `agent` / `task` 是**组织语义**（谁、哪条 lane、要达成什么），不是技术标识符，
> 也不映射到任何外部约定 —— 诚实标注即可。

到这里就是协议的全部。下面都是讲*每类 agent 如何发出它*。

---

## 2. 三档保真度

异构 agent 能给的可见度不同。诚实标注每个 agent 处在哪一档 —— 看板会区分渲染。

### Tier A — hook  → 实时状态/步骤
**Claude Code / Codex**（或任何带钩子的本地 agent）。用钩子在每步上报 status/step。
见 `shims/claude-code/` 与 `shims/codex/`。

### Tier B — wrapper  → 状态(开始/心跳/结束)
**Open Claw / Claw Code、Hermes、任意本地 CLI / API 脚本；Codex 也可用此方式临时包装。**
用通用包装器 `tf-run`，自动发 `started` → `running` 心跳（每 60s） → `done`/`error`。见 `shims/wrapper/`。

### Tier C — cloud black box  → 仅 run 级 start/end
**Manus、MuleRun、ChatGPT web。** 你看不到内部。只在**派发点**埋点：派发任务时发 `started`，
返回时发 `done`（有 API/webhook 就用，否则手动包一层派发脚本）。没有内部步骤。看板把这些 session
标为 `coarse`，避免有人把"沉默"误当成"没在干活"。

---

## 3. 传输可靠性（上报方必须遵守）

可观测性工具**绝不能反过来拖垮被观测的 agent**。所以上报方（钩子 / wrapper / 客户端库）必须：

- **Fire-and-forget + 短超时。** 单次 POST 超时 ≤ 5s，失败不阻塞宿主 agent，永远不让上报影响主流程。
- **失败本地 spool。** POST 失败（服务端挂了、网络断了）时，把事件追加到本地暂存文件
  （`~/.tranfu/spool.ndjson`），不要丢弃。
- **至少一次投递。** 下次有事件要发时，先尽力把 spool 里积压的事件按序补发，再发当前事件。
  服务端通过 §6 的去重容忍重复投递，所以"至少一次"是安全的。
- **有界 spool。** 暂存文件设上限（默认 1000 行 / 5 MiB），超出丢最旧的，避免离线太久撑爆磁盘。

> 钩子尤其要注意：钩子运行在宿主 agent 的关键路径上，必须立即返回、异常吞掉、退出码 0。

### Shim 自更新
服务端提供 `GET /shims/manifest`,列出当前 shim 文件、安装目标、sha256 与整体内容版本。
新版安装器按 manifest 全量下载并校验所有目标文件,成功后才把该 manifest 写到
`~/.tranfu/manifest.json`;若全量安装失败,不得写入假的本地版本基线。随后 `tf_hook.py` 在
`SessionStart` / `on_session_start` 后台拉起 `tf_selfupdate.py` 做低频检查。自更新必须先下载到
staging、校验 sha256,`.py` 通过 `py_compile`,全部通过后才替换正式文件;失败静默并保留旧版。
本地版本与服务端一致但 manifest 文件缺失或哈希不符时,自更新仍必须修复该文件。`TF_AUTO_UPDATE=0` 完全关闭。
Claude Code / Codex / Hermes 在下一次 hook 触发时使用新文件;OpenClaw 插件文件可被刷新,但需重启
OpenClaw 才加载新 JS。

> **进程内插件例外。** 标准 Python/shell shim 继续按上面规则做本地 spool。OpenClaw 原生插件运行在宿主
> 进程内,其 equipped skill 上报是派生统计而非核心状态事件;为保证 `session_end` 不等待网络、不影响
> agent 主流程,它采用后台 at-most-once POST + 本地诊断日志(`~/.tranfu/logs/openclaw-skill.log`)。
> 因此极端进程退出可能丢失少量 equipped 条目,但不得阻塞宿主、不得上报 prompt/代码/输出。

---

## 4. 身份与鉴权

写入有两道关：

1. **`X-TF-Key`（团队写入密钥，粗粒度）。** 团队级共享，决定"能不能写"。这是 ADR-0002 唯一的写凭证基线。
2. **`X-TF-Token`（per-operator 令牌，可归因）。** 每个队友一把，决定"以谁的身份写"。

### 威胁模型 —— 为什么需要 per-operator 令牌
只有团队密钥时，`operator` 字段是**完全自证**的：任何拿到团队密钥的人都能发
`"operator":"alice"` 冒充别人上报。对一个"治理 / 可见性"工具来说，这意味着看板上的数据
**无法可靠归因到真人**。因此：

> **`operator` 不是身份凭证。** 在未开启强制令牌时，它只是一个展示标签，看板会标注
> "未验证（unverified）"。要让归因可信，必须走下面的入职注册流程拿到 per-operator 令牌。

### 入职注册流程（轻量，无账号体系）
沿用 ADR-0001"单容器 / 无账号库"的取舍 —— **不做登录页、不做会话、不做多租户**，只加一张
`operators` 绑定表：

```
# 管理员用团队密钥为某个队友签发一次性令牌（令牌只在响应里出现一次，服务端只存 sha256）
POST {SERVER}/v1/enroll
X-TF-Key: <团队写入密钥>
{ "operator": "alice" }
→ 200 { "operator": "alice", "token": "ttk_9f3c…", "note": "保存到 TF_TOKEN，仅此一次可见" }
```

队友把 `token` 存进 `TF_TOKEN` 环境变量，shim 上报时带上 `X-TF-Token`。服务端校验：

- 令牌有效 **且** 其绑定的 operator == body 里的 `operator` → 接受，标记 `verified=true`。
- 不一致 / 令牌无效 → **403**（开启强制时），不允许冒名。

服务端通过 `TF_REQUIRE_TOKEN=1` 开启强制归因；关闭时（默认，向后兼容）允许 `operator` 自证，但
事件标 `verified=false`，看板据此显示"未验证"。

---

## 5. 隐私与内容捕获

**默认姿态：** 发送 `operator`、`runtime`、`status`、`task`、`current_step`，以及能从工具调用元数据
安全识别到的 `skill` 名 —— 但**不发** `input`/`output`。
内容捕获是 opt-in 的（shim 侧 `TF_CAPTURE_CONTENT=1`），因为你明确想要这个反馈闭环。
`skill` 只记录名称，不记录参数、prompt、代码或输出；`skill_mode` 缺省为 `used`。如团队不希望统计 skill 使用，可在本机设置
`TF_REPORT_SKILLS=0` 关闭。Claude Code 从 `Skill` 工具调用参数取 skill 名；Hermes 从
`skill_view` 工具调用参数取 skill 名。Codex 不把 skill 触发暴露为 `Skill` 工具调用，因此在 Codex 下
shim 会在轮次/会话结束时**本地读取该会话的 rollout 文件**，仅提取"读取了某个已装 `SKILL.md`"
这一信号并上报 skill 名；会话内容不离开本机。OpenClaw 没有 skill 工具边界,只在原生插件的
`llm_input` 里从 system prompt 注入的 `<skill>` 块提取 skill 名,并以 `skill_mode=equipped` 上报
「装备态」,不与 `used` 使用态相加。`TF_REPORT_SKILLS=0` 同样关闭这些路径
（见 ADR-0016 / ADR-0017 / ADR-0018）。

> 本协议**不含任何 token / 费用字段**，这是刻意的取舍（见 ADR-0002）。本工具是"谁在干什么"的协作可观测，
> 不是计费系统。

### 硬约束：开启内容捕获前必须先有读侧鉴权
看板默认"谁有网址谁就能看"。一旦开启敏感上报（`input` / `output` / `instructions` / `memory`），
等于把 prompt、代码、系统提示明文挂到一个对外可见的页面。因此本协议规定：

> **在开启 `TF_CAPTURE_CONTENT` / `instructions` / `memory` 之前，必须先落地读侧鉴权**
> （边缘 Cloudflare Access / Caddy basic auth，或应用内 `TF_READ_KEY`）。这不是建议，是硬约束。

服务端据此**强制执行**：若收到含敏感字段的事件，但服务端未声明读侧鉴权已就位
（`TF_READ_AUTH=1` 或设置了 `TF_READ_KEY`），则**丢弃这些敏感字段不予存储**，只保留状态类字段，
并记一条告警。这样即便有人误开了捕获，也不会造成明文裸奔。

**业务流程影响（知情）：** 内容捕获从"改个环境变量就开"变成"先配读侧鉴权、再开捕获"两步。
新人入职默认全关；要开内容捕获需先完成部署侧鉴权配置并走团队审批。代价是开启有摩擦 —— 这正是目的。

---

## 6. 服务端语义（上报方无需自己算）

这些由服务端从事件历史推导，**shim 不要尝试计算**：

- **去重 / 心跳。** 去重键 = `operator + runtime + agent + session_id`。与上一条
  status/step 完全相同的事件视为纯心跳：只刷新存活时间，不产生新历史行、不进 feed。
  **去重键包含 `session_id`** —— 同一身份并发多个 session 不会互相吞掉活性。
- **质量块**（`runs / success / error / blocked / avg_sec / auto_rate`）：从事件历史推导。
- **活跃时长**：用服务端落库时间（`recv`）做区间累加，按天分桶（today / week / 7日 / 90日）。
- **reuse**：跨 operator 的技能名重叠信号。
- **leverage**（`assets` / `skills_week`）：从团队上报过的技能推导。口径是
  **"累计曾出现过的技能资产"**（cumulative），不是"当前在用"。
- **skill 使用/装备计数**：当事件带 `skill` 且有 `session_id` 时，服务端记录一行
  `session_id × skill × mode`；`mode` 来自 `skill_mode`，只允许 `used` / `equipped`，缺省或非法值按
  `used` 处理。同一会话重复上报同一 `skill+mode` 只算一次，即使第二次事件命中心跳去重也会先处理。
  同一 skill 的 `used` 与 `equipped` 是两条独立记录，读侧排行分条呈现、数值不相加。无 `session_id`
  时忽略 `skill` 字段并正常返回。
- **SKILLS 读侧统计接口**：
  - `GET /api/skills?days={7|30|90}` 返回 SKILLS 总览,并携带 UTC 当日 `today`。`daily` 与 `table` 只统计 `mode=used`;
    `days` 只接受 7 / 30 / 90,只影响 `daily` 的窗口,不影响主表 7 天 / 30 天 / 累计列,也不影响公司库漏斗。
    `funnel` 只统计 catalog 中 `type ∈ {own, meta}` 的 skill,返回 catalog 收录、已安装、30 天有人使用、
    已安装未使用四组名单。catalog 拉取失败时接口仍返回 200,使用旧缓存并标记 `catalog.stale`;
    从未拉取成功时只让漏斗显示不可达,其它统计照常返回。
  - `GET /api/skill/{name}` 返回单 skill 详情,并携带 UTC 当日 `today`:used 指标、equipped 指标、日级 used/equipped 分列序列、
    runtime/operator 分布和最近 50 条会话记录。`equipped` 仅表示 OpenClaw 装备态,不与 used 相加。

### Profile 全量覆盖语义
profile 字段（见 §7）按 **full-snapshot / 全量覆盖**语义上报：带 profile 的事件必须携带该 agent
**当前完整的** profile，服务端整体替换旧 profile（**不做增量 merge**）。这样本地删掉的技能/集成会
真正从看板消失，避免陈旧条目把 leverage / reuse 越刷越高。偶尔上报一次即可，不必每个事件都带。

### 数据保留
事件表只保留 **90 天**窗口；更早的历史按天聚合后删除。`skill_uses` 表是会话×skill×mode 的去重统计源，
长期保留，不随事件窗口清理。SQLite 开启 WAL，读写互不阻塞。

---

## 7. 可选 profile 字段（用于 agent 详情 / 治理页）

任何事件都 MAY 携带这些**可选 profile 字段**。服务端按 §6 的全量覆盖语义保存每个 agent 身份
（`operator`+`agent`+`runtime`）的**最新**一份，展示在 agent 详情页。全部可选 —— 本地能读到什么就发什么。

```jsonc
{
  // ... 上面的核心事件字段 ...
  "models":   ["claude-opus-4-8", "gpt-4o"],          // 在用模型
  "config":   { "temperature": 0.4, "sandbox": "read-only" },  // 关键参数
  "mcp":      ["figma", "github"],                    // 连接的 MCP server
  "skills":   { "local":  [{"name":"prd-to-wireframe","desc":"需求→框架"}],
                "cross":  [{"name":"组件命名规范","desc":"三段式"}],
                "pitfalls":["别用红底白字"] },
  "integrations": [{"name":"Figma","desc":"读写设计稿"}],       // 工具及其作用
  "about":    "一句话需求 → 低保真原型",               // 这个 agent 擅长什么
  "tips":     "先说清谁用、要完成什么动作",            // 派单人的使用说明
  "cf":       { "ver":"Open Claw v1.4", "role":"品牌文案执行体",
                "location":"~/work/copy", "terminal":"zsh", "ims":["飞书"] },
  "shim_version": "b7f3c2a9...",                      // ~/.tranfu/manifest.json 的内容版本

  // --- 敏感，OPT-IN（更多内容离开本机），受 §5 硬约束 ---
  "instructions": "完整系统提示 ...",
  "memory":   { "file":"~/.claude/CLAUDE.md", "updated": 7200,
                "conventions":["命名三段式"], "learned":["hero 浅底深字转化更高"] }
}
```

**由服务端计算、绝不上报：** 质量块（`runs / success / error / blocked / avg_sec / auto_rate`）由
事件历史推导，`reuse` 由跨 operator 技能重叠推导，`leverage`（`assets` / `skills_week`）由团队上报
的技能推导。shim **不要**尝试计算这些。

`shim_version` 只用于治理可见性:看板把它与服务端当前 `/shims/manifest.version` 对比,缺失或不一致时
显示"旧 shim"提示,便于发现自动更新失败或仍未重装的机器。

`instructions` 和 `memory` 是敏感字段（暴露 agent 如何被装配、学到了什么），与 `input`/`output`
同等对待：**opt-in**，且受 §5 读侧鉴权硬约束 —— 无读侧鉴权时服务端丢弃不存。

---

## 8. 限流与尺寸上限

按 tranfu agent 的实际（看板只要"谁在干嘛"，全量内容是 opt-in 反馈闭环、无需存完整大 diff）：

| 项                  | 上限       | 超限处理 |
|---------------------|-----------|----------|
| 请求体总大小         | **256 KiB** | 直接 `413` 拒绝 |
| 落库 `input`/`output` | 各 **16 KiB** | 截断存储（尾部标 `…[truncated]`） |
| 落库 `meta`         | **4 KiB**  | 截断存储 |
| 看板展示 `input`/`output` | 4000 字 | 读取时再截断 |

这道闸防止超大 POST 撑爆 SQLite / 内存，同时保证看板要的状态信息永远能进。
