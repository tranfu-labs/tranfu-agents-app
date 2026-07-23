# 设计：fix-heartbeat-pending-consistency

行为增量见 `spec-delta/ingest/spec.md`。

## 方案

### 1. 统一“最后确认心跳”

新增小型时间选择 helper：解析 SQLite `last_seen`（缺失时回退 `recv`、`ts`）和同事件 id 的 pending，
返回时间最大的原始 UTC 字符串。单个脏值只被忽略，不阻断其它有效候选。

同状态、同步骤的断档判断只消费该 helper，保证：

- DB 较新时不被旧 pending 回退。
- pending 较新时仍参与 `STALE_SECONDS` 判断。
- 两者缺失或无法解析时保持现有保守行为，不因解析异常拒绝事件。

### 2. pending 生命周期

在 ingest 已持有 `app._lock` 的前提下：

- 纯心跳继续只更新 pending。
- profile、skill 或 shim 版本等语义写入要求即时更新同一事件行时，先移除该事件旧 pending，再以当前
  `recv` 更新 DB；旧 pending 不得在稍后 flush 回退 DB。
- 即将插入任何新事件行时，调用统一 helper：若 pending 比旧行 DB 端点更新，先更新旧行
  `last_seen`；随后移除 pending。该操作不区分状态变化、步骤变化或同状态 stale recovery。

pending 的读取、固化和删除都发生在同一 `app._lock` 临界区内，避免同一事件的写侧交接被 flush 穿插。

### 3. flush 原子协调

ingest 的既有锁顺序是 `app._lock → _heartbeat_pending_lock`。flush 改为相同顺序：

1. 获取 `app._lock`。
2. 获取 pending lock 并复制当前 batch。
3. 在仍持有 `app._lock` 时批量更新 SQLite 并 commit。
4. 只清除本次成功写入且值未被替换的 pending 项。
5. 释放锁后标记 board state dirty。

第 4 步保留值比较，作为 helper 可独立调用时的防御；正常生产路径中 ingest 无法在全局写锁内并发改写
pending。DB 写或 commit 失败时不清 pending，允许后续重试，不把内存中的最后确认心跳静默丢失。

## 单元测试

- `00:00 running → 00:02 pending → 00:03 skill 即时写 → 00:05:30 heartbeat`：
  不插入 `heartbeat_resume`，DB `last_seen` 不回退，最新心跳继续进入 pending。
- `00:00 running → 00:02 pending → 00:10 done`：插入终态前旧行固化到 `00:02`，活跃区间为 120 秒，
  pending 清空。
- flush 已取得 pending 快照但 SQLite 尚未 commit 时，并发 ingest 不得观察空 pending；flush 完成后
  `00:04:30` 相对 `00:02` 仅 150 秒，仍为普通 heartbeat。
- flush 数据库写失败时 pending 保留，下一次 flush 可重试。
- 既有阈值内纯心跳、长断档恢复、batch 禁用、state dirty 行为保持通过。

## AI / 运行验证

- 用 TestClient 和受控 `now_utc` 复现上述三个 QA 时序，检查事件行、pending map 和
  `/api/agents?w=today` 时长。
- 用线程与同步 Event 卡住 flush 的 DB commit 窗口，确认 ingest 只会等待，不能在交接中间态做断档判断。
- 运行 `py_compile`、全量 pytest、server 覆盖率、前端单测和生产构建。

## 权衡

- 不把 pending 合并进数据库新表：它仍是允许最多丢一个 batch 窗口的进程内优化，本次只修原子性。
- 不使用单独的新协调锁：`app._lock` 已是所有 ingest SQLite 写的串行化边界；复用它能保持锁模型简单。
- 不在 flush 前清空 map 后失败补回：补回会覆盖期间更新并引入更复杂的版本合并；持锁写成功后再条件清除
  更容易证明正确。

## 风险

- 锁顺序不一致会死锁；所有同时需要两把锁的路径必须固定为
  `app._lock → _heartbeat_pending_lock`，不得反向获取。
- flush 持有全局写锁的时间略增，但原实现本就用同一锁执行 SQLite batch，新增部分只是一份内存快照。
- 测试夹具可单独获取 pending lock 清理状态，但不得在生产写路径持 pending lock 后再请求 `app._lock`。

## 方案反思

- 修正覆盖 QA 的三个具体失败场景，同时把 DB/pending 交接收敛到一个可复用 helper，避免为状态变化和
  stale recovery 各写一套分支。
- 失败恢复有明确语义：SQLite 失败时 pending 留存，不会用“清空后补回”赌并发时序。
- 改动不触碰 board 时长算法，能把回归风险限制在心跳证据写入域。

## 实现后反思

- `_latest_heartbeat` 同时解析 SQLite、pending 与当前 `recv`，以真实时间最大值选择确认点；无时区的
  legacy 值按 UTC 解释，单个脏值不会阻断采集。
- 即时语义写入在 SQLite commit 成功后才淘汰旧 pending；状态/步骤变化和
  `heartbeat_resume` 都先调用 `_persist_pending_heartbeat`，commit 成功后才删除 pending。
- `flush_heartbeat_batch` 统一为 `app._lock → _heartbeat_pending_lock`，map 在 SQLite commit 前始终
  可见；批量 SQL 另以 `julianday` 守住 `last_seen` 单调不减，写入失败自然保留整个 batch。
- 并发回归用可控锁让旧实现稳定暴露“map 已空、DB 未写”的窗口；修正后 ingest 读到 pending 并返回普通
  heartbeat，不生成伪 `heartbeat_resume`。
- board 聚合和前端均未改动；状态变化回归通过 `/api/agents` 验证最终活跃时长为已确认的 120 秒。

## 验证结果

- 新增四个 QA 回归在旧实现上稳定表现为 4 failed；连同 legacy UTC 用例，修正后
  heartbeat/Agents targeted tests 为 41 passed。
- `python -m py_compile server/*.py server/routes/*.py`：通过。
- `python -m pytest -q`：384 passed。
- `python -m coverage run -m pytest -q`：384 passed；
  `python -m coverage report --include='server/**/*.py'`：整体 97%，`server/routes/ingest.py` 95%。
- `npm --prefix frontend run test:unit`：77 passed。
- `npm --prefix frontend run build`：通过；仅保留既有单 chunk 超过 500 kB 的 Vite warning。
- `server/app.py`：210 行，低于 220 行模块边界门槛。
