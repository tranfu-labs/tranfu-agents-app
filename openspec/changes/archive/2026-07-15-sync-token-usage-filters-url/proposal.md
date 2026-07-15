# 提案：sync-token-usage-filters-url

## 背景

`/token-usage` 的时间范围和图表粒度由路由组件的 React state 保存，KEY 类型、模型、风险状态、Top N、搜索、隐藏零消耗和表格排序则分散在页面组件的本地 state。所有筛选都没有写入 URL，导致刷新、复制链接和浏览器历史导航后无法恢复当前观察范围。

用户确认本页应参考 `/skills` 的 URL 状态模型：全部可见筛选与排序进入 query string，默认值保持简洁，变化使用 replace；详情抽屉、选中 KEY 和忽略风险仍是临时页面状态。

## 提案

- 为 `/token-usage` 增加统一的 query-state 模块，复用 `/skills` 已采用的 `nuqs/useQueryStates` 与 `history: 'replace'`。
- 用 `w/wstart/wend/g/kind/model/risk/topn/q/hz/sort/dir` 表达时间范围、自定义起止、图表粒度、类型、模型、风险、Top N、搜索、隐藏零消耗和排序。
- 页面无 query 时保持现有默认语义，默认值无需冗余写入 URL；刷新、复制链接和浏览器历史导航后必须恢复筛选。
- 自定义时间逐项输入时保留已有 query；两端有效后驱动 `/api/token-usage` 请求。
- 增加 URL 解析/归一化/请求映射单元测试，并补齐 `/token-usage` 的 OpenSpec 与字符线框事实源。

## 影响

- 影响 `frontend/src/App.tsx`、`frontend/src/views/TokenUsage.tsx`、`frontend/src/lib/tokenUsageRange.ts`，新增 token usage query-state 与前端单元测试。
- 更新 `openspec/specs/board/spec.md`、`docs/wireframes/pages/token-usage.md`、`docs/wireframes/flow.md`、`docs/architecture/module-map.md` 与根 `AGENTS.md` 中的前端路由/URL 状态描述。
- 不改变 `/api/token-usage` 契约、上游分发平台请求、服务端缓存、Token Usage 统计口径、数据库、Agent 上报协议或页面视觉布局。
