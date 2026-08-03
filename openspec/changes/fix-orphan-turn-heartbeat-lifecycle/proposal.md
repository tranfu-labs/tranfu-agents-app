# 提案：fix-orphan-turn-heartbeat-lifecycle

## main / 并行工作审计

- 当前 worktree、`main` 与 `origin/main` 都在 `9698602 feat: humanize agent step display (#122)`。
- `b01af6b fix: split active gap threshold and add turn heartbeat (#121)` 首次新增完整的
  `shims/tf_heartbeat.py`，并在 `tf_hook.py` 接入异步 start/stop、owner 存活自续租和 turn heartbeat；
  本次孤儿心跳缺陷由 #121 引入。
- `9698602/#122` 只修改步骤展示、board 的 `pod_step` 投影和相关文档/测试，没有修改 heartbeat 生命周期。
- 现有 worktree 中没有未提交的 `tf_heartbeat.py` / `tf_hook.py` / `test_turn_heartbeat.py` 改动。
  `moebius/XpqrrCC3vDq9` 是已合并 #121 的旧源分支，其他活跃分支处理步骤展示或更早任务；当前没有并行修复与本 change 冲突。

## 背景

#121 的 daemon 在 owner PID 可可靠确认存活时会自行续租。Codex Desktop 的 owner 实际可能是跨 session
常驻的 `codex` 进程；一旦 `Stop` drain 缺失、异步 helper 乱序或未生效，owner 仍活着就会让 daemon
无限续租并持续上报 `running / turn heartbeat`。

2026-08-03 对生产导出库的只读诊断确认：至少六条 session 在 7 月 31 日最后一次可信 hook 活动之后，
仍把 `last_seen` 推进到 8 月 2–3 日；其中五条已有 `done`。本机 session
`019fb774-be5a-7fd1-bb61-ab1360f9dcad` 的 heartbeat PID `99704` 已成为 PPID=1 的孤儿，
状态仍为 `stop_requested=false`，而 owner PID `2460` 是常驻 Codex 进程。

这使 `/agents` 的总运行时长从真实事件证据之外继续增长。8 月 1 日页面/API 为 `138:59:02`，
8 月 2 日为 `167:21:36`；六条已确认异常 session 分别贡献 `121:06:15` 与 `143:20:04`。

## 提案

本修复分为互不混淆的三层：

1. **止血（运维动作，方案阶段不执行）**：只对经过 state generation、PID 启动身份和命令行三重核验的
   heartbeat daemon 写 drain；超时仍存活时只向同一个已复核 PID 发 `SIGTERM`，绝不 `pkill`、不杀 owner、
   不直接删状态文件。确认停止后等待现有 180 秒掉线规则自然转 idle；如需立即关卡，另行授权后再发一条明确的
   `idle` 事件。
2. **根因修复**：保留 owner liveness 作为软续租，但新增 owner 无权续期的“可信 hook 活动硬截止”；默认每次
   `UserPromptSubmit` / `PreToolUse` 最多担保后续 4 小时，只有新的真实 hook 活动能延长，daemon 自己不能延长。
   同时为异步 start/stop 加请求时间与 terminal tombstone，阻止迟到 start helper 覆盖 Stop；服务端拒绝终态之后、
   新真实活动之前到达的纯 `turn heartbeat`。服务端还独立按“最近真实活动 + 4 小时”裁剪 synthetic `last_seen`，
   即使旧客户端 daemon 已在其它机器运行、没有 terminal、也尚未升级，仍不能无限推进时长。
3. **历史订正（用户决策项，本 change 不执行生产写入）**：先对完整保留窗口生成全库只读 preview，以同一未来
   规则识别和裁剪全部 unsupported heartbeat，输出所有候选 session 和 7 月 31 日起逐日 before/after；再由用户
   看完整候选表圈定最终 allowlist或选择不订正。任何 UPDATE/DELETE 前必须
   停止对应 daemon、备份数据库、暂停/排空 pending heartbeat，并在单事务内执行且输出前后逐日对账。

## 非目标

- ADR-0025 的跨 session 重叠累加保持不变。它放大了异常输入，但不是本次生命周期缺陷的根因；是否改为墙钟并集
  属于独立产品决策。
- 不新增 token、成本或敏感内容采集，不增加第三方依赖，不改变正常 `running/started/waiting/blocked` 计时口径。
- 方案阶段不停止本机进程、不修改生产数据库、不部署、不发布。

## 影响

- shim：`shims/tf_heartbeat.py`、`shims/tf_hook.py`、对应 README 和生命周期单元测试。
- ingest：`server/routes/ingest.py` 对 terminal 后迟到 synthetic heartbeat 的保护及回归测试。
- 分发/事实源：manifest 自动包含原路径文件，无新增运行依赖；同步 ingest spec、AGENTS、模块地图和必要运维说明。
- board/frontend：不改 API schema 与页面结构；只因不再接收虚假活跃证据而显示更短、更稳定的运行时长。
