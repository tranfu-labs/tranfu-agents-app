# 架构决策记录(ADR)

记录重要技术/架构选择的背景、决策与后果,避免后续(尤其 AI)无意中破坏隐含约束。
状态:Accepted(已采纳)/ Proposed(提议中)/ Superseded(被取代)。

| # | 决策 | 状态 |
|---|---|---|
| 0001 | 单容器 + SQLite,无外部依赖 | Accepted |
| 0002 | 不追踪 token/成本;写凭证仅 TF_KEY / X-TF-Key | Accepted |
| 0003 | 心跳去重:仅状态或步骤变化才落新行 | Accepted |
| 0004 | profile 由 shim 可选上报;服务端存最新 + 计算 leverage/quality | Accepted |
| 0005 | shim 自动探测 profile(三路径),仅 role/about/tips 手填 | Accepted |
| 0006 | 看板按身份(operator + agent‖runtime)合并卡片 | Accepted |
| 0007 | install.sh 与 shim 从看板域名分发(支持私有库) | Accepted |
| 0008 | 服务端默认端口 8788 | Accepted |
| 0009 | Claude Code 钩子用 stdin 分发器(tf_hook),不依赖环境变量取上下文 | Accepted |
