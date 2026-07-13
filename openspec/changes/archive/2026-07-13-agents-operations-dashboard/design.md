# 设计：agents-operations-dashboard

## 方案概览

服务端继续以 `/api/state` 为 Agents 的唯一数据源。`_snapshot` 先完成现有事件、profile、Shim 和质量聚合，再以最终身份卡片计算 `agent_overview`，由 SSE 与 adaptive polling 一起下发。这样 TopBar、Pods、Agents、AgentDetail 仍共享同一份 state，不会出现第二套刷新节奏。

## `agent_overview` 契约

顶层字段为可选对象，旧客户端忽略即可：

```json
{
  "today": "2026-07-13",
  "days": ["2026-04-15", "...", "2026-07-13"],
  "summary": {
    "agents": 2,
    "live": 1,
    "operators": 2,
    "today_active": 3600,
    "week_active": 7200,
    "runs": 10,
    "success": 8,
    "errors": 2,
    "blocked": 1,
    "success_rate": 0.8,
    "outdated_shim": 1,
    "unknown_shim": 0
  },
  "daily": [{"day": "2026-07-13", "active_seconds": 3600, "active_agents": 1}],
  "runtime": [{"runtime": "codex", "agents": 1, "live": 1, "today_active": 3600, "week_active": 3600, "runs": 5, "success": 4, "errors": 1, "blocked": 0, "success_rate": 0.8}],
  "operator": [{"operator": "alice", "agents": 1, "live": 1, "today_active": 3600, "week_active": 3600, "runs": 5, "success": 4, "errors": 1, "blocked": 0, "success_rate": 0.8}]
}
```

`days` 与 `daily` 固定覆盖服务端 `WINDOW_DAYS`（当前 90 天），日期使用默认 `Asia/Shanghai` 统计日。`active_seconds` 来自现有 per-identity 活跃时长；`runs/success/errors/blocked` 来自现有 quality 聚合。排行按当前 Agent 数、活跃时长、成功率提供确定性排序，前端只负责展示和交互。

## 前端结构

- `frontend/src/lib/agentsDashboard.ts`：纯函数层。负责 Agents URL 查询的规范化、过滤/排序、线索分类、成功率、待处理去重计数和旧 state fallback。
- `frontend/src/components/agents/AgentActivityChart.tsx`：90 天活跃 Agent/活跃时长柱状趋势，长轴只在图表内部横向滚动，默认显示最新日期。
- `frontend/src/components/agents/AgentRankPanel.tsx`：Runtime/操作员分段视角和事实排行；操作员行可把 `op` 写入 Agents URL，Runtime 行可把 `rt` 写入 URL。
- `frontend/src/views/Agents.tsx`：控制条、摘要、问题线索、主分析区、Agent 卡片和空态编排。Agent 卡片整卡为键盘可达链接，进入既有 `/agent/:key`。
- `frontend/src/lib/types.ts`、`frontend/src/lib/i18n.ts`、`frontend/src/styles.css`：契约、双语文案和响应式样式。

筛选参数为 `q`、`status`、`signal`、`rt`、`op`、`sort`；变化使用 `replace`，详情跳转使用既有 `push`。不保存任何筛选状态到浏览器存储。

## 问题线索口径

问题线索是事实提示，不是评分标签：

- 异常/阻塞：当前卡片状态为 `error` 或 `blocked`，或质量中存在 error/blocked。
- Shim 不一致：`outdated` 与 `unknown` 分开展示，均可筛到对应 Agent。
- 长期未活跃：非 live Agent 最近 14 天 `active_days` 全为 0。
- 成功率偏低：至少 3 次 runs 且 `success / runs < 0.8`。

同一 Agent 可出现在多个线索卡片；总览“待处理 Agent”按身份 key 去重。

## 测试设计

后端在 `tests/test_board.py` 或新增 Agents 专项测试中覆盖：固定日期下 90 天序列、时长汇总、Runtime/操作员聚合、质量分母为 0、身份合并后不重复计数、Shim 计数和旧 state 字段不变。

前端在 `frontend/src/lib/agentsDashboard.test.ts` 覆盖：查询规范化、筛选/排序、成功率边界、14 天静默边界、unknown/outdated Shim、多个线索下的去重和缺少 `agent_overview` 时的 fallback。展示层（大块 JSX/CSS/ SVG）不写 DOM 单测，使用构建与浏览器走查验证。

## 风险与取舍

- 复用 `/api/state` 会让 Agents 和 Pods 一起承担新增聚合，但避免了重复请求和状态不一致；聚合只遍历已经生成的身份卡片，边界清晰。
- 90 天趋势在手机上不能撑出页面根横滚，因此只允许图表盒子横向滚动，并默认滚到最新日期。
- 低成功率阈值是页面治理提示而非协议字段，集中在纯函数常量和测试中，未来可以独立调整。
