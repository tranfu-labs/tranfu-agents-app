# Board spec delta：Agents 固定按 Agent 运行时长统计

## MODIFIED — Agents 运营看板

- `/agents` 的统计集合为当前搜索、状态与问题线索范围内的全部 Agent 身份卡片，统计对象固定为 Agent，主指标固定为所选窗口运行时长。页面不得再按操作员或运行终端切换观察维度。
- 控制条 MUST 只保留 Agent 搜索、状态、时间窗、自定义时间与排序，并以静态文案说明“全部 Agent · 按运行时长”；不得渲染只有一个选项的伪切换控件。操作员和运行终端不得作为 `/agents` 的筛选条件或明细表字段。
- `/agents` URL 支持 `q/status/signal/w/wstart/wend/sort`；旧 `rank/rt/op` 参数 MUST 作为 no-op 忽略并由前端 replace 清理，不得继续形成隐藏筛选。默认排序 MUST 为 `window_time`。
- Agent 搜索 MUST 匹配 Agent 名、任务、当前步骤与 model；不得匹配页面已不展示的操作员或运行终端字段。
- 八卡固定为：窗口总运行时长、平均运行时长/活跃 Agent、窗口活跃 Agent、Agent 总数、当前在线、本周运行时长、累计运行质量、待处理 Agent。前三张窗口指标在当前与上一窗口完整可用时展示同长度环比；平均值以窗口总时长除以窗口活跃 Agent 数。
- 主分析区左侧 MUST 为 Agent 运行时长排行，右侧 MUST 为 Agent 运行时长分布/趋势。排行按窗口 `active_seconds` 降序，零时长不进入排行，行点击下钻 `/agent/:key`；不得再回填操作员或运行终端筛选。
- 单日窗口正值 MUST 显示按 Agent 运行时长分区的环形扇形图，中心显示全部 Agent 总运行时长；多日窗口 MUST 显示按 Agent 分段的逐日运行时长堆叠柱。每天全部分段之和 MUST 等于该日总运行时长，当前窗口使用 Top 8 + 其他且不得丢失时长。
- 图表不得再提供“活跃 Agent｜活跃时长”指标切换。tooltip MUST 同时保留当日活跃 Agent 数、总运行时长和各 Agent 运行时长；当前窗口全零时 MUST 显示 Empty。
- Agent 明细 MUST 保留 Agent/状态/任务、窗口运行时长与天数、累计质量、Skill/MCP、Shim、最近活跃和整行详情下钻，但 MUST 删除操作员与运行终端列。头像与可访问名称 MUST 以 Agent identity 为基准。
- 统计基数 MUST 继续使用按 `operator + agent||runtime` 合并后的身份卡片，不得退化为按 session 展示或计数；同名 Agent 身份不得跨身份合并时长。

## MODIFIED — Agents 可验证行为

- 打开 `/agents?rank=runtime&rt=codex&op=alice` 时，页面 MUST 展示全部 Agent 口径并通过 replace 移除三个旧参数；不得因隐藏参数缩小排行、趋势或明细集合。
- 无窗口参数打开 `/agents` 时默认使用 `today` 与 `sort=window_time` 语义，但默认值无需写入 URL。
- `today` 有正时长时显示 Agent 环形扇形图，中心总值等于全部扇区原值之和；`7d` 显示按 Agent 分段的短窗堆叠柱；`30d` 只在图表盒内部滚动。
- Agent 排行与明细窗口时长必须来自同一批已合并身份卡片和同一组窗口日；排行第一行必须是当前窗口时长最大的非零 Agent。
