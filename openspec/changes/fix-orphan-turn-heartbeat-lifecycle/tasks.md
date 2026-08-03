# 任务：fix-orphan-turn-heartbeat-lifecycle

## 方案与授权闸门

- [x] 读取 AGENTS、模块地图、board/ingest specs、ADR-0003/0025、#121 change 与当前 heartbeat 实现。
- [x] 核对 `main=origin/main=9698602`、确认 #121 引入缺陷、确认 #122 未修复、检查并行 worktree 无同块未提交修复。
- [x] 形成止血、根因、历史订正三层独立方案，并明确 ADR-0025 不在范围。
- [x] 写出自动化和真实 `/agents` 页面逐条验收依据。
- [x] @dev-manager 核验方案范围、4 小时默认值、server terminal fence、历史 preview 口径和验收清单。
- [x] 主理人放行精确止血与根因实现；生产历史订正仍保持用户授权闸门。

## 止血（独立运维动作，不随代码实现自动执行）

- [x] 重新 inventory 本机 heartbeat state、PID 启动 token、命令行和 generation，输出精确目标清单。
- [x] 获得本机进程操作授权后，对目标逐个 drain；目标正常退出，未使用 SIGTERM，不杀 owner、不 broad pkill。
- [x] 验证目标 PID/state 不再增长；未补发未经授权的 idle 生产事件。
- [x] 其它 operator 机器由服务端兼容闸门立即止住增长；精确 drain 步骤保留在 design，不从本机猜测或远程杀进程。

## 根因实现

- [x] 在 `tf_hook.py` 为 start/stop 捕获并传递可比较的请求时间，保持 hook 非阻塞和失败静默。
- [x] 在 `tf_heartbeat.py` 增加可信活动 deadline、terminal tombstone 和有界清理；owner 只能续软 lease。
- [x] 增加 `TF_HEARTBEAT_MAX_SILENCE_SECONDS=14400` 配置、边界校验与旧 state 安全升级行为。
- [x] 在 ingest 增加 terminal 后 synthetic heartbeat fence，保持 side effect、pending 锁顺序和 200 fail-silent 契约。
- [x] 在 ingest 增加最近真实活动 + 4h 的服务端 synthetic 截止，同时约束即时更新和 pending flush，兼容当前已分发旧名称。
- [x] 保持 ADR-0025 逐 session 累加、900 秒 read-side fallback、180 秒在线判定与 API schema 不变。
- [x] 同步 ingest spec、AGENTS、模块地图、shim README、PROTOCOL/运维文档中确有受影响的生命周期说明。

## 测试与验证

- [x] 单测 owner 永久存活 + Stop 缺失时在 hard deadline 自行 idle/退出且不再续租。
- [x] 单测 1h45 长 turn 不误杀、可信活动延期、默认 4h 边界及配置 override。
- [x] 单测异步 start/stop 乱序、tombstone、新 turn 重启和各 terminal 路径只发一次 terminal。
- [x] 服务端测试 done 后 heartbeat 不推进、并发顺序、done 后新 prompt 恢复、pending/state dirty 不回归。
- [x] preview 在导出 DB 上 query-only 扫描完整窗口，输出全部候选及 7/31 起逐日 before/after，并校验六条已知基线。
- [x] 运行仓库规定的 py_compile、pytest/coverage、shim 检查、前端 unit/build 和模块边界门禁。
- [x] 真实运行/UI 已验收 design §4 的 1–4、6；第 5 条历史订正后页面值仍等待用户批准后执行。

## 历史订正用户决策闸门

- [x] 先只交付全库 preview：全部候选 session、row id、cutoff、7/31 起逐日 before/after、误判风险；源库 hash/mtime 不变。
- [ ] 用户选择 A 不订正或 B 在完整候选表上圈定 allowlist。
- [ ] 只有用户显式选择 B 后，另行核验维护窗口、完整备份/哈希、pending flush、事务 SQL 和回滚步骤。
- [ ] 未获批准时不执行任何历史 UPDATE/DELETE；根因代码完成也不能隐含授权历史订正。

## 符合度与事实源闭环

- [x] 对照 proposal/design/spec delta 检查漏做、多做和范围漂移。
- [x] 根因实现验证通过后合并 spec delta；未批准的历史订正未写入当前行为事实源。
- [ ] 用户完成历史订正决策后记录最终反思与剩余风险，再按项目约定归档 change。
