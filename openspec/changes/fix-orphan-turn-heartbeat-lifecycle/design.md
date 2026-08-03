# 设计：fix-orphan-turn-heartbeat-lifecycle

## 0. 已确认事实与约束

- #121 同时引入 detached heartbeat、异步 start/stop helper、owner 自续租和 900 秒读侧补偿；#122 没有修复该生命周期。
- 数据库不会把未结束 session 自动延伸到“现在”；虚高来自 daemon 持续推进真实 `last_seen`。
- `turn heartbeat` 是固定 synthetic step，真实活动入口仍是 `UserPromptSubmit` / `PreToolUse`，终态入口仍是
  `Stop` / `SessionEnd`。
- `implementation_authority=granted`：主理人已核验并放行根因实现与精确止血；生产历史订正仍无授权。

## 1. 止血层：安全停止当前孤儿

止血必须先做只读 inventory，再对精确对象操作：

1. 从 `~/.tranfu/heartbeats/*.json` 解析 `session_id/generation/pid/owner_pid/owner_token/stop_requested`，
   与生产导出库中仍推进 `turn heartbeat` 的 session allowlist 交叉确认。
2. 对每个候选记录 PID 当前启动 token和完整命令行；只有命令明确为当前安装目录的
   `tf_heartbeat.py daemon --session <sid> --generation <generation>` 且 state 仍匹配时才允许继续。
3. 调用 `python3 ~/.tranfu/tf_heartbeat.py stop --session <sid>` 写 drain，轮询最多
   `REPORT_TIMEOUT_SECONDS + 2s`，确认 state 消失/进入 terminal tombstone 且原 PID 已退出。
4. 若超时，重新读取 PID 启动 token、命令和 state generation；三者仍与快照一致时仅发送一次 `SIGTERM`。
   PID 已复用、generation 已变化或命令不匹配时停止操作并报告，不使用 `SIGKILL`、`pkill` 或模糊进程名。
5. 不杀 owner PID，不预先删除 state。停止后默认等待服务端 180 秒掉线规则自然转 idle；如需立刻闭卡，
   把“一条 `idle / heartbeat orphan cleanup`”作为另一个需显式授权的生产写动作。

本机已确认的首个目标是 `019fb774-be5a-7fd1-bb61-ab1360f9dcad`；执行时必须重新 inventory，
不能复用诊断时的 PID `99704` 作为未经复核的删除/kill 目标。其他机器上的孤儿只能由对应机器执行同样步骤，
或在新 shim 被真实 hook 再次调用后由新生命周期规则接管。

## 2. 根因层：四道生命周期闸门

### 2.1 可信活动硬截止

state schema 增加：

- `request_at_ns`：hook 进程在派生 helper 前取得的本机请求顺序时间。
- `last_trusted_activity`：最近一次 `UserPromptSubmit` / `PreToolUse` start 请求时间。
- `activity_deadline`：`last_trusted_activity + TF_HEARTBEAT_MAX_SILENCE_SECONDS`。
- `stopped_at_ns`：最近 terminal stop 请求时间，兼作 tombstone。

新增 `TF_HEARTBEAT_MAX_SILENCE_SECONDS`，默认 `14_400` 秒（4 小时），最小值在代码中设有合理下限。
只有 start helper 可把 `activity_deadline` 更新为“当前可信活动 + 4h”；daemon 的 owner 检查只允许续现有软
`lease_expires`，永远不能更新硬截止。

daemon 每轮先检查 stop/tombstone，再检查硬截止，然后才检查 owner：

- 达到硬截止，即使 owner 仍存活，也发送一次 `idle / heartbeat activity deadline` 并退出。
- owner 明确死亡仍立即 idle 退出。
- owner 检查不可靠时仍沿用现有软 TTL；硬截止始终存在并给出最终上界。
- 新可信 hook 到来时允许启动新 generation 或延长仍健康 generation；真实活动可让跨多个工具的长 session
  超过 4 小时，但单个完全静默 turn 最多由 heartbeat 担保 4 小时。

选择 4 小时是因为 #121 的真实长任务验收样本约 1 小时 45 分，4 小时提供超过 2 倍缓冲，同时把本次
34–65 小时的无限泄漏收敛到有界范围。代价是单个工具/子代理若连续超过 4 小时且没有任何可信 hook，
4 小时后的部分会被低估；已知存在这种任务的环境可显式调大配置。相比 24 小时上限，4 小时能有效阻止
“周五一路计到周一”；相比直接恢复 30 分钟 TTL，又不会回归 #121 要解决的 1 小时 45 分长静默漏计。

### 2.2 异步 start/stop 顺序与 terminal tombstone

当前 helper 由多个独立 `Popen` 异步启动，进程调度可能让较早的 start 在较晚的 Stop 之后才真正拿锁。
修复后 hook 在派生 helper 前生成 `request_at_ns` 并传入：

- stop 写入 `stopped_at_ns=request_at_ns` 和 `stop_requested=true`。
- start 的 `request_at_ns <= stopped_at_ns` 时必须忽略，不能创建新 generation、清除 stop 或续期。
- `request_at_ns > stopped_at_ns` 表示真实的新 prompt/tool，可以创建新 generation。
- daemon 因 stop 退出时保留轻量 terminal tombstone，而不是立即删除全部顺序证据；后续更新采用原子写与现有
  session lock。新 start 已可凭更晚时间覆盖 tombstone，旧 tombstone 可按有界保留期清理，避免目录无限增长。

这解决“Stop 发出但迟到 start helper 又把 daemon 拉起”的本机竞态；硬截止仍负责 Stop 完全缺失的情况。

### 2.3 服务端 terminal fence

`POST /v1/events` 在保留现有 profile/skill/shim side effect 顺序的前提下，对固定 synthetic 事件
`status=running && current_step='turn heartbeat'` 增加保护：

- 同一身份/session 的最新事件若为 `done/error/idle`，该 heartbeat 返回 200 的 ignored/heartbeat 结果，
  不 INSERT、不更新 terminal 行 `last_seen`、不把 state 标脏。
- 新的真实 `prompt/tool/...` active 事件先到后，最新事件不再是 terminal，后续 heartbeat 正常工作。
- heartbeat 与 Stop 并发时，无论谁先取得写锁，Stop 之后的下一条 heartbeat 都无法重开 terminal session。

这一层不替代客户端硬截止：Stop 整体缺失时服务端看不到 terminal，仍由 4 小时活动截止兜底。

### 2.4 服务端 synthetic 活动截止（兼容未升级客户端）

服务端不能假设所有 operator 机器都已升级新 shim，也不能假设能逐台 drain。写侧因此必须独立维护与客户端同口径的
4 小时上界：

- 固定 synthetic heartbeat 名称首先认当前已分发 #121 的确切值 `turn heartbeat`；未来若重命名，服务端 MUST
  在旧 shim 支持窗口内同时识别旧名与新名，不能直接替换导致旧 daemon 绕过 fence。
- 对同一身份/session 收到 synthetic heartbeat 时，查询最近一条非 synthetic 真实 active 事件的服务端 `recv`。
  synthetic 接收时间超过该时间 `TF_HEARTBEAT_MAX_SILENCE_SECONDS` 后，返回 200 ignored，不 INSERT、不更新
  `last_seen`、不进入 pending，也不把 state 标脏。
- 在截止前，synthetic `last_seen` 也不得超过 `trusted_recv + 4h`；批量 pending 与即时写路径都使用同一个允许上界，
  防止截止前排队的较晚 pending 在截止后 flush 突破上限。
- 新的非 synthetic active 事件立即刷新可信活动锚点；terminal fence 仍优先关闭 turn。
- 这一规则只约束 synthetic heartbeat。普通真实 hook 事件、旧协议非 synthetic 心跳和 ADR-0025 聚合均不改义。

该层让已在其它机器运行、没有 terminal、也没有升级机会的旧 orphan daemon在部署后最多保留到最近真实活动 + 4 小时，
之后其每分钟请求仍返回 200 但不再推进生产历史。客户端升级与现场 drain只负责更早释放本机进程资源。

## 3. 历史订正层：只预览，用户决定是否执行

### 3.1 识别与裁剪规则

先实现只读 preview，不直接生成宽泛 UPDATE。preview MUST 扫描完整保留窗口而不是预设六条：

1. 以 `operator + agent||runtime + session_id` 排序服务端 `recv/id`。
2. synthetic heartbeat 定义为 `status=running && current_step='turn heartbeat'`；其他 active hook 是可信活动，
   `done/error/idle` 是 terminal。
3. terminal 后、下一条可信 active 前的 synthetic heartbeat 全部 unsupported，贡献 0。
4. 没有 terminal 的开放段，synthetic `last_seen` 最多保留到最近可信活动 `recv + 4h`；超过部分截断。
5. preview 输出所有候选 session 的 row id、身份、原/新 `last_seen`、需要删除的纯 orphan resume 行、判定原因、
   逐 session/逐日 before/after；逐日汇总至少覆盖 2026-07-31 起到导出快照末日。
6. 六条已确认 session 只作为回归基线，不作为扫描过滤器。用户在完整候选表上圈定 allowlist；没有人工确认的
   session 不进入写方案。

若用户选择订正，执行顺序是：先部署根因修复并停止孤儿 → 复制完整 DB 和校验哈希 → 维护窗口暂停写入并 flush
pending → 在单事务内仅对 allowlist 执行：跨 cutoff 的行把 `last_seen` 收窄到 cutoff，完全位于 unsupported
区间的内部 heartbeat/resume 行移入可恢复审计备份后删除 → commit 后清 state cache → 用同一 preview 对账。
任何行数或逐日秒数与批准 preview 不一致都回滚事务。

### 3.2 全库只读 preview 结果

对 SHA-256 `8d192886cc61965bd472b8be1a3edeaad96188a7ca70203c45f6c9ddd67ae988` 的导出库全量扫描后，
源文件 hash、size、mtime 均未变化，共命中 8 个候选 session。六条已确认孤儿全部在内；另发现两条边界候选：

- `019f92e5-0691-7b50-91cd-e6920aa5ef02`（小北 / codex）：只有 7/31 超过 4 小时上界的 `last_seen`，
  影响 `1:03:22`，没有污染 8/1–8/3。
- `019fa764-ce09-7d53-b693-fe707cb8792f`（程鹏 / 万能百宝箱）：terminal 后又出现一行 synthetic heartbeat，
  影响 8/2 `0:03:11`。

若按规则批准全部 8 条，逐日结果为：

- `2026-07-31`：`131:32:28` → `125:45:26`（减少 `5:47:02`）。
- `2026-08-01`：`138:59:02` → `17:52:47`（减少 `121:06:15`）。
- `2026-08-02`：`167:21:36` → `23:58:21`（减少 `143:23:15`）。
- `2026-08-03` 导出快照：`68:20:25` → `14:25:55`（减少 `53:54:30`，进行中日期）。

若只批准原六条，8/1 仍为 `17:52:47`，8/2 为 `24:01:32`；7/31 保留小北候选的 `1:03:22`，
8/3 只有按最终身份先舍入再汇总造成的一秒边界差异，最终仍以批准 allowlist 的再次 preview 为准。

### 3.3 用户选项与不订正后果

- **A. 不订正**：风险最低，保留原始生产历史；8/1–8/2 会永久维持 138h59m / 167h22m，趋势、排行、
  平均时长和 Agent 详情继续被污染，但部署后不再继续增长。
- **B. 查看全库 preview 后圈定 allowlist（推荐）**：preview 一次性列出全部候选与 7/31 起每日影响，用户可全选、
  排除疑似真实长任务或仅选六条已确认项；会不可逆改变生产历史，因此必须显式批准并依赖备份恢复。

## 4. 验收设计

### 自动化可核查断言

1. owner 永久存活、没有 Stop、没有新可信活动：fake clock 到 `activity_deadline` 前持续 heartbeat；到 deadline
   后只发一次 idle，daemon 在一个 control poll + report timeout 内退出，state 不再续租。
2. 1 小时 45 分静默任务：默认 4 小时配置下 daemon 不提前退出；新的 PreToolUse 会把 deadline 延到该事件后 4 小时。
3. 真正超过 4 小时的单工具：默认配置在 4 小时边界退出；显式调大配置后按新边界退出，测试锁定该已知取舍。
4. 先 start(request=100)、再 stop(200)、最后迟到 start helper(100)：generation 不重开；新 prompt start(300)
   可以覆盖 tombstone并正常启动。
5. done 后 heartbeat：events 行数和 terminal `last_seen` 不变；heartbeat 先到、done 后再 heartbeat也不重开；
   done 后 prompt 再 heartbeat则正常接受。
6. 没有 terminal 的旧 synthetic daemon：服务端在最近真实活动 + 4h 前允许推进，到边界后连续请求都返回 200但
   events/pending/`last_seen`/state revision不再变化；新真实活动可重新打开 4h 窗口。
7. 截止前入队、截止后 flush 的 pending 不得把 `last_seen` 推过可信活动 + 4h；旧/新 synthetic 名称兼容集合回归。
8. stop、deadline、owner-dead 并发只产生一个 terminal idle，daemon 不在 terminal 后再发 running。
9. preview 在导出 DB 上逐秒复现当前基线，扫描完整窗口并输出全部候选和 7/31 起逐日 before/after；全程 query-only。

### 真实运行/UI 验收

1. 本地把 `TF_HEARTBEAT_MAX_SILENCE_SECONDS` 临时设为 120 秒，启动测试 session 后故意不发 Stop且保持
   owner 进程存活；打开 `/agents?w=today`，观察该 Agent 先增长，超过 120 秒及一次上报/刷新容差后转 idle，
   连续两次刷新时长不再增长。恢复默认配置后再做其它验收。
2. 在测试环境制造 `done` 后迟到 heartbeat；打开 `/agents?w=today`，该 Agent 保持 done/idle，窗口时长不因
   后续 heartbeat 增长；再发送真实新 prompt 后，页面才重新显示运行和增长。
3. 部署根因修复但尚未订正历史时，打开 `/agents` 选择 custom `2026-08-01..2026-08-02`：历史值仍约为
   `138:59:02` / `167:21:36`，明确证明代码部署没有暗改历史。
4. preview 生成后打开本地只读报告，对照 `/agents` custom `2026-07-31..2026-08-03`：报告列出全部候选，
   每一天都有 current/corrected/delta，六条已知 session 必须包含在内；用户尚未批准时生产页面保持原值。
5. 只有用户批准并执行 allowlist订正后，再打开同一入口：页面逐日值等于批准 preview；若只批准已知六条，
   8/1 约 `17:52:47`、8/2 约 `24:01:32`。趋势 tooltip、八卡、排行和明细使用同一订正日序列。
6. 打开包含两个真实重叠 session 的测试窗口：页面仍按 ADR-0025 显示两 session 时长之和，证明本修复没有
   顺手改成墙钟并集或 24 小时封顶。

### 项目门禁

实现阶段除定向测试外，运行全量 pytest + coverage（server 每文件/整体门槛按仓库配置）、shim py_compile、
`tf_report --print`、前端 unit/build；UI 完成声明必须附上述真实入口观察记录，构建成功不能替代。

## 5. 风险、回滚与方案反思

- 4 小时上限会低估极少数真正超长的单工具静默段；配置逃逸和可信 hook 延期是明确补偿，不允许 daemon 自续硬截止。
- wall-clock request ordering 可能受系统时间调整影响；实现时优先采用同一启动周期跨进程可比较的 monotonic 值，
  若目标平台不能保证，再使用 wall time + generation/tombstone 守门并补时钟回退测试。
- 服务端识别固定 `turn heartbeat` 是有意的内部协议耦合，需把常量集中并同步 spec，避免字符串分叉。
- 历史订正与根因实现严格分开；未获用户批准时 tasks 中历史写入项保持未执行，不能因代码已验证而顺带运行。
- 根因代码可回滚到 #121 行为；止血和历史订正属于独立外部动作，分别需要现场 inventory/授权和 DB 备份恢复。
