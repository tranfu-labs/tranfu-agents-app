# 变更提案:dsh-heartbeat-stop-on-subagent(DSH 子 agent 轮末必须停心跳)

- 状态:Implemented locally(真实 headless 会话端到端验证)
- 关联:dsh-runtime-hooks、ADR-0009、tf_heartbeat.py、tf_hook.py

## 背景 / 问题

DSH 接入后看板出现明显虚增:大肥鱼单日 8.8h,本地会话日志重建的密集活动约 1.9h。

根因是启用/停止不对称:心跳由 tools/pre-execute 启动,停止只挂在插件上下文的 session/event 上;
DSH child agent 的 turn/end 只在它自己的 agent.ctx 派发,插件上下文收不到,于是心跳空转到 4h 上限。

本地证据:修复前 ~/.tranfu/heartbeats 有 28 个 stop_requested=False,其中 25 个是子 agent;
这些会话在 DSH 日志里都有 turn/end。

## 目标

- 子 agent 的 turn/end、agent/turn-stopping、agent/disposed 都能停心跳。
- 同一轮只上报一次终态。
- 不改统计口径、不改服务端、不影响其它 runtime。

## 非目标

- 不改并行会话时长相加、重叠不去重的既有口径。
- 不追溯历史数据。
