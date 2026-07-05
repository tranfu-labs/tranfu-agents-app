# 设计：m3-t9-evidence-completeness

## 方案

### 1. 明确 evidence 总量来源

`SkillsEvidencePayload.summary` 已承载各 kind 的汇总数字。实现阶段优先使用 `summary.records` 作为 raw records 总量；名单型 kind 优先使用能表达名单总数的 summary 字段，若后端 payload 对某类名单没有专用字段，则降级为 `items.length` 并只展示已加载项。

本 change 的缺陷场景是 raw records `367` 条，因此 raw records 总量展示必须覆盖。

### 2. 抽出分页 query 与追加逻辑

在 `frontend/src/lib/skillsEvidence.ts` 增加纯函数：

- `evidencePageQuery(search, loadedCount, limit)`：从当前 search 参数复制 evidence 筛选，设置 `offset=loadedCount` 与 `limit=limit`，并保证 `kind` 和 `w` 有默认值。
- `evidenceQueryKey(search)`：归一化当前 evidence 筛选口径，排除 `limit/offset` 这类分页游标，用于判断慢响应是否仍属于当前 URL。
- `mergeEvidencePage(current, next, mode)`：按当前视图类型追加 `records` 或 `items`，保留 summary/top/daily/actions 等首批上下文；追加时用稳定 key 去重，并保持“服务端各页顺序拼接”的展示顺序。
- `evidenceLoadedCount(payload, mode)` 与 `evidenceTotalCount(payload, mode)`：统一计算 `已加载/总量`。
- `evidenceHasMore(payload, mode)`：根据唯一已加载数与最新总量判断是否继续展示加载入口；若最新总量小于已加载数，完成态以已加载唯一数为准，避免出现 loaded > total 的反常文案。

这些逻辑可直接单测，不把分页状态和 DOM 事件耦在一起。

### 3. Evidence 视图状态

`SkillsEvidenceView` 在首批 `data` 变化时重置本地分页状态：

- 当前展示数据初始化为首批 payload。
- `loadingMore`、`loadMoreError` 清空。
- `loadedCount` 来自首批 `records.length` 或 `items.length`。
- 当前 `queryKey` 来自 `evidenceQueryKey(search)`；后续分页响应只有在 `queryKey` 仍匹配时才允许合并。

点击“加载更多记录”时：

1. 使用当前 `location.search` 和 `loadedCount` 构造下一批 API URL。
2. 请求 `/api/skills/evidence?...&offset=<loaded>&limit=100`。
3. 为请求创建 `AbortController` 与有界 timeout，例如 15 秒。timeout、组件卸载或筛选 URL 变化时 abort 当前请求并恢复为可重试状态。
4. 成功返回后先比对请求发起时捕获的 `queryKey` 与当前 `queryKey`；不匹配则丢弃旧响应，不追加到新筛选列表。
5. query 匹配时把下一批 records/items 追加到当前展示 payload；如果返回空批但最新总量仍大于已加载唯一数，则进入可重试错误态，避免静默失败。
6. 失败时保留已加载内容并显示重试文案；重试必须复用同一筛选参数与同一 `offset`，不得重复请求首批或跳过失败批次。

### 4. 数据漂移处理

`offset` 分页期间服务端记录集可能变化。实现不改为游标分页，但 UI 必须保持可操作：

- 每个成功响应后读取最新 `summary.records` 或名单总数字段，并用它更新总量展示。
- 若最新总量增加，例如 `367 -> 368`，且唯一已加载数仍小于最新总量，继续展示加载入口。
- 若最新总量减少，例如 `367 -> 366`，但本地已加载唯一记录数已达到或超过最新总量，进入完成态，完成文案以 `已加载全部 N 条记录` 表达，其中 `N` 使用当前可证明的唯一已加载数或最新总量中的较大值，避免 loaded < total 且无入口。
- 若后续批次返回重复记录导致唯一已加载数没有增长，且总量仍显示还有更多，则进入可重试错误态，而不是无限请求或静默完成。

### 5. 可访问入口与完成态

加载入口必须是原生 `<button type="button">` 或等价可访问控件。按钮默认可通过 Tab 聚焦，Enter/Space 触发，不额外拦截键盘事件。

按钮区域展示：

- 未到底：`加载更多记录` + `100 / 367`。
- 加载中：`加载中...`，按钮 disabled。
- 错误：`加载失败，重试`，按钮保持可聚焦可触发。
- 已到底：显示 `已加载全部 367 条记录`，不再留下无效入口。

### 6. URL 刷新语义

已加载批次数只存在组件内存中。刷新 `/skills/evidence?kind=total&w=7d&rt=codex` 后，页面重新按该 URL 取首批数据；只要仍显示同筛选总量并可继续加载到全部，就满足验收 3。

## 权衡

- 选择显式“加载更多”而不是传统分页：改动面小，不破坏 evidence 页“顺着同一批证据继续看”的连续阅读心智，也更适配手机摘要行。
- 不采用无限滚动：产品要求必须有明确、可聚焦、可键盘触发的入口；无限滚动也更难表达错误重试和到底态。
- 不把 offset 写入 URL：刷新后恢复已展开批次不是本轮验收要求，写入 URL 会扩大状态语义并影响分享链接稳定性。
- 不改后端接口：服务端已有 `limit/offset`，本轮只补前端可达入口，避免触碰 evidence 统计口径。
- 不改为游标分页：总量漂移可以通过去重、最新 summary 与可重试状态处理到“不丢失操作入口”；游标协议属于后端接口语义扩展，超出本缺陷范围。

## 风险

- 若某些名单型 kind 的 summary 没有总量字段，只能先准确展示已加载项和完成态。实现时需确认 payload 字段，必要时把 raw records 作为本轮硬验收路径，名单型入口做兼容。
- `offset` 基于已加载条数，若服务端排序不稳定可能出现重复或漏项。当前接口应按既有 evidence 排序返回；前端仍会用合并去重降低重复渲染风险，但不改变服务端排序。
- ETag revalidate 层按完整 URL 缓存，分页请求 URL 不同于首批 URL，应能自然区分。实现时需确认不会被 9.5 秒刷新节流挡住手动加载。
- 有界 timeout 需要避免和慢网络误伤之间的取舍。15 秒作为前端恢复阈值，不代表请求结果无效；超时后用户可重试，已加载数据保留。

## 回滚

回滚前端分页状态与加载入口即可恢复当前首批展示行为；不涉及数据库、协议或服务端 schema 迁移。
