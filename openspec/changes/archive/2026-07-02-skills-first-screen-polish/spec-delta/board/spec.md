# spec delta:board

> 合入后并入 `openspec/specs/board/spec.md`。本变更只修改 `/skills` 前端首屏展示规则，不改服务端 API 与统计口径。

## 修改规则(MODIFIED)
- `/skills` 的时间窗口展示必须随当前语言切换。窗口 query key 仍为
  `today` / `this_week` / `last_week` / `7d` / `14d` / `30d` / `90d` / `custom`，
  但界面 label 必须显示为当前语言文案；不得直接把 query key 暴露给用户作为选项文案。
- `/skills` 首屏核心文案必须随当前语言切换，至少覆盖控制条、移动筛选摘要、过去 W 变化 KPI、
  问题线索、待处理线索与 icon action 的 `aria-label` / `title`。英文模式下不得在这些首屏区域混入中文硬编码。
- `/skills` 控制条中的 Skill 搜索字段在桌面与平板断点下必须保持字段内部单行：
  label 与 input 同行，label 不换行，input 使用剩余宽度。手机展开筛选态可降级为单列，前提是页面根无横向滚动。
- `/skills` 的过去 W 变化 KPI 卡片必须把核心数值与证据 icon 放在同一行；证据入口仍是 icon button，
  并通过 `aria-label` / `title` 暴露“查看证据/查看名单”等语义，不重复显示可见文字“证据”。
- `/skills` 响应式顺序保持：桌面为控制条 → 过去 W 变化 → 问题线索 → 主分析区 → 待处理线索；
  平板为单列主内容流；手机为控制摘要 → 问题线索 → 待处理线索 → 排行/趋势 → 过去 W 变化。
  任何断点页面根不得出现横向滚动。

## 可验证行为(新增)
- 1440x900 打开 `/skills?view=skill&w=7d&topn=8`，切换中文/英文：
  时间窗口选项、移动摘要等窗口文案随语言变化，当前窗口仍写入同一个 `w=7d` query。
- 1440x900 英文模式打开 `/skills?view=skill&w=7d&topn=8`：
  控制条、过去 W 变化、问题线索、待处理线索不出现中文硬编码。
- 1440x900 打开 `/skills?view=skill&w=7d&topn=8`：
  搜索 Skill 名字段 label 与 input 同行，不发生 “Search skill / 搜索 skill 名”自身换行；
  “总触发次数/Total triggers”的数值和证据 icon 在同一行。
- 768x1024 打开 `/skills?view=skill&w=7d&topn=8`：
  控制条可以换行，但搜索字段内部不拆行；KPI 为 4×2；页面根无横向滚动。
- 375x812 打开 `/skills?view=skill&w=7d&topn=8`：
  默认只展示一行控制摘要，首屏优先露出问题线索与待处理线索；KPI 位于排行/趋势之后，页面根无横向滚动。
