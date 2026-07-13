# spec delta: board（Agents 运营看板）

> 合入后并入 `openspec/specs/board/spec.md`。

## 接口（新增字段）

- `GET /api/state` 与 `/api/state/stream` 顶层可返回 `agent_overview`。对象包含 `today`、90 天 `days[]`、`summary`、`daily[]`、`runtime[]`、`operator[]`；日期为服务端 `Asia/Shanghai` 统计日，时长为秒。
- `agent_overview` 的聚合以最终身份卡片为单位，遵守 `operator + agent||runtime` 合并规则；`summary` 的 runs/success/errors/blocked 沿用 Agent card 的 quality 口径。
- 现有 `sessions`、`totals`、`feed`、`leverage`、`skills`、`shim` 字段保持兼容，新增字段缺失时前端必须可由现有 sessions 降级展示。

## Agents 页面规则（新增）

- `/agents` 必须是证据型运营页面，信息流为：控制条 → 摘要 → 活跃趋势与 Runtime/操作员排行 → 问题线索 → Agent 明细。
- 控制条支持 `q`、`status`、`signal`、`rt`、`op`、`sort` URL 参数；筛选变化使用 replace，不得使用浏览器存储；详情仍跳转 `/agent/:key`。
- 摘要至少展示 Agent 总数、运行中数量、今日活跃、成功率/运行质量和待处理 Agent；待处理总数按身份去重。
- 趋势展示服务端 90 天日级 active agents/active seconds，长时间轴只允许在图表容器内横向滚动，手机页面根不得横向滚动。
- Runtime/操作员排行必须使用服务端 `agent_overview`，展示 Agent 数、活跃时长和质量事实；操作员排行支持将操作员筛选写回当前 Agents URL。
- 问题线索至少包含当前异常/阻塞、Shim outdated/unknown、最近 14 天无活跃、至少 3 runs 且成功率低于 80%；线索为事实提示，不作为评分或成本指标。
- Agent 明细由宽表改为可扫描卡片/摘要行，至少保留身份、操作员、Runtime、当前状态、任务/步骤、活跃时长、Skill、MCP、质量、Shim 和 7 日活跃趋势；整卡键盘可达并进入 `/agent/:key`。
- 页面必须支持中英文、system/light/dark 主题和 `>1080px` 桌面、`601–1080px` 平板、`≤600px` 手机布局；新增 Agents 前端状态不得持久化。

## 可验证行为

- 固定数据库数据后，`/api/state` 的 `agent_overview.daily` 长度为 90，日期顺序递增，最终一天等于服务端 `today`；身份跨多个 session 时只在 summary、runtime、operator 和 daily 中计为一个 Agent。
- 同一身份拥有 error、blocked、outdated shim 或低成功率时，前端对应线索可见；同一身份出现在多个线索时待处理摘要只计数一次。
- `/agents?rt=codex&status=attention&signal=quality` 只显示满足筛选条件的卡片；刷新/复制链接保持筛选；清空筛选回到全量列表。
- Agent 卡片点击或键盘 Enter/Space 进入对应 `/agent/:key`；无 Agent 时显示空态，不渲染空表头。
