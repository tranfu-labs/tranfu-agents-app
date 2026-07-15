# ADR-0002 核心 Agent 遥测不追踪 token/成本；写凭证仅 TF_KEY

- 状态:Accepted
## 背景
核心 Agent 遥测用于回答“谁在干什么”，不是计费系统；把 token/成本混入 Agent 事件、身份或会话模型会带来隐私与误导。仓库另有一个可选 Token Usage 模块，只读展示既有分发平台的 KEY 用量，该模块不属于 Agent 遥测采集链路。
## 决策
- Agent 上报协议、shim、事件/身份/会话数据库与核心 Pods、Agents、SKILLS UI **不包含 token 或费用字段**。
- 可选 `/token-usage` 仅在管理员配置外部分发平台只读凭证后镜像其已有数据；不得写回 Agent 遥测模型、不得要求 shim 上报 token/prompt/代码/输出，也不得把该模块扩成项目计费系统。
- Agent 遥测唯一的写入凭证是 `TF_KEY`，通过请求头 `X-TF-Key` 校验；Token Usage 的外部读取凭证不是写凭证，只能保留在服务端。
## 后果
- ✅ 协议简单、隐私友好。
- ✅ 外部分发平台用量与 Agent 协作可观测保持隔离。
- 约束：禁止把成本/计费概念带回 Agent 遥测模型或上报链路；可选只读模块不得改变这一边界。
