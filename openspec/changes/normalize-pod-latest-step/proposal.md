# 变更提案：normalize-pod-latest-step（看板步骤归一）

- 状态：Implemented locally（code-verified，待部署后归档）
- 实现授权：Granted（用户已明确选择“只做第一档”）
- 方案闸门：Passed（主理人已核验验收清单、写路径与 `pod_step` 原始字段隔离后放行）
- 关联：ADR-0003（活动流只含真实事件变化）、ADR-0006（按身份合并卡片）、ADR-0015/0016（Skill 使用与扫描补采）

## 背景 / 问题

Pods 卡片把 `/api/state.sessions[].current_step` 直接显示为 `▸ ${current_step}`。该自由文本字段同时承载：

1. 工具活动：`tool: Bash`、`tool done: Bash`；
2. 生命周期：`turn end`；
3. Skill 统计补采：`skill: ai-opportunity-evaluation`；
4. 其它调用方自由文本。

因此内部事件前缀会直接泄漏到用户界面。尤其 Codex / Claude Code 在 `Stop` / `SessionEnd` 后追加
`status=done, current_step="skill: <name>"` 的 Skill 补采事件，最新一条补采事件会覆盖卡片原本的
最新有效步骤。任务行是独立的 `task` 字段；例如 `接入自检` 是真实任务名，不属于需要清洗的步骤。

## 目标

优化 `/`、`/agents`、`/agent/:key` 和 `/` 活动流的步骤行：

- `tool: Bash` 显示为中文「正在执行命令」、英文「Running a command」；
- `tool done: Bash` 显示为中文「已完成执行命令」、英文「Finished running a command」；
- `turn end` 不作为步骤文案显示，由卡片现有本地化状态表达终态；
- Skill 扫描事件不再成为卡片步骤来源；即使连续补采多个 Skill，也不显示 `skill: ...`；
- `接入自检` 等真实 `task` 原样保留；
- 未识别的自由文本原样显示，不截断、不翻译、不丢失信息；
- 无步骤、被抑制的生命周期步骤或无可回退步骤时，沿用现状显示本地化状态。

## 非目标

- 不增加真实 shell 命令、文件名、搜索词或其它命令详情；
- 不修改 TATP 上报协议、事件表、Skill 表或 shim 上报行为；允许在 board 只读响应中增加
  看板展示用的可选派生字段；
- 不改变任务行、卡片时长、状态枚举、身份合并、掉线判定或 Skill 统计口径；
- 不改 Agent 详情、Agents 列表和活动流 API 返回的原始 `current_step`、事件事实、组件版式与交互；
  这些入口仅复用同一展示函数，活动流不消费卡片 `pod_step` 回退值；
- 不做无关 CSS、组件或服务端聚合重构。

## 提案

1. 在 board 读模型中增加看板展示用的 `sessions[].pod_step?: string | null`：
   - 原始 `current_step`、状态、时间和其它字段仍以当前最新事件为准；
   - 当最新步骤来自 `source ∈ {heartbeat, heartbeat_resume} + status=done +
     current_step="skill: ..."` 的扫描补采时，只为 `pod_step` 回退到同一身份、同一 session
     最近的非扫描事件；
   - 找不到回退事件时 `pod_step=null`，由前端显示状态；
   - 原始 events、`current_step`、feed 与 `skill_uses` 不变。
2. 复用不依赖 React 的步骤展示纯函数，集中完成已知前缀的分类、本地化和安全退化；
   四个入口消费同一函数，前三者按 `pod_step` 字段是否定义选择来源，活动流使用原始事件步骤。
3. 为服务端步骤来源回退和前端文案投影分别补单元测试，并把四个入口的真实页面验收语句写入任务清单。
4. 实现时同步 board 当前事实规格与 `docs/wireframes/pages/board.md`；无路由或流转变化，
   `docs/wireframes/flow.md` 不需修改。

## 影响

- `server/routes/board.py`：为 `/api/state.sessions[]` 增加可选 `pod_step` 看板展示投影；
  保留原始 `current_step`，不改变写侧、表结构或统计。
- `frontend/src/views/Board.tsx`、`AgentDetail.tsx`、`AgentDirectoryTable.tsx`：四个入口共享步骤归一函数；
  Feed 以原始事件步骤为输入且不消费卡片回退值。
- `frontend/src/lib/types.ts`：为 `AgentSession` 增加可选 `pod_step?: string | null`；
  其它消费者继续读取 `current_step`。
- `frontend/src/lib/`：复用 `agentStep.ts` 纯展示规则及单元测试，中英文文案集中可测。
- `tests/test_board.py`：覆盖 `heartbeat` / `heartbeat_resume` 两条 Skill 扫描写路径，
  并验证原始 `current_step`、状态、任务、feed、AgentDetail / Agents 与 Skill 统计不受影响。
- `openspec/specs/board/spec.md`、`docs/wireframes/pages/board.md`：实现并验证后同步当前事实与线框。
