# 设计：fix-heartbeat-pending-monotonic-retry

行为增量见 `spec-delta/ingest/spec.md`。

## 方案

### 1. pending 入队单调不减

`_queue_heartbeat` 在 `_heartbeat_pending_lock` 内读取同一事件 id 的已有值，并复用
`_latest_heartbeat` 比较现值与新值：

- 两者都可解析时保留时间较新者。
- 新值不可解析时不覆盖已有有效值。
- 首次入队仍保留当前服务端生成的 `recv`。

比较与写入在同一 pending lock 临界区完成，所以即使两个请求在取得 `app._lock` 前已经分别生成不同
`recv`，后取得锁、后入队的较早请求也不能把时间倒退。

### 2. 单轮 flush 失败隔离

`_heartbeat_flush_loop` 维持既有间隔与 batch 开关语义，只把每轮
`flush_heartbeat_batch()` 包在 `try/except Exception` 中：

- 成功时按既有原子路径更新 SQLite、清除对应 pending 并标记 state dirty。
- 失败时异常不逃出循环；`flush_heartbeat_batch` 的既有事务/清理顺序保证 pending 仍保留。
- 下一轮重新读取配置间隔并重试同一 pending。

不在失败时将 `_heartbeat_thread_started` 复位，因为线程并未退出；这避免并发启动第二个 flush 线程。
不捕获 `BaseException`，保留解释器退出等非普通运行时终止语义。

## 单元测试

- 建立 `00:00` 事件后，按 `00:02 → 00:01` 顺序向同一事件 pending 入队，再于 `00:04:01`
  上报相同状态/步骤：仍返回普通 heartbeat、不生成 `heartbeat_resume`，pending 最终推进到
  `00:04:01`。
- 构造一个 pending，令后台循环第一次 flush 抛出瞬时 SQLite 异常、第二次使用真实连接成功：
  循环必须进入第二轮，SQLite `last_seen` 更新为原 pending，pending 随后清空。
- 既有 flush 直接调用失败仍向调用方抛错且保留 pending；只有后台循环负责隔离和自动重试。

## AI / 运行验证

- 单独运行新增测试，先确认旧实现分别产生伪恢复行和终止循环，再确认修复后通过。
- 运行 heartbeat/Agents 相关 targeted tests、`py_compile`、全量 pytest 与 server 覆盖率门槛。
- 运行前端 unit 与 production build，确认共享仓库门禁未受服务端修复影响。

## 权衡

- 不把 `recv` 移入全局写锁后生成：服务端权威时间应尽量接近请求进入时刻，而且所有 pending 更新都应
  自身满足单调性，不能依赖调用时序规避。
- 不在 `_queue_heartbeat` 外预先比较：检查与赋值必须在同一锁内，否则仍有 TOCTOU 竞争。
- 不让 `flush_heartbeat_batch` 本身吞异常：显式调用方和测试仍应观察失败；只有长期运行的后台循环负责
  容错与重试。
- 不新增重试退避或日志系统：下一既有 batch 间隔已经提供有界重试节奏，本次不扩张运行模型。

## 风险

- 宽泛捕获普通异常可能隐藏持续性数据库故障；pending 会保留且每间隔重试，现有服务没有日志设施，
  本次保持最小修复，持续故障仍可由 liveness 冻结与服务监控发现。
- 时间比较必须继续兼容 legacy naive UTC 值；复用已覆盖该兼容性的 `_latest_heartbeat`，不引入第二套解析。
- 测试后台无限循环时必须提供受控终止哨兵，避免留下测试线程或忙等。

## 方案反思

- 两个修改都位于问题真实边界：入队处保证单调，长期循环处保证生命周期；无需改 board 或增加补偿任务。
- 失败路径继续依赖已验证的“commit 成功后才清 pending”，因此自动重试不会丢失同一批证据。
- 测试同时验证内部 map 和外部事件分段结果，避免只锁实现细节而遗漏业务影响。

## 实现后反思

- `_queue_heartbeat` 在 pending lock 内复用 `_latest_heartbeat` 完成比较与赋值，较旧或不可解析的新值
  均不能覆盖已有有效端点；服务端 `recv` 的生成位置和权威时间语义保持不变。
- `_heartbeat_flush_loop` 只隔离 `flush_heartbeat_batch` 的普通异常，`time.sleep` 与
  `BaseException` 仍保留原有终止语义；直接调用 flush 也继续向调用方报告失败。
- 自动重试继续使用原子 flush 的“commit 后条件清除”路径，第一次失败时 pending 原样保留，第二次
  成功后更新 SQLite、清 map 并标记 state dirty。
- 新测试在旧实现上稳定为 2 failed：分别观察到 `00:02 → 00:01` 回退和首次异常逃出循环；修复后
  两条均通过，heartbeat/Agents 共同口径回归也全部通过。
- 改动没有触碰 board、前端、schema、历史事件或 API 契约，符合最小影响范围。

## 验证结果

- 新增回归旧实现：2 failed；修复后：2 passed。
- `python -m pytest -q tests/test_heartbeat_batch.py tests/test_agents_dashboard.py`：43 passed。
- `python -m py_compile server/*.py server/routes/*.py`：通过。
- `python -m coverage run -m pytest -q`：386 passed。
- `python -m coverage report --include='server/**/*.py'`：整体 97%，`server/routes/ingest.py` 96%。
- `npm --prefix frontend run test:unit`：77 passed。
- `npm --prefix frontend run build`：通过；仅保留既有单 chunk 超过 500 kB 的 Vite warning。
- `server/app.py`：210 行，低于 220 行模块边界门槛；`git diff --check`：通过。
