# tasks:fix-shim-version-reporting

部署顺序:**先服务端,再客户端**(避免新客户端上报顶层 `shim_version` 被旧服务端忽略时,看板继续显示 unknown)。

## 服务端

- [ ] 1. `server/app.py`:新增 `agent_shim_versions` 表(`CREATE TABLE IF NOT EXISTS`)与索引。
- [ ] 2. `server/app.py`:`/v1/events` 处理路径中,顶层 `shim_version` 非空 → UPSERT 该表;为兼容旧客户端,
       若顶层无、但 profile 有 → 同样兜底写入。
- [ ] 3. `server/app.py`:`PROFILE_KEYS` 移除 `shim_version`(profile 不再承载它)。
- [ ] 4. `server/app.py`:`_snapshot()` / `card()` 改为从 `agent_shim_versions` 读取并合并到 card。
- [ ] 5. `server/app.py`:`admin-data-cleanup` 路径(`_delete_profile_rows` 周边)把 `agent_shim_versions`
       一并清理。
- [ ] 6. `tests/test_protocol.py` 或新 `tests/test_shim_sticky.py`:
       发"带 → 不带 → 带新值"三连事件,断言 `/api/state` 该 agent 的 `shim_version` 行为符合 sticky。

## 客户端

- [ ] 7. `shims/tf_profile.py`:抽出 `quick_shim_version()`(进程内缓存),`detect_shim_version()` 复用。
- [ ] 8. `shims/tf_report.py`:`argparse` 新增 `--shim-version`;自动兜底:每次构造 payload 时,
       若顶层无 `shim_version` 且没传 `--profile`,主动调 `quick_shim_version()` 注入。
- [ ] 9. `shims/openclaw/reporter.mjs`:启动时同步读 `~/.tranfu/manifest.json` 缓存 `shimVersion`;
       `SIGUSR1` 重读;`postJson` 注入顶层字段。
- [ ] 10. `tests/test_profile.py`:补 `quick_shim_version()` 缓存命中(同一进程多次调用只读一次)。
- [ ] 11. `tests/test_protocol.py` 或新文件:补 case —— `tf_report.py` 不带 `--profile` 也不带 `--shim-version`
        时,只要 `manifest.json` 可读,POST 出去的 payload 顶层必须含 `shim_version`。
- [ ] 12. `tests/test_openclaw_skill_reporter.mjs`:补 case —— payload 含 `shim_version` 顶层字段。

## 前端

- [ ] 14. `frontend/src/lib/utils.ts`:新增 `shimState(agent, latest)` 三态;保留 `isOldShim` 包装。
- [ ] 15. `frontend/src/lib/i18n.ts`:加 `shimUnknown`(中 + 英)。
- [ ] 16. `frontend/src/components/Common.tsx`:卡片按三态渲染。
- [ ] 17. `frontend/src/views/AgentDetail.tsx`:详情按三态渲染。
- [ ] 18. `frontend/src/lib/demo.ts`:加一个 `shim_version` 缺失的演示 agent。

## AI 验证流程(实施完跑一遍)

- [ ] V1. 启动服务端,本地 `curl -XPOST /v1/events` 发"带 `shim_version=A`"→ 再发"不带" → 再发"带 B";
       `curl /api/state` 看该 agent card 的 `shim_version` 依次是 A、A(sticky)、B。
- [ ] V2. 前端 `npm run dev` → 切到 demo 模式,核对三态颜色与文案;切到真实数据,看本机美羊羊从灰转绿。
- [ ] V3. OpenClaw 触发一次 session,`/api/state` 看 OpenClaw agent card 的 `shim_version` 非空。
- [ ] V4. Codex / Claude Code 触发一次 `PreToolUse`,核对单次心跳即可让 `shim_version` 刷新。

## 文档

- [ ] 19. `UPDATE.md` §6 / §7:说明协议升级 —— 旧客户端"未上报"时看板呈现 unknown 灰态,而非误标"旧 shim"。
- [ ] 20. `PROTOCOL.md`(若存在):`shim_version` 从 profile 字段升为事件顶层可选字段;旧路径兼容保留。
