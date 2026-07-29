# 任务：sum-overlapping-agent-sessions

## 方案与范围闸门

- [x] 读取 AGENTS、模块地图、board/ingest specs、ADR-0003/0006/0013、上一轮时长修复 change 和邻近实现。
- [x] 确认 `implementation_authority=granted`，但按团队契约在方案落盘后停下，等待 @dev-manager 范围核验。
- [x] 定义“每 session 连续段准确计时、跨 session 重叠累加、身份和活跃天数仍去重”的验收口径。
- [x] 写入 proposal、design、board spec delta、Proposed ADR 与逐条自动化/真实运行验收清单。
- [x] @dev-manager 核验范围、消费者清单、ADR 取代方式和验证证据要求。

## 服务端实现

- [x] 调整 `server/routes/board.py::metrics`：每个 session 的有效连续段直接进入上海日分桶，不再做身份级区间并集。
- [x] 删除不再使用的 `_merge_intervals` 和 `intervals_by_identity`，保留 `_session_active_intervals` 的断档、迟到终态与最后确认心跳规则。
- [x] 保持质量 `avg_sec`、最终身份卡片、缓存、Agents 筛选/比较和 API 字段结构兼容。
- [x] 确认没有任何单身份单日 `86_400` 截断、百分比或墙钟上限假设。

## 测试

- [x] 把重叠 session 回归改为逐 session 累加，并覆盖 `/api/state`、`agent_overview`、
      `totals.today_active`、`/api/agents` 全部时长区块和 `/api/agent/{key}`。
- [x] 把“单日上限”回归改为 12 个重叠 session 精确超过 24 小时，同时锁定
      `active_agents=1`、`window_active_days=1`。
- [x] 覆盖跨上海午夜的重叠 session 逐日累加、同名不同身份隔离和质量平均时长不变。
- [x] 新增 pending × 并行 session 组合回归：A 的未 flush `00:02` 心跳期间穿插 B 的即时
      `done` 状态写入，再以 A 的迟到终态触发旧行末点固化；逐项断言 A pending 不丢失、不回退、
      离线区间不回填，并断言 A 120 秒 + B 180 秒 = 身份 300 秒。
- [x] 新增旧 pending/乱序心跳 × 并行 session 组合回归：A 的 pending 依次输入
      `00:02`、`00:01:30`、`00:03` 后只保留 `00:03`，flush 后再输入 `00:02:30` 也不得回退 SQLite、增加事件行或
      产生额外连续段；与 B 的 180 秒重叠区间累加后断言身份 360 秒且 `active_agents=1`。
- [x] 保留并运行纯心跳、pending flush、状态变化固化末点、长断档恢复、迟到终态和未来窗口回归。
- [x] 补前端累计小时格式化测试，确认大于 24 小时不截断；组件继续直接呈现服务端秒数。

## 事实源

- [x] 实现验证通过后把 `spec-delta/board/spec.md` 合并进 `openspec/specs/board/spec.md`。
- [x] 接受 ADR-0025、将 ADR-0013 标为 Superseded，并同步 `docs/adr/README.md`。
- [x] 同步根 `AGENTS.md`、`server/AGENTS.md`、`docs/architecture/module-map.md`、
      `PROTOCOL.md` 和 `DEPLOY.md`，删除身份并集与 86,400 秒上限陈述。
- [x] 复核 QUICKSTART/USAGE/线框无需变更；实现未改变其现有事实，未做无关编辑。

## 验证与符合度反思

- [x] `python -m py_compile server/*.py server/routes/*.py`。
- [x] `python -m coverage run -m pytest` 与
      `python -m coverage report --include='server/**/*.py'`：整体 96%，`board.py` / `ingest.py` 均 96%。
- [x] `npm --prefix frontend run test:unit`。
- [x] `npm --prefix frontend run build`。
- [x] `wc -l server/app.py` 为 210（≤220），server 模块行数没有失控。
- [x] 按 design 的四条真实运行验收语句检查 `/`、`/agents?w=today` 和 `/agent/:key`，
      覆盖 4 小时重叠累加与单日大于 24 小时。
- [x] 对照原始目标、proposal、design 和 spec delta 做实现后反思；记录测试数量、覆盖率、
      真实运行证据、未验证项和剩余风险。
- [x] 验证通过后归档 change，不把未实现行为提前写入当前事实规格。
