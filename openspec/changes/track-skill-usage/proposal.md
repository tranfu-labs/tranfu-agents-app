# 变更提案:track-skill-usage(skill 使用计数——采集与落库)

- 状态:Proposed(待实现)
- 关联:ADR-0003(心跳去重)、ADR-0005(shim 自动探测)、ADR-0009(钩子 stdin)、ADR-0014(存储上限)、specs/ingest、PROTOCOL.md
- 后续 change:show-skill-usage(聚合 API 与看板排行,依赖本变更先落库积累数据)

## 背景 / 问题
系统对 skill 的感知目前是**静态**的:`tf_profile.py` 上报"装了哪些 skill",服务端记首次出现
(`skills_seen`)与跨人重叠(`reuse`)。回答不了两个问题:
- 团队:沉淀下来的 skill 有没有**真被用起来**(而不只是装了)?
- 运营:哪些 skill 值得维护、哪些该下架?

后续还希望评估"skill 效果是否符合预期"——本期**不做**,只留数据钩子(保留 session_id 供未来关联)。

## 目标
- 记录"某会话用过某 skill"。口径:**一个会话内同一 skill 只算一次**(需求方确认)。
- 全 runtime **尽力而为**:协议字段通用;Claude Code 本期打通,其余 runtime 能探则探、
  探不到上报为空,不报错(需求方确认)。
- **默认上报**,提供 `TF_REPORT_SKILLS=0` 退出开关(需求方确认;与"已装 skill 清单默认上报"同敏感度)。
- 落库**幂等**:同会话重复触发、spool 重试重复投递,均不重复计数。

## 非目标
- 不做聚合 API 与看板展示(归 show-skill-usage)。
- 不做 skill 效果/成功率评估(未来单独立项)。
- 只报 skill **名**,不报参数与内容——skill 名是元数据,与默认上报的工具名同级,
  不触碰"不得默认上报 prompt/代码/输出/记忆"的硬约束。

## 方案概述(详见 design.md)
钩子 `PreToolUse` 已携带工具名与 session_id;Claude Code 的 skill 触发就是一次 `Skill` 工具调用,
skill 名在 `tool_input` 里。链路:`tf_hook.py` 解析出 skill 名 → `tf_report.py` 在**既有事件**上
附加可选字段 `skill` → 服务端 ingest 时幂等写入新表 `skill_uses`(唯一键 session_id+skill),
永久保留、不受 events 90 天清理影响。**零新增请求、零新事件类型。**

## 影响
- specs/ingest:新增 `skill` 字段与 `skill_uses` 落库规则(见本 change 的 spec delta)。
- PROTOCOL.md:事件可选字段 +1(`skill`);隐私小节注明默认上报与 `TF_REPORT_SKILLS` 开关。
- 新增 ADR-0015:skill 使用计数的口径(按会话去重)、幂等存储、永久保留、默认上报四项决策。
