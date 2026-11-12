# tasks:dsh-heartbeat-stop-on-subagent

- [x] 1. 用例梳理:根会话轮末、子 agent 轮末、agent 销毁、session 销毁、无 session id、重复终态去重。
- [x] 2. 复现测试:tests/dsh_shell.test.mjs 两条用例在旧壳上失败。
- [x] 3. 修复 shims/dsh/index.js(agent.ctx 注册 + agent/disposed + stopOnce)与 tf_dsh_event.py 映射。
- [x] 4. 本地真实 dsh headless 会话验证:全部会话正确停止、无泄漏。
- [ ] 5. 桌面版重启后确认看板当日时长回落到真实量级。
