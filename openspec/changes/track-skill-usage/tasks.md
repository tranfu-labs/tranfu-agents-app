# tasks:track-skill-usage

- [x] 1. `tf_hook.py`:`resolve()` 提取 skill 名(含 `TF_REPORT_SKILLS=0` 短路)。
      单测(`tests/test_hook.py`):Skill 调用 → argv 带 `--skill <名>`;普通工具调用 → 不带;
      `tool_input` 缺名 → 不带;开关=0 → 不带;以真实 Claude Code 钩子负载样本锁定键名。
- [x] 2. `tf_report.py`:`--skill` → 事件 JSON 可选顶层字段 `skill`。
      单测(`tests/test_protocol.py` 或就近新增):`--print` 验证 payload 含/不含该字段。
- [x] 3. `server/app.py`:建表 `skill_uses` + ingest 落库(先于心跳短路;`INSERT OR IGNORE`;名称截断)。
      TestClient 测试:同会话同 skill 投递两次 → 1 行;不同会话同 skill → 2 行;
      带 skill 无 session_id → 0 行且 200;连续相同 status/step 走 heartbeat 路径 → skill 仍落库。
- [x] 4. 文档:`PROTOCOL.md` 字段表 + 隐私小节;`QUICKSTART.md`/`USAGE.md` 如列环境变量则补 `TF_REPORT_SKILLS`;
      `UPDATE.md` 注明"需重跑 install.sh 更新本地 shim 才开始统计"及查不到数据时的排查顺序。
- [x] 4b. 兼容性测试:旧 shim 事件(无 skill 字段)打新服务端 → 行为与现状一致;
      新 shim 事件(带 skill 字段)打未建表的旧服务端 → 200 不报错(未知字段被忽略)。
- [x] 5. `docs/adr/0015-skill-usage-per-session.md` 成文(口径/幂等/永久保留/默认上报,
      并写明"skill 名属元数据,不触碰内容捕获硬约束"的边界)。
- [ ] 6. 端到端手验:真实 Claude Code 会话触发任一 skill,服务端 sqlite 查 `skill_uses`
      出现且仅一行;同会话再次触发同一 skill → 行数不变;`TF_REPORT_SKILLS=0` 重试 → 无新行。
      本地已用 hook payload + `/v1/events` 造数验证;真实 Claude Code 会话需在可触发 Skill 的环境中手验。
- [x] 7. (调研项)Codex 钩子负载是否暴露 skill 调用,结论写回 design.md;能做则顺手接通。
- [ ] 8. 上线后:spec delta 合入 `openspec/specs/ingest/spec.md`,归档本 change。
      spec delta 已合入;归档留到上线后执行。
