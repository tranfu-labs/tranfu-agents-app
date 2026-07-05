# 任务:reduce-dashboard-load

- [x] 1. `server/routes/board.py`:为 `/api/state` 增加 single-flight / stale-while-revalidate 缓存保护。
      单测覆盖 TTL 内命中、TTL 后重算、并发过期请求只触发一次 `_snapshot`、`/healthz` 仍是 async 轻量 handler。
- [x] 2. `server/routes/board.py`:新增 `/api/state/stream` SSE 端点与 state dirty/coalesced broadcast 机制。
      首包返回完整 state;dirty 后合并推送;空闲 keepalive;慢连接不阻塞全局。
- [x] 3. `server/routes/ingest.py`:新增纯心跳 pending map 与 `TF_HEARTBEAT_BATCH_SECONDS` 配置,默认 15 秒。
      只 batch `last_seen`;`0` 禁用 batch;flush 用一个事务批量更新并标记 state dirty。
- [x] 4. `server/routes/ingest.py`:跳过相同 `shim_version` 的 no-op 写。
      首次/变化即时写;缺失或空白不清空 sticky 值。
- [x] 5. `server/routes/ingest.py`:保证状态/步骤变化、done/error、skill、profile、shim version 变化仍即时落库。
      写入前后正确清理该 session 旧 pending 心跳。
- [x] 6. `server/routes/admin.py`:管理清理 / 恢复会影响 `/api/state` 的数据时,操作完成后标记 state dirty。
      测试删除或恢复后已连接 SSE client 能收到新 state。
- [x] 7. `frontend/src/lib/api.ts`:把 state hook 改为 SSE-first + adaptive polling fallback。
      连接成功消费 SSE;SSE error 后 fallback;fallback 按 live 数和页面可见性调节间隔;避免请求并发叠加。
- [x] 8. 后端测试 / 手验:
      `/api/state` single-flight;`/api/state/stream` 首包;纯心跳 flush 前后 DB 行为;
      真实事件即时写;skill/profile 不被 batch;相同 shim_version 不重复写;admin 清理 / 恢复 dirty 通知;
      `TF_HEARTBEAT_BATCH_SECONDS=0` 兼容旧行为。SSE 首包用本地 `curl -N /api/state/stream` smoke 验证。
- [x] 9. 前端验证:
      `npm --prefix frontend run test:unit`;`npm --prefix frontend run build`;
      本地服务用 `/api/state` 与 `/api/state/stream` smoke 验证状态 payload。in-app Browser 插件连接失败,
      本变更无视觉布局调整,页面级可视 smoke 未执行。
- [x] 10. 服务端验证:
      `python -m py_compile server/*.py server/routes/*.py`;
      `python -m coverage run -m pytest && python -m coverage report --include='server/**/*.py'`;
      用并发 `/api/state` 压测验证 `_snapshot` 重算次数受控且 `/healthz` 响应不被拖慢。
- [x] 11. 文档与事实源准备:
      已准备 `spec-delta/board/spec.md` 与 `spec-delta/ingest/spec.md`,归档阶段再合并回 `openspec/specs/`;
      新增环境变量已同步 `.env.example`、DEPLOY/UPDATE/PROTOCOL/AGENTS 中对应说明。
