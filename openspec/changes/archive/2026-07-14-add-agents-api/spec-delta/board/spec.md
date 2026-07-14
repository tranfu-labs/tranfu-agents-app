# board spec delta：独立 Agents 统计接口

## 接口增量

- `GET /api/agents?w={today|this_week|last_week|7d|14d|30d|90d|custom}[&wstart=&wend=&q=&status=&signal=&sort=]` → Agents 指定时间窗统计 payload，至少包含 `today/window/summary/comparison/daily/ranking/agents/signals/shim`。
- `w=custom` 的 `wstart/wend` 为 Unix 秒，按 `Asia/Shanghai` 映射统计日；两端必填、起日不得晚于止日、含首尾最多 90 天，且起点不得早于当前 90 天可用序列，否则返回 `400`。终点可延伸到未来，未来日期按当前时点返回 0。
- `ranking[]` 以 `operator + agent||runtime` 身份为统计基数，返回稳定 `key/rank/operator/agent/runtime/active_seconds/active_days/status/last_seen`；`agents[]` 同样显式返回 `key/operator/agent/runtime`。零时长不进入排行，排序固定为 `active_seconds DESC, key ASC`。
- `agents[]`、`daily[]`、`summary`、`comparison` 和 `signals` 必须使用同一组经 `q/status/signal` 过滤的身份卡片与同一窗口，不得混用全量集合或浏览器二次统计。
- `q` 只匹配 Agent 名、任务、当前步骤和 model；`status` 支持 `all/live/attention/idle/done`；`signal` 支持 `error/shim/quiet/quality`；`sort` 支持 `recent/window_time/window_days/success/errors/name`，非法值返回 `400`。
- 时长单位固定为秒，日期为服务端 `Asia/Shanghai` 统计日；累计质量字段必须继续明确为累计口径。

## 前端增量

- `/agents` 必须独立请求 `/api/agents`，不得等待全局 `/api/state` 首包后才挂载；页面首次加载和 query 变化期间显示与当前信息架构对应的 skeleton，失败显示可重试错误态。
- `/agents` 的 KPI、问题线索、排行、趋势和明细必须消费同一 `/api/agents` payload；排行榜不得再只存在于浏览器内计算结果。
- `/agents` 底部 Agent 明细表必须显示操作员列，数据来自 `agents[].operator`；运行终端仍不得作为明细列，操作员和运行终端仍不得作为筛选条件，搜索仍不得匹配这两个字段。
- `/api/state.agent_overview` 与 `/api/state/stream` 保持兼容，供其它现有消费者继续使用。

## 可验证行为增量

- `GET /api/agents?w=7d` → `window.days` 恰为最近 7 个上海统计日，`ranking[0]` 是该窗口正时长最大的 Agent。
- `GET /api/agents?w=custom&wstart=<上海日A内instant>&wend=<上海日B内instant>` → 起止日分别为 A/B；跨越 91 个统计日或起点早于 90 天保留序列时返回 `400`；未来 B 的日期槽按当前时点为 0。
- 同一 Agent identity 跨多个 session → `ranking/agents/summary` 只计一个 Agent；同名不同 identity → 分开返回且时长不合并。
- 人为延迟 `/api/agents` 后刷新 `/agents` → 页面立即显示 skeleton，不被 `/api/state` 是否返回所阻塞。
