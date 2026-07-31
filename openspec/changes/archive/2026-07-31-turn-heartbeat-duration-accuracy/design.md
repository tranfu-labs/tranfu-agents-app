# 设计：turn-heartbeat-duration-accuracy

## 方案

### 1. 拆分服务端阈值

- 在 `server/config.py` 新增 `ACTIVE_SEGMENT_GAP_SECONDS = 900`，并保留 `STALE_SECONDS = 180`。
- `server/routes/board.py::_session_active_intervals` 只使用 `ACTIVE_SEGMENT_GAP_SECONDS`；卡片状态判定仍使用 `STALE_SECONDS`。
- `server/routes/ingest.py` 的同状态恢复边界和 `server/routes/admin.py` 的删除保护不改。
- 900 秒选择为 15 分钟：足以覆盖原始建议中的长工具静默段，同时把无心跳异常过计时上限固定在可解释的窗口内。它是读侧历史补偿和客户端故障兜底，不被当作在线状态阈值。

### 2. turn 心跳事件与调度

新增 `shims/tf_heartbeat.py`，只复用现有 `tf_report.py` 和环境变量，不引入新协议字段：

- `start --session <sid> [--owner-pid <pid>]`：按 session 的哈希文件名建立状态，原子创建短锁；已有同 session 且 PID、租约和宿主身份有效时只续租，不再启动第二进程；状态损坏或 PID 已死时清理后重建。
- 新进程 detached、关闭 stdin/stdout/stderr，先发送一次 `--status running --step "turn heartbeat" --session sid`，随后按 `TF_HEARTBEAT_INTERVAL_SECONDS` 周期发送；默认 60 秒。心跳调用 `tf_report.py --no-spool`：该开关跳过既有 spool flush，失败时直接丢弃本轮，不写入共享 `spool.ndjson`；正常 hook 事件仍保留原有 at-least-once spool。
- `stop --session <sid>`：读取该 session 状态并原子写入 drain 请求后立即返回；daemon 以不超过 250ms 的控制轮询看到标记，不等待 stopped ack、不等待网络请求、不阻塞宿主 hook。daemon 看到 drain 后不再开新 heartbeat，完成当前 report 后自行退出；状态文件由 daemon 的 `finally` 按 PID/代次条件清理，避免误删新一轮进程。没有状态、PID 已死或发送失败都静默返回。
- `TF_HEARTBEAT_TTL_SECONDS` 默认 1800 秒。daemon 每轮先检查宿主：检查可靠且宿主仍存活时，daemon 自己把租约续到 `now + TTL`，因此长工具不会因“距上次 hook touch”而退出；宿主检查不可用（没有 owner PID、`ps` 降级或无法取得启动 token）时不续租，TTL 才作为绝对孤儿兜底。宿主明确消失时立即关段退出，不等待 TTL。

宿主消失或 TTL 到期属于无结果的关闭：daemon 在退出前发送一次 `status=idle`、`step` 为固定短标签的关段事件，使用正常 spool（只发生一次，不会被高频心跳挤满），以便立即关闭服务端活跃段；若网络不可达，终态按既有 spool 机制保留，下一次普通上报时补发。显式 Stop/SessionEnd 不发送 idle，由 hook 自己发送既有 `done`。`idle` 不进入质量 runs/error 统计，也不产生 error signal。

### 3. 宿主退出与并发回收

- `tf_hook.py` 在启动心跳前尽可能解析实际宿主 agent PID：从 hook 进程向上跳过 shell/python 包装进程，并记录宿主 PID 的启动身份 token；解析失败时仍使用 TTL，不因诊断失败阻塞 hook。
- daemon 每轮检查宿主 PID 是否仍存活且启动身份未改变；宿主被 kill、PID 被复用或进程进入不可用状态时发送 idle 并退出。PID 启动身份 token 采用一次 `ps -o lstart= -p <pid>` 的无平台分支调用，结果做空白归一化；命令不存在、返回异常或无法取得 token 时进入“检查不可用”状态，停止续租并等待绝对 TTL，不阻塞、不抛错。
- session 状态放在 `~/.tranfu/heartbeats/`，session 只使用哈希作为文件名，不把原始 session 放进路径。短锁采用目录原子创建/删除；锁残留超过锁 TTL 时可回收。不同 session 使用不同锁和状态，因此并发不会互相覆盖或停止。
- `tf_hook.py` 的事件顺序：启动事件先按现有逻辑上报 `running`，成功返回后 start/touch daemon；`Stop`/`SessionEnd` 调用 stop 只写 drain 请求并立即返回，随后按既有逻辑上报 `done`，不让可靠性等待阻塞宿主。正常 daemon 路径会在当前 report 返回后退出，不再开新 heartbeat；极端在途 running 仍可能晚于 done 到达，接受其最多 180 秒的卡片显示瑕疵，但因 board 的单点 active 段要求 `active_last > active_start`，不会造成时长虚增。缺少 session_id 时不启动也不停止任何 session，防止误杀并发会话。
- 仅对 Claude/Codex CamelCase 生命周期启用本 change：`UserPromptSubmit`/`PreToolUse` start，`Stop`/`SessionEnd` stop。Hermes 的 snake_case 生命周期不在本次范围，保留现有单事件上报；不新增 `PostToolUse`。

### 4. 分发与兼容

- `server/shim.py` 自动把新文件纳入 manifest；根 `install.sh` 的 manifest 失败 fallback 也加入 `tf_heartbeat.py`。
- 新文件保持 stdlib-only、所有异常静默；安装/自更新仍按现有 manifest sha256 与 py_compile 流程工作。
- 不改 `tf_hooks.py` 的事件清单，不新增 `PostToolUse`，因此已有 hook 配置无需迁移；下一次 hook 触发即可使用新 `tf_hook.py` 和心跳器。
- 不改 TATP、`PROTOCOL.md` 的字段定义或服务端 ingest 写路径；每个周期事件就是已有的纯 `running` heartbeat，自动进入既有 pending + 15 秒批量落库。
- `tf_report.py --no-spool` 只是客户端发送策略开关，不改变服务端 payload；只有周期 heartbeat 使用它，异常终态和普通 done/error 仍使用原有可靠发送路径。

## 测试与验收设计

### 服务端单元测试

- 直接覆盖 `_session_active_intervals`：相邻 active 事件间隔 900 秒以内不切段，超过 900 秒切段；同时确认 `STALE_SECONDS` 仍为 180。
- 用既有 Agents API fixture 构造“当前约 40 分钟、墙钟约 1 小时 45 分钟”的长静默数据，确认 `/api/state`、`/api/agents`、`/api/agent/:key` 共享追溯后的同一秒数，并覆盖跨上海日切分。
- 保留/补回归 ingest：超过 180 秒的同状态事件仍生成 `heartbeat_resume`；旧卡超过 180 秒不再显示 live/running；本 change 不改变 pending batch、flush 或删除保护。

### shim 单元测试

- `tf_heartbeat.py` 的纯生命周期规则覆盖：同 session 重复 start 只保留一个进程，不同 session 可同时存在；stop 只停止目标 session；失效 PID/租约和宿主身份变更会清理；TTL 到期自杀；report 失败不抛异常。
- `tf_heartbeat.py` 覆盖 heartbeat 失败不写共享 spool、宿主消失/TTL 只发送一次 idle、daemon 每轮可靠宿主检查后自续租、Stop drain 不等待且不阻塞 hook。
- `tf_hook.py` 覆盖 start/stop 事件调用顺序、无 session_id 不操作、`PostToolUse` 不启动心跳，以及现有 report argv 不回归。
- manifest/install 测试确认新文件可取、被列入 manifest，fallback 清单不遗漏；`py_compile` 和 `bash -n install.sh` 通过。

### 真实运行验收（交给 QA）

- 页面入口 `/agents?w=today`：准备一个长静默 session 后刷新页面，断言同一 Agent 的今日运行时长从旧 40 分钟口径提升到接近 1 小时 45 分钟，且 `/api/state`、Agents 排行、Agent 详情显示同一结果；不以“单元测试通过”替代此断言。
- 页面入口 `/` 或 `/agents?w=today`：让 agent 发送 running 后停止/退出并等待超过 180 秒，断言该身份不再显示“运行中/Live”，状态显示 idle 或 done；900 秒不能延长在线展示。
- 真实 Claude Code 会话：在一个长工具/子代理 turn 中观察 `/agents`，每约 60 秒仍收到同 session 的 running 心跳，Stop 后不再新增 running；下一轮 prompt 可以重新拉起且不产生两个并发心跳器。
- 真实多会话：同时运行两个 session，分别 Stop 一个，断言另一个仍持续上报；杀掉宿主进程后，断言孤儿心跳器发出一次 idle、在宿主探测或 TTL 到期后退出，且不会继续无限刷新看板。
- 反向上界：隔离一个真实 session，记录服务端收到首个 running 与 Stop/done 的 `recv` 时刻，在 `/agents?w=today` 刷新并等待 batch flush 后，断言该 session 的今日时长 `active_seconds <= recv_stop - recv_start`（允许页面刷新延迟，不允许超过实际服务端墙钟跨度）。宿主被 kill 后记录 kill 时刻，等待至少两个“心跳间隔 + batch flush + 页面刷新”周期，连续两次刷新断言该 Agent 的今日时长不再增长。

## 权衡

- 不直接把 `STALE_SECONDS` 改成 900：会污染在线状态、ingest 恢复和 admin 删除保护，且让已退出 agent 长时间保持运行中。
- 不采用“有心跳时窄阈值、无心跳时宽阈值”：现有历史事件没有可靠的“这是 turn 心跳器”标记，按事件密度推断会把历史/并发/补发场景混在一起；固定独立的 900 秒切段阈值可重算、可解释、不会改写 180 秒的实时语义。
- 不让 heartbeat 进入共享 spool：断网时一条/分钟的低价值纯心跳会在约 17 小时填满 1000 行上限，挤掉 done、error 和 skill 事件；心跳没有客户端时间戳，丢掉一轮由下一轮补足，不能用 at-least-once 的代价换取错误的历史时间。
- 宿主消失发送 idle 而非 error/done：本 change 只需要无质量副作用地闭合活跃段；idle 已由 board 立即关段且不计 runs/error，避免用户主动退出造成错误线索污染。
- Stop 只写 drain 不等待 ack：等待 6 秒违反 shim 不得阻塞宿主的硬约束，而晚到 running 不会增加时长，只会让卡片最多多显示 180 秒；由 daemon 自己消费 drain 保持零阻塞。
- 不安装 `PostToolUse`：中档心跳本身覆盖工具静默段；PostToolUse 只增加低价值事件和 hook 热路径开销。
- 不升级协议或让客户端本地累计时长：本 change 目标是低/中档修复，沿用服务端权威 `recv`、既有去重和批量落库，避免迁移历史数据。
- 不让一个全局 heartbeat daemon 管理所有 session：全局状态更容易在 Stop、PID 复用或多 agent 并发时误杀；每 session 一个受控 daemon 更容易验证和回收。

## 风险与回滚

- 宿主 PID 识别受不同启动器影响；`ps` 一次调用失败时停止续租并只依赖 PID/TTL 兜底，极端超长 turn 可能在 TTL 到期时结束，需要通过环境变量调大。
- Stop 后已经进入内核或反向代理的 HTTP 请求理论上仍可能晚于 done 到达；这是现有无事件序号协议无法完全消除的边界，时长影响为 0，卡片显示瑕疵上限为 180 秒，且 daemon 不再周期重发。
- 进程/文件权限、信号或系统休眠可能延迟 heartbeat；所有失败静默，服务端仍以 180 秒在线判定和 900 秒历史兜底运行。
- 回滚可删除/停用 shim heartbeat 启动调用并恢复 board 对 `STALE_SECONDS` 的引用；无需 schema 或数据迁移。恢复为 180 秒会重新暴露长静默历史截断，不影响事件安全性。

## 方案反思

- 影响面覆盖了真实问题的两个边界：board 读侧历史补偿与 shim 写侧实时覆盖；没有用一个常量同时改变四种语义。
- 心跳器的状态机、进程、租约、宿主检查和 TTL 都有独立失败路径，且不把可靠性前提放在 Stop 一定到达上。
- 用户可见验收明确绑定页面入口和可断言信号，服务端秒数验证与进程生命周期验证分别由单测和真实运行承担。
