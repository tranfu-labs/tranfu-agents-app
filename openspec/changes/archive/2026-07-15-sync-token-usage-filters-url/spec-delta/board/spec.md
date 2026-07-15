# Board spec delta：Token Usage 筛选同步 URL

## ADDED — Token Usage 页面 URL 状态

- `/token-usage` 的时间范围、图表粒度、KEY 类型、模型、风险状态、Top N、搜索、隐藏零消耗与表格排序 MUST 由 URL query 驱动，不得只保存在 React 组件 state 或浏览器持久化存储。
- URL 参数固定为 `w/wstart/wend/g/kind/model/risk/topn/q/hz/sort/dir`。筛选变化 MUST 使用 replace，并沿用 `/skills` 的默认值省略语义，不得因初次渲染强制写入无关默认参数。
- 无 query 时 MUST 保持现有默认语义：`today`、`hour`、全部类型/模型/风险、Top 10、不隐藏零消耗、按消耗金额倒序。
- 刷新、复制链接、在新标签打开或浏览器历史导航到含 query 的 `/token-usage` 时，页面 MUST 从 URL 恢复全部可见筛选与排序。
- `w=custom` 时 `wstart/wend` 使用 Unix 秒并允许逐项保留；只有两端均为有效范围时才驱动新的 API 时间查询，半填写不得形成错误请求或清除已填写值。
- custom 缺少任一端或结束早于开始时 MUST 显示明确提示并禁用刷新；切换到非 custom 预设时 MUST 移除 `wstart/wend`。
- `w/wstart/wend/g` MUST 映射到 `/api/token-usage` 的 `start_timestamp/end_timestamp/time_granularity`；其它筛选与排序只影响当前 payload 的前端派生，不得改变 API 时间范围。
- 顶部 KEY 类型控件和明细区快捷类型按钮 MUST 读写同一 `kind` 参数；隐藏零消耗 MUST 使用 `hz`；可排序表头 MUST 使用 `sort/dir`。
- 详情抽屉、选中 KEY 与忽略风险属于临时页面状态，MUST NOT 写入 URL、localStorage 或 sessionStorage。
- 模型参数在 payload 到达前 MUST 保留；payload 到达后若模型已不存在，页面 MUST 立即按全部模型展示，并以 replace 清理失效参数。

## ADDED — Token Usage URL 可验证行为

- 打开 `/token-usage` 时页面按默认语义展示，URL 无需自动变成带全部默认参数的长链接。
- 打开 `/token-usage?w=30d&g=day&kind=dapp&model=gpt-5&q=alice&risk=high_error&topn=20&hz=1&sort=request_count&dir=asc` 时，对应控件、图表、排行与表格排序必须恢复。
- 自定义开始时间写入后 URL 保留 `w=custom&wstart=...`；补齐 `wend` 后 API 请求使用两端原值。
- custom 半填写或倒序时不请求 API、显示范围提示且刷新不可用；切回普通预设后 URL 不含旧 `wstart/wend`。
- 打开包含已失效 `model` 的链接时，payload 到达后回退到全部模型且 URL 清除该参数，不显示空选择或误导性空结果。
- 从含筛选 query 的 Token Usage URL 刷新或复制到新标签后，筛选结果不得回到组件默认值。
