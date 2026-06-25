# 架构决策记录(ADR)

记录重要技术/架构选择的背景、决策与后果,避免后续(尤其 AI)无意中破坏隐含约束。
状态:Accepted(已采纳)/ Proposed(提议中)/ Superseded(被取代)。

| # | 决策 | 状态 |
|---|---|---|
| 0001 | 单容器 + SQLite,无外部依赖 | Accepted |
| 0002 | 不追踪 token/成本;写凭证仅 TF_KEY / X-TF-Key | Accepted |
| 0003 | 心跳去重:仅状态或步骤变化才落新行(去重键由 0014 修订为含 session_id) | Accepted |
| 0004 | profile 由 shim 可选上报;服务端存最新 + 计算 leverage/quality(合并语义由 0014 改为全量覆盖) | Accepted |
| 0005 | shim 自动探测 profile(三路径),仅 role/about/tips 手填 | Accepted |
| 0006 | 看板按身份(operator + agent‖runtime)合并卡片 | Accepted |
| 0007 | install.sh 与 shim 从看板域名分发(支持私有库) | Accepted |
| 0008 | 服务端默认端口 8788 | Accepted |
| 0009 | 本地 agent 钩子用 stdin 分发器(tf_hook),不依赖环境变量取上下文 | Accepted |
| 0010 | 本地 hooks 配置必须幂等且可回退(Claude Code / Codex) | Accepted |
| 0011 | per-operator 令牌身份(轻量入职注册,不做账号体系) | Accepted |
| 0012 | 读侧鉴权是内容上报的硬前提(服务端强制丢弃敏感字段) | Accepted |
| 0013 | 活跃时长用服务端时间;blocked 计活跃且单列;心跳 60s / stale 180s | Accepted |
| 0014 | 存储与 schema:限流 / 90天保留+WAL / profile 全量覆盖 / session 去重 / parent / 版本号 | Accepted |
| 0015 | Skill 使用按会话去重统计 | Accepted |
| 0016 | Codex skill 使用从会话文件(rollout)补采 | Accepted |
| 0017 | Hermes skill 使用从 `skill_view` 工具调用采集 | Accepted |
| 0018 | OpenClaw skill 采集——装备态 `equipped`(与「使用」分语义) | Proposed |
| 0019 | React 看板构建,同时保持单运行容器 | Accepted |
| 0020 | 后台清理:硬删+回收站+审计(不软删);管理鉴权 TF_ADMIN_KEY 与 TF_KEY 隔离 | Proposed |
| 0021 | 按 operator 删除收口到本人行(session 不再是 operator 路径的删除原子单位;修订 0020) | Proposed |
| 0022 | Hermes 钩子链路常态结构化诊断日志(默认开 / 双文件 5MB rotate / 不与 harden-codex 重复 raw dump) | Proposed |
