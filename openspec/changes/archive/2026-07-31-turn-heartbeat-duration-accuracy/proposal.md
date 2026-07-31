# 提案：turn-heartbeat-duration-accuracy

## 背景

当前服务端把 `STALE_SECONDS=180` 同时用于四种语义：活跃时长连续段切分、看板在线状态掉线判定、ingest 同状态恢复边界和 admin 删除保护。长工具调用或子代理静默超过 180 秒时，历史时长会被截断；直接把这个常量调大又会让已退出 agent 长时间显示为运行中，并扩大恢复写入和删除保护窗口。

客户端目前只在 hook 事件到达时上报。turn 内没有周期性 `running` 事件时，服务端只能用 stale 阈值猜测静默段是否仍在工作，导致今天墙钟约 1 小时 45 分钟的工作可能只统计为约 40 分钟。

## 提案

1. 从 `STALE_SECONDS` 拆出仅供 board 活跃时长连续段计算的 `ACTIVE_SEGMENT_GAP_SECONDS=900`。该阈值在查询时重算，立即追溯修复历史时长；`STALE_SECONDS=180` 的在线展示、ingest 恢复和 admin 语义不变。
2. 新增仅依赖 Python 标准库的 `tf_heartbeat.py`。Claude Code / Codex 的 `UserPromptSubmit`、`PreToolUse` 拉起或复用当前 session 的 detached turn 心跳器，以 60 秒周期发送既有 `status=running` 事件；`Stop`、`SessionEnd` 显式停止它。
3. 心跳器按 session 隔离状态和进程，短临界区用原子文件操作防止同一 session 重复启动；不同 session 可并发。宿主 PID 身份检查、退出清理和 TTL 自杀共同回收 Claude 被 kill、hook 丢失或状态文件残留的孤儿进程。
4. turn heartbeat 走 `tf_report.py --no-spool`，失败时丢弃当前轮，保护共享 spool 中的 done/error/skill 事件；宿主消失或 TTL 到期时只发送一次 `idle` 关段事件，不污染 error/runs 质量指标。
5. Stop/SessionEnd 只写 drain 请求并立即返回，daemon 自行停止后续 heartbeat；hook 不等待 ack、不阻塞宿主，接受在途 running 造成最多 180 秒卡片显示瑕疵但不增加时长。
6. 不安装或新增 `PostToolUse` 心跳钩子。turn 心跳已经覆盖长工具静默段，额外的工具结束事件只增加请求噪声，不提升该问题的覆盖率。

## 影响

- 服务端 board/config 的时长计算常量与历史聚合结果。
- `shims/tf_hook.py`、新增 `shims/tf_heartbeat.py`、shim manifest 和安装 fallback。
- Claude Code / Codex hook 生命周期；不新增 TATP 字段、不改 ingest API 和 SQLite schema。
- onboarding、ingest、board 规格 delta，相关 shim 与 Agents 时长单元测试。
- 用户可见结果：已退出 agent 仍按 180 秒规则及时转 idle；历史长静默段在 Agents/看板今日时长中按 15 分钟切段阈值追溯计入；启用 turn 心跳后新 turn 的时长接近实际 prompt→Stop 区间且不超过服务端记录的实际墙钟跨度；宿主被 kill 后发送 idle、时长停止增长且不产生 error 质量线索。
