# ADR-0006 看板按身份合并卡片

- 状态:Accepted
## 背景
同一 agent 多次运行/换 session 会产生多个 session 行,曾导致看板对"同一个 agent"显示多张卡。
## 决策
`/api/state` 生成卡片后,**按身份 `(operator, agent 或 runtime)` 合并,只保留最近活跃的一张**。
## 后果
- ✅ 一个 agent = 一张卡,随运行刷新。
- ⚠️ 仍无法合并"漏报 `--agent`"(退化成 runtime 名)或"换了 operator/runtime"的情况——这靠使用规范(同一 agent 永远用同一套 operator/runtime/agent)。
