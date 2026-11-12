# 设计:dsh-heartbeat-stop-on-subagent

在插件上下文的 agent/created 里取 agent.ctx,把 per-agent 的 session/event(仅 turn/end)
与 agent/turn-stopping 注册到该 ctx;同时把 agent/disposed 映射成终态。任一来源先到即停,
stopOnce 保证同一会话一轮只发一次。

## 验证

- tests/dsh_shell.test.mjs:子 agent ctx 的 turn/end、agent/disposed 必须产出终态(修复前失败)。
- 真实 dsh --profile headless(含 subagent)端到端:所有会话 stop_requested=True,无泄漏。
- 诊断:TF_DSH_DEBUG=1 写 ~/.tranfu/logs/dsh-events.ndjson。
