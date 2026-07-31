# 任务：turn-heartbeat-duration-accuracy

## 方案与事实源

- [x] 读取根/服务端 AGENTS、module map、ingest/board/onboarding 规格及相关 ADR。
- [x] 确认 `STALE_SECONDS` 四处语义，决定独立 900 秒历史切段阈值。
- [x] 确认中档心跳上线后 900 秒仍保留为历史补偿/异常兜底。
- [x] 确认低档② `PostToolUse` 不做，避免重复事件和额外热路径开销。
- [x] 写 proposal/design/spec delta，列出真实页面验收语句。

## 服务端

- [x] 新增 `ACTIVE_SEGMENT_GAP_SECONDS=900`，仅替换 board 连续段切分引用。
- [x] 保持 ingest 180 秒恢复边界、board 180 秒在线判定、admin 180 秒删除保护不变。
- [x] 增加历史长静默、900 秒边界、跨日和 API 共享秒数回归测试。

## shim 心跳器

- [x] 新增 stdlib-only `shims/tf_heartbeat.py`：start/touch/stop、按 session 隔离、原子锁、PID/租约、周期发送、TTL 自杀和静默失败。
- [x] 为 `tf_report.py` 增加仅供 heartbeat 使用的 `--no-spool` 发送开关：跳过 spool flush，失败不写共享 spool；普通 done/error/skill 仍保留原有 spool。
- [x] 在 `tf_hook.py` 接入 Claude/Codex `UserPromptSubmit`/`PreToolUse` start、`Stop`/`SessionEnd` stop，并保持无 session_id 安全 no-op。
- [x] 覆盖宿主 PID 身份变更、Claude 被 kill/TTL 到期发送一次 idle 且不增加 error/runs、daemon 每轮可靠检查后自续租、Stop drain 不等待/不阻塞、同 session 去重和多 session 并发。
- [x] 明确不接入 `PostToolUse`，不改变 `tf_hooks.py` 事件安装清单。

## 分发与文档

- [x] 让 manifest 自动包含 `tf_heartbeat.py`，补充 `install.sh` fallback 清单和必要 shim README/模块地图说明。
- [x] 将 spec delta 合并回 `openspec/specs/`，必要时同步 `docs/architecture/module-map.md`；不新增协议字段。

## 验证

- [x] 运行 shim 定向测试、Agents/heartbeat 定向测试、服务端 `py_compile`、`bash -n install.sh`。
- [x] 运行全量 `pytest` 与服务端覆盖率门槛；运行前端 unit/build 作为共享仓库回归。
- [x] 在真实运行页面执行“40m→接近1h45m”和“退出后不再 running”验收，并记录页面入口/观察信号。
- [x] 在真实运行页面执行反向上界验收：session 时长不超过服务端 start→stop 墙钟跨度；kill 后至少两个观察周期内时长不再增长。
- [x] 完成符合度反思，确认无 `PostToolUse`、无新 token/费用字段、无运行期第三方依赖。
