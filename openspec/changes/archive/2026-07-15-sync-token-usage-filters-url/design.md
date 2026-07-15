# 设计：sync-token-usage-filters-url

字符图见 `wireframes.md`，行为增量见 `spec-delta/board/spec.md`。

## 方案

### 1. 单一 URL 状态模型

新增 token usage query-state 模块，使用 `nuqs` 的 typed parsers 和 `useQueryStates(..., { history: 'replace' })`。参数映射如下：

| URL 参数 | 页面状态 | 默认值 |
|---|---|---|
| `w` | 时间预设 | `today` |
| `wstart/wend` | 自定义起止 Unix 秒 | 空；仅 `w=custom` 时生效 |
| `g` | 图表粒度 | `hour` |
| `kind` | KEY 类型 | `all` |
| `model` | 模型 | `all` |
| `risk` | 风险状态 | `all` |
| `topn` | 排行数量 | `10` |
| `q` | KEY/归属搜索 | 空 |
| `hz` | 隐藏零消耗 | `0` |
| `sort/dir` | 表格排序字段/方向 | `quota/desc` |

沿用 `/skills` 的默认值清理行为，不在初次渲染时强制把默认参数写进 URL。筛选变化使用 replace，避免搜索输入和连续筛选制造大量浏览器历史记录；页面仍能在外部导航、刷新或复制链接后从当前 URL 恢复。

### 2. URL 到 API 查询的派生

`TokenUsageRoute` 读取 query state，只用 `w/wstart/wend/g` 派生 `TokenUsageQuery`。普通时间预设继续复用 `makeTokenUsageRange`；`w=custom` 且两端有效时使用 URL 时间戳。自定义范围仅填写一端或结束早于开始时，已填写值留在 URL，页面不把半成品错误发送给 API；控制条显示明确提示并禁用刷新。切回普通预设时同时移除失效的 `wstart/wend`，避免分享链接残留无效范围。

派生结果用相关字段 memoize。改变 KEY 类型、模型、风险、Top N、搜索、隐藏零消耗或排序只重算当前 payload 的视图，不应改变 API 时间范围或触发无意义的不同时间请求。

### 3. 页面控件统一读写

`TokenUsageView` 删除对应的分散本地筛选 state，改从统一 query state 读取归一化后的值：

- 顶部时间范围、图表维度、KEY 类型、模型、风险、Top N 与搜索控件写回 URL。
- KEY 明细区的快捷类型按钮与顶部 `kind` 共用同一参数；隐藏零消耗写 `hz`。
- 可排序表头写 `sort/dir`；非法或过期值回退到默认排序，不让页面抛错。
- 模型参数先保留到 payload 到达；若当前 payload 已不包含该模型，视图立即按“全部模型”展示并以 replace 清理失效的 `model` 参数，避免空下拉和误导性空结果。
- 详情抽屉、选中 KEY、忽略风险继续使用组件 state，关闭/刷新后恢复默认，且不污染可分享筛选 URL。

### 4. 事实源与版式

本次不改变页面信息架构，但在 custom 控制条下增加一行仅错误时出现的范围提示。首轮变更前 `docs/wireframes/pages/` 缺少已经存在的 `/token-usage` 路由基线，本 change 的 `wireframes.md` 以 `docs/wireframes/pages/token-usage.md` 为目标基线文件，在归档时补齐桌面/平板/手机页面事实，并在 `flow.md` 增加顶栏进入 Token Usage 以及筛选只改 query 的同页流转。

## 测试

### 单元测试

- 空 query 解析为今天、小时、全部、Top 10、不隐藏、消耗倒序，规范 URL 无需补默认值。
- 共享给 `useQueryStates` 的 nuqs parsers 通过 `createSerializer/createLoader` 做真实 round-trip；默认值清空、空格和非 ASCII 文本不丢失。
- 自定义起止逐项保留；两端有效时生成相同 Unix 秒的 API query；缺一端时不形成错误范围。
- 非法枚举、Top N、时间戳和排序方向安全回退，不向视图注入无效状态。
- payload 未就绪时保留模型参数；payload 已就绪且模型失效时回退全部模型。
- 切换时间预设或粒度时保留其它筛选，切换本地筛选时 API 查询键保持不变。

### AI / 浏览器验证

- 在 `/token-usage` 逐项改变全部筛选和排序，URL 立即反映状态且默认参数保持简洁。
- 刷新、复制到新标签以及从其它 URL 前进/后退后，界面、表格与图表恢复当前 query。
- `w=custom` 逐项填写起止值，半填写保留控件值，完整后请求对应时间段。
- custom 半填写或倒序时展示提示、刷新不可用；切回普通预设后 URL 不再保留 `wstart/wend`。
- 打开含已失效模型的分享链接，payload 到达后回退全部模型并清理 URL，不出现空下拉或误导性空结果。
- 顶部类型与明细快捷类型按钮双向一致；隐藏零消耗和表头排序刷新后保持。
- 1440×900、768×1024、375×812 下控制条与明细表布局无回归，页面根无新增横向滚动；浅色、深色、system 均可读。

## 权衡

- 复用 `nuqs` 而不是手写 `history.replaceState`，保持与 `/skills` 同一状态机制，并让 React Router 导航和浏览器历史行为一致。
- 不把详情抽屉、选中 KEY 或忽略风险加入 URL：它们是临时查看/处置状态，不属于用户确认的可分享筛选；这也与 `/skills` 对临时抽屉的处理一致。
- 不把本地筛选发给服务端：当前 API 返回所选时间范围的完整 KEY 数据，本地派生已经满足页面交互，扩展 API 只会增加契约和缓存键复杂度。

## 风险

- 动态时间默认值若在每次本地筛选时重新计算，可能导致 API query identity 抖动；通过只依赖 URL 时间字段的 memoized 派生避免。
- 自定义时间半填写若直接请求会形成错误范围；解析层显式区分 draft URL 与完整 API query。
- 模型名与搜索文本包含特殊字符；交给 `URLSearchParams/nuqs` 编解码并用 round-trip 测试覆盖。
- ADR-0002 的旧文本与仓库现有可选 Token Usage 模块冲突；只澄清“核心 Agent 遥测不采集”和“外部分发平台只读展示”的边界，不借本 change 扩大统计能力或采集范围。

## 实现后反思

- 实现与提案一致：全部可见筛选与表格排序统一由 `nuqs` query state 驱动，临时 KEY 选中/抽屉和忽略风险仍留在组件 state。
- API query 只依赖 `w/wstart/wend/g` 的 memoized 派生；浏览器验证普通筛选和排序只改 URL 与本地结果，没有改变时间范围。
- 首轮反思发现三项遗漏并已修正：nuqs 需要真实 serializer/loader round-trip 测试；custom 草稿需要可见错误和不可刷新状态；动态 model 需要失效回退与 URL 清理。第二轮复查又发现旧时间范围 payload 可能过早清理新范围 model，因此校验被限定为 payload range 与当前 API query 完全匹配后执行。
- custom 半填写或倒序返回 `null` API query，保留草稿 URL、显示明确提示并禁用刷新；切回非 custom 预设时清理 `wstart/wend`。两端有效后仍按 Unix 秒原值请求。
- 没有把临时抽屉、选中 KEY 或忽略风险写入 URL，没有修改服务端 API、统计口径、缓存或页面信息架构；ADR/AGENTS 的改动只消除既有只读模块与“核心遥测不采集 token”之间的事实冲突，未扩大采集或计费范围。
- 76 个前端单元测试、生产构建、改动文件定向 lint 与 wireframe 显示宽度检查通过。构建仅保留仓库既有的单 chunk 超过 500 kB 提示。
- 浏览器验证覆盖 custom 半填写、倒序、切回预设、失效 model 清理以及 1440/768/375 根宽度；三档均满足 `scrollWidth === clientWidth`，控制台无错误。
