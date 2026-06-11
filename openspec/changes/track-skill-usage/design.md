# 设计:track-skill-usage

## 已确认的决策(2026-06-11 与需求方逐项确认)
1. **目标**:团队"哪些 skill 真被用起来" + 运营"维护/下架决策";"效果是否符合预期"
   后续单独立项,本期只保留 session_id 作关联钩子。
2. **口径**:一个会话用过算一次,同会话重复触发不累加。
3. **runtime**:全部尽力而为,Claude Code 先打通。
4. **存储**:专用表,一行 = 会话×skill,唯一键幂等,永久保留。
   理由:上报链路是 at-least-once(spool 重试),任何"计数器 +1"都会被重试重复加;
   events 表 90 天清理与"运营要看长期趋势"冲突;口径既然按会话去重,
   "去重后的最细粒度"恰好就是"一行 = 会话×skill",原始记录与计数源合一。
5. **隐私**:默认上报,`TF_REPORT_SKILLS=0` 关闭。比 `TF_REPORT_MEMORY` 的 opt-in 宽松是有意的:
   skill 名与已默认上报的工具名/已装 skill 清单同敏感度,不属于内容捕获。

## 数据流
```
Claude Code 触发 skill
→ PreToolUse 钩子 stdin JSON(tool_name="Skill", tool_input 含 skill 名, session_id)
→ tf_hook.py:识别并提取 skill 名,tf_report 调用参数追加 --skill <名>
→ tf_report.py:事件 JSON 附加可选顶层字段 skill(复用本来就要发的事件,不新增请求)
→ POST /v1/events:事件带 skill 且有 session_id 时,幂等写 skill_uses
→ (show-skill-usage)读时 GROUP BY 出排行/趋势/人数
```

## 改动文件与职责
- `shims/tf_hook.py` —— `resolve()` 识别 skill 调用:`tool_name` 为 `Skill`(大小写宽容)时
  从 `tool_input` 提取 skill 名(键名宽容:`skill`/`name`/`skill_name`;取不到则不附加,宁缺毋错)。
  受 `TF_REPORT_SKILLS=0` 短路。沿用"绝不抛错"约定。
- `shims/tf_report.py` —— 新增可选 `--skill` 参数,写入事件 JSON 顶层可选字段 `skill`。
  spool 重试路径不动(幂等由服务端唯一键保证)。
- `server/app.py` —— 建表 `skill_uses`;ingest 在**心跳去重判断之前**处理 skill 字段
  (否则连续两次相同 status/step 的事件走 heartbeat 短路,第二次的 skill 会被吞掉);
  `INSERT OR IGNORE`;skill 名长度上限对齐 ADR-0014 风格(超长截断)。
- `PROTOCOL.md` —— 事件字段表 + `skill`(可选);隐私小节 + `TF_REPORT_SKILLS`。
- `docs/adr/0015-skill-usage-per-session.md` —— 固化四项决策(见上)。
- `openspec/specs/ingest/spec.md` —— 实现上线后,把本 change 的 spec delta 合入并归档。

## 表形状(描述,非 DDL)
`skill_uses`:`session_id`、`skill`、`operator`、`runtime`、`day`(UTC,首次见到该会话×skill 的日期)。
唯一键 `(session_id, skill)`。无清理任务(永久保留;量级 ≈ 人数 × 日会话数 × 每会话 skill 数,
一个团队一年数万行,SQLite 无压力)。

## 各 runtime 采集可行性(尽力而为)
- **Claude Code**:✅ 本期打通。skill 触发经 `PreToolUse` 暴露为 `Skill` 工具调用;
  实现时以真实钩子负载验证 `tool_input` 键名,并用单测锁定。
- **Codex**:实现时调研其 hooks 是否暴露 skill 调用(tasks 调研项);能拿则同链路,
  拿不到则该 runtime 无数据,不算失败。
  调研结论(2026-06-11):OpenAI 官方 Codex Hooks 文档确认 command hook 通过 stdin 收到 JSON,
  `PreToolUse` 包含 `tool_name` 与 `tool_input`,但公开文档列出的当前支持范围是 Bash、`apply_patch`
  和 MCP 工具,并注明 WebSearch 等非 shell/非 MCP 工具不一定被拦截;未找到稳定公开的 Codex Skill
  hook 负载样本。因此实现保持通用解析(`tool_name=Skill` 时可上报),但不把 Codex Skill 统计列为本期已接通。
- **Hermes**:`pre_tool_call` 仅有工具名,skill 触发机制待验证,默认无数据。
- **OpenClaw**:尚无钩子接入,本期无数据;协议字段通用,接入后即生效。

## 已知口径细节(默认决策,需求方可推翻)
- **子代理会话单独计数**:子代理有独立 session_id,skill 在子代理里被用会单独 +1,
  会拉高"会派生子代理的 skill"的数字。v1 接受;events 已存 parent 链,
  未来如需按"顶层工作单元"归并可在读侧做,不改采集。
- 事件**无 session_id 时不落库**(无法去重,且口径以会话为单位)。

## 分发线:上线后数据何时开始产生(易漏)
shim 是队友机器 `~/.tranfu` 里的**本地副本**,服务端部署完不等于采集生效:
- 服务端先上线(向后兼容:旧 shim 不发 skill 字段,服务端行为与现状完全一致);
- 队友重跑 install.sh(从 `$SERVER/shims` 拉新版)后,其会话才开始产生数据;
- 兼容性两个方向都要成立:旧 shim + 新服务端 = 无 skill 字段、无影响;
  新 shim + 旧服务端 = 多一个未知字段、必须被忽略不报错。
- `UPDATE.md` 注明"此版本需更新本地 shim 才开始统计",并预期数据是**逐人渐进**出现的。

## 风险与对策
- 钩子负载键名变化 → 提取逻辑键名宽容 + 单测锁定当前格式;取不到名宁可不报。
- 心跳去重吞掉 skill 字段 → ingest 处理顺序前置,spec delta 写成可验证行为强制锁定。
- 上报放大 → 无:skill 字段附加在本来就会发的 PreToolUse 事件上,零新增请求。
- 上线后查不到数据 → 大概率是队友 shim 未更新(见"分发线"),排查顺序写进 UPDATE.md。
