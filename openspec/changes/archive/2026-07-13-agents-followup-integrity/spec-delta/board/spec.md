# spec-delta:board（agents-followup-integrity）

## MODIFIED Requirements

### Requirement: Agents summary facts and URL state

Agents 在时间窗变化卡片之后 MUST 保留 Agent 总数、运行中、今日/本周活跃、运行质量和待处理 Agent 等原有摘要事实。排行榜 Runtime/操作员视角 MUST 通过 `rank=runtime|operator` 保持在 URL，缺省为 `runtime`，刷新或复制链接不得丢失；该参数不得写入浏览器存储。

### Requirement: Agents custom window input

当 `w=custom` 时，Agents MUST 分别保留已填写的 `wstart` 与 `wend`，不得因另一端暂空而丢失已有值。Unix instant 转服务端统计日 MUST 使用 `Asia/Shanghai` 语义；自定义窗口聚合必须与服务端 90 天日序列按服务日对齐。

#### Scenario: Custom window keeps partial input

- **WHEN** 用户先填写 custom 开始时间但尚未填写结束时间
- **THEN** URL 至少保留 `w=custom&wstart=...`
- **AND** 随后填写结束时间时，开始时间仍保留并形成完整 custom 窗口

#### Scenario: Rank view survives refresh

- **WHEN** 用户在 Agents 顶部切换到操作员排行
- **THEN** URL 包含 `rank=operator`
- **AND** 刷新或复制该 URL 后仍显示操作员排行
