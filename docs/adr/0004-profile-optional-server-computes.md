# ADR-0004 profile 由 shim 可选上报;服务端存最新并计算派生指标

- 状态:Accepted
## 背景
希望治理详情丰富,但又不想引入"重注册"流程;质量/复用应可信(来自事件而非自报)。
## 决策
- profile(cf/skills/mcp/integrations/about/tips/models/config/instructions/memory)是**事件可选字段**;
  服务端把每个身份的**最新 profile**存 `profiles` 表,详情页从中合并。
- 质量(runs/success/error/avg_sec/auto_rate)、复用(跨人技能重叠)、leverage(资产数/本周新增技能)
  由服务端**从事件历史计算**,不由 shim 自报。
- `instructions`/`memory` 敏感,默认不报(opt-in)。
## 后果
- ✅ 无需注册端点;详情可有可无不拖慢 2s 轮询。
- 约束:派生指标必须服务端算;敏感字段保持 opt-in。
