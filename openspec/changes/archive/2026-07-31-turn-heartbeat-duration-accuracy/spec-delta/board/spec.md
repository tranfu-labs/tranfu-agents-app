# board 规格增量：独立活跃时长切段阈值

## 规则增量

- 活跃时长连续段切分 MUST 使用独立的 `ACTIVE_SEGMENT_GAP_SECONDS=900` 秒，而不是复用 `STALE_SECONDS`。
- `/api/state`、`/api/agents`、`/api/agent/:key`、Agents overview 和其它复用 metrics 的读路径 MUST 使用同一独立切段口径；该口径在查询时重算，历史事件无需迁移。
- `STALE_SECONDS=180` 的卡片在线/掉线判定 MUST 保持不变；本规则不得把超过 180 秒未收到心跳的 running 卡继续展示为 live。

## 可验证行为增量

- 相邻 active 事件间隔 `<=900` 秒时属于同一连续段；间隔 `>900` 秒时旧段停在最后确认心跳，后续事件从自身 `recv` 开始新段。
- 同一历史数据经 `/api/state`、`/api/agents` 与 `/api/agent/:key` 查询时，三者的今日活跃秒数一致，并可追回原先被 180 秒切断的长静默段。
- active 卡片最后心跳超过 180 秒后，页面状态仍转为 idle；900 秒阈值不得影响该展示断言。
