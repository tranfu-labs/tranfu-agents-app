# onboarding 规格增量：turn 心跳 shim 生命周期

## 规则增量

- `/shims/manifest` 与 manifest 安装流程 MUST 分发新增 `tf_heartbeat.py`；manifest 失败时的安装 fallback 也 MUST 下载该文件。
- Claude Code / Codex 的共享 `tf_hook.py` MUST 在 `UserPromptSubmit` 或 `PreToolUse` 为有 `session_id` 的 turn start/touch session 心跳器，在 `Stop` 或 `SessionEnd` 停止同一 session；不新增 `PostToolUse` hook 安装项。
- 心跳器 MUST 按 session 隔离进程和状态，启动操作幂等；宿主 agent 被 kill、PID 身份失效、状态残留或固定 TTL 到期时 MUST 自动回收，且不得误杀另一 session。异常回收前尝试发送一次 `idle` 关段事件；显式 Stop/SessionEnd 只写 drain 后立即发送既有 `done`，不等待 ack。
- daemon 每轮宿主检查可靠且仍存活时 MUST 自行续租；只有宿主检查不可用时固定 TTL 才作为绝对兜底，不能因长工具缺少 hook touch 而提前退出。
- shim 继续只依赖 Python 标准库、不得抛错或阻塞宿主 agent；等待用户输入期间不得运行 turn 心跳器。

## 可验证行为增量

- 重复安装现有 Claude/Codex hooks 不增加事件组；新 shim 通过下一次 hook 触发即可生效，`tf_hooks.py` 的既有 `SessionStart/UserPromptSubmit/PreToolUse/Stop/SessionEnd` 清单保持一致。
- 长工具运行期间每个心跳间隔最多发送一个同 session `running` 事件；Stop 后该 session 不再发送 running。
- 同一宿主内两个 session 同时运行时，停止其中一个不会停止另一个；宿主进程被 kill 后孤儿心跳器在宿主探测或 TTL 到期后退出。
- 宿主被 kill 或 TTL 到期后，服务端最终收到一次 idle（网络恢复时可由 spool 补发），该 Agent 今日时长停止增长且 error/runs/质量线索不增加。
- Stop hook 不因 drain 等待网络而阻塞；在途 running 晚到最多影响 180 秒卡片显示，不增加活跃时长。
- `PostToolUse` 不会启动或额外维持 turn 心跳。
