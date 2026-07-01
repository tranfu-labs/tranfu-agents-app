# 设计:reflow-skills-trend-window

## 锁定口径
- 默认窗口: `/skills` 无参数进入时等价于 `w=7d`。旧 `win` 参数仍兼容；当 `w` 为空且 `win` 为空或非法时回退到 `7d`。
- 布局: 趋势图不再是全宽独占层，而是排行区域的下半区。桌面主分析区为左排行+趋势、右治理待办；平板/手机主内容单列。
- 图表比例: 单日槽宽沿用当前 30d 观感，`7d` 不放大、不压缩、不铺满整行；短窗口右对齐显示最新日期。
- 长窗口: `30d`、`90d`、`custom>7d` 的日期轨道可以超过可视区域，图表内部横向滚动，默认滚到最右侧最新日期。
- 联动: Skill 视角中排行选中态继续驱动趋势图 `selectedSegment`；Operator 视角不新增选中态，趋势图展示当前筛选后的 operator 分布。
- 空态: 沿用现状，窗口内无数据或筛选后无数据时显示 Empty，不渲染空轴。

## 当前实现问题
- `SkillsView` 当前顺序是控制条 -> KPI -> 健康条 -> 全宽趋势图 -> 主视图 split -> Donut -> 明细 -> 漏斗。
- `StackedSkillChart` 当前按 `days` 计算 `w`，再用 SVG `width:100%` 展示。7d 与 30d 的图形密度会随窗口变动，不适合承担稳定的布局基准。
- `chart-box` 已经具备内部横向滚动能力，但还没有“短窗口右对齐”和“长窗口切换后自动滚到最右”的明确行为。

## 信息架构
```
控制条
KPI 环带
治理健康条
主分析区:
  左:排行 / 操作员排行
     每日使用趋势图
  右:治理待办
归因 Donut
明细表 + 抽屉
公司库采纳漏斗
```

趋势图变成排行的时间解释层:用户先看“谁最多”，再立即看“这些使用发生在最近哪几天”。治理待办仍在右侧，保持管理动作的可见性。

## 改动文件与职责

### `frontend/src/lib/skillQuery.ts`
- `win` 默认从 `30` 改为 `7`。
- `w` 仍保留字符串参数，URL 显式传入时优先级高于 `win`。

### `frontend/src/lib/skillsWindow.ts`
- `keyFromParams()` 的 fallback 从 `30d` 改为 `7d`。
- 当 `win` 为 7/30/90 时继续映射为对应 `w`；非法或缺失时回退 `7d`。
- `custom` 无效时回退 `7d`。

### `frontend/src/views/Skills.tsx`
- 删除当前全宽趋势图 section。
- 在 `.skills-main-split` 左侧 frame 内部，排行内容之后追加一个非 frame 的趋势图区，例如:
  - 标题行: `每日使用趋势图` + 当前窗口 label。
  - 内容: `StackedSkillChart`。
- 不把趋势图再包一层 `.frame`，避免 frame 嵌套 frame。
- Skill 视角:
  - `RankBars` 保持点击选中/取消。
  - 下方趋势图继续接收 `selectedSegment={selected}`。
- Operator 视角:
  - `OperatorTable` 继续整行跳 `/operator/:name`。
  - 下方趋势图使用 `segmentKey="operator"` 展示当前筛选后的 Top operator，不把行点击改为选中。

### `frontend/src/components/Charts.tsx`
- 抽出或内联固定图表几何常量:
  - `DAY_SLOT` 采用当前 30d 观感对应的单日宽度。
  - `AXIS_PAD` 保留 Y 轴和右侧留白。
  - `SHORT_WINDOW_DAYS = 7`。
- `w` 不再为“为了填满容器而随天数重定比例”，而是日期轨道宽度:
  - `trackWidth = AXIS_PAD + axis.length * DAY_SLOT`。
  - `7d/today/this_week/last_week` 这类 `axis.length <= 7` 的轨道右对齐。
  - `axis.length > 7` 的轨道内部滚动，默认显示最右端。
- 给 `chart-box` 加 ref，在窗口天数、右端日期、视角切换变化时执行:
  - `scrollLeft = scrollWidth - clientWidth`。
  - 只在长窗口需要内部滚动时触发，避免用户滚动过程中被数据刷新频繁拉回。
- SVG 的实际 CSS 宽度使用轨道像素宽度，不再强制 `width:100%` 拉伸短窗口。
- 保留现有浮窗锚定、滚动关闭浮窗、今日进行中、TopN+其它分色、空态逻辑。

### `frontend/src/styles.css`
- 新增排行 frame 内部趋势图区样式，例如 `.skills-rank-chart`:
  - `border-top:1px solid var(--line)`，作为同一 frame 内部下半区分隔。
  - 标题和图表内容不再使用 `.frame`。
- 图表 SVG 增加专用类以覆盖通用 `.chart-box svg{width:100%}`，确保短窗口不被拉伸。
- 平板 `601px-1080px`: `.skills-main-split` 单列后，顺序自然为排行 -> 趋势 -> 治理待办。
- 手机 `<=600px`:页面根继续 `overflow-x:hidden`；趋势图内部可横滚；7d 右对齐且无需页面横滚。

## 多尺寸影响
- 桌面 `>1080px`:主分析区左列包含排行和趋势，右列治理待办；趋势图若 30d/90d 超过左列宽，只在图表内部滚动。
- 平板 `601px-1080px`:排行 frame 占满一行，趋势图在排行后紧跟；治理待办下一行。
- 手机 `<=600px`:排行表/条使用现有摘要行样式；趋势图位于摘要行后；30d/90d 仅 `.chart-box` 内部横滚。

## 需要验证的边界
- `today`、`this_week` 少于 7 天:固定单日槽宽，右对齐，不拉伸。
- `last_week`:7 天固定槽宽，右对齐；不强行显示“今日进行中”之外的新语义。
- `custom`:1-7 天右对齐；8-90 天内部滚动并默认最右。
- 切换 `topn`、`runtime`、`source`、`q`:排行和趋势图使用同一过滤后数据，筛选后全空继续 Empty。
- 数据刷新:增量刷新保留旧数据时不应反复把用户手动滚动位置拉回；只在窗口/右端日期/视角变化时自动滚最右。
- Operator 行点击仍然跳详情，不被趋势图联动需求劫持。

## 测试策略
- 单元测试:
  - `resolveSkillsWindow({})` -> `7d`。
  - `resolveSkillsWindow({ win: 30 })` -> `30d`，旧参数仍兼容。
  - 无效 `custom` fallback -> `7d`。
  - 图表 layout helper 覆盖 1/7/30/90 天的 trackWidth、rightAlign、shouldScrollToEnd。
- AI/视觉验证:
  - `npm --prefix frontend run test:unit`。
  - `npm --prefix frontend run build`。
  - 本地打开 `/skills`，在 1440、768、375 三个视口分别检查 `7d`、`30d`、`90d`。
  - 重点看页面根无横向滚动、30d/90d 默认显示最新日期、7d 右对齐且不拉伸。

## 风险与回滚
- 风险:趋势图下移后，Operator 视角如果操作员表很长，趋势图会被推到更低位置。先按用户确认的“排行下方”执行，不额外裁剪 operator 表；若后续反馈趋势图过低，再单独讨论 operator TopN 摘要。
- 风险:自动滚到最右如果绑定过宽，会干扰用户查看历史。实现时必须限制触发依赖。
- 回滚:纯前端布局/默认参数变更，回滚对应 commit 即可；无数据迁移。
