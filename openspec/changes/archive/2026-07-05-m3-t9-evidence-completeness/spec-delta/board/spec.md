# spec-delta：board（m3-t9-evidence-completeness）

> 本 delta 聚焦 `/skills/evidence` 记录访问完整性。归档时把下面的 MODIFIED / ADDED 合并回 `openspec/specs/board/spec.md`。

## MODIFIED

### SKILLS evidence 记录完整性

- `/skills/evidence` 对有 raw records 的 kind（`total`、`untracked`、`runtime`、`source`、`top3`、`coverage`、`operators`、`avg_per_session`）不得只停留在 `/api/skills/evidence` 首批默认 `limit=100` 的记录。当前筛选下的全部 records 必须能通过显式“加载更多记录”或等价可访问入口继续访问。
- `/skills/evidence` 的加载入口必须是标准可聚焦控件（原生 `button` 或等价 ARIA 语义），支持 Tab 聚焦，并能用 Enter / Space 触发。
- 加载更多请求必须保留当前 evidence URL 的筛选语义，只追加或覆盖 `limit` 与 `offset`；不得改变 `kind/w/wstart/wend/q/rt/src/skill/operator` 等筛选条件。
- 页面必须展示已加载数量与当前筛选下可访问总量，例如 `100 / 367`。
- 当全部 records 已加载完时，页面必须进入明确完成态；不得继续留下会触发空请求的无效入口。
- 加载失败时，页面必须保留已加载记录并提供可聚焦的重试入口；不得让用户卡死在前 100 条。
- 加载更多请求必须有有界恢复路径。请求超时、网络永久 pending、组件卸载或筛选 URL 变化时，页面不得永久停留在 disabled loading 状态；仍在当前筛选口径下时必须恢复为可重试状态。
- 若加载更多请求返回时当前 evidence 筛选 URL 已变化，旧响应必须被丢弃或取消，不得追加到新筛选列表。
- 加载更多重试必须复用失败批次的同一筛选参数和同一 `offset`；不得重复追加首批，也不得跳过失败批次。
- 连续加载到完成时，前端必须能以唯一记录数证明当前筛选下全部 records 可达；不得仅依赖按钮文案或 `N / N` 文案证明完整性。
- 加载期间若服务端返回的总量发生变化，页面必须使用最新总量和已加载唯一数重新计算入口或完成态；不得出现“已加载数小于总量但没有加载或重试入口”的状态。
- 刷新带筛选参数的 `/skills/evidence` URL 不要求恢复刷新前已加载到第几批；刷新后可以回到首批记录，但必须保持同一筛选口径、同一可访问总量，并能继续加载直到全部 records 可达。
- 本行为不得改变 `/api/skills/evidence` 的 `mode=used` 统计口径、kind 强制筛选、source 冲突处理或 ETag revalidate 规则。

## ADDED

### 可验证行为

- 打开 `/skills/evidence?kind=total&w=7d`，当接口 summary 表示当前筛选有 367 条 records 且首批返回 100 条时：
  - 页面显示前 100 条；
  - 页面显示 `100 / 367` 或等价已加载/总量信息；
  - 页面提供可 Tab 聚焦、Enter / Space 可触发的“加载更多记录”入口。
- 触发“加载更多记录”后，前端请求同一筛选条件下 `offset=100` 的下一批 records，并把后续 records 追加到当前列表；不得丢记录、重记录或改变筛选条件。
- 构造 367 条唯一 records，连续加载直到完成后，测试能统计到 367 条唯一记录，顺序与服务端各页拼接顺序一致，页面显示完成态且不再暴露无效加载入口。
- 加载下一批失败或超时后，已加载的 100 条仍保留，用户可通过可聚焦重试入口继续请求同一筛选、同一 offset 的后续记录。
- 当 `offset=100` 的慢响应返回前用户切换到另一个 evidence 筛选 URL，旧响应不得追加到新筛选列表；新页面只展示新筛选口径的数据和总量。
- 加载过程中服务端总量从 367 变为 368 或 366 时，页面必须更新总量并保持可继续操作或明确完成，不得出现“还有更多但没有入口”的状态。
- 刷新 `/skills/evidence?kind=total&w=7d&rt=codex&src=own` 后，页面回到该 URL 对应的首批记录，但仍显示同一筛选下的总量，并能继续加载直到全部记录。
