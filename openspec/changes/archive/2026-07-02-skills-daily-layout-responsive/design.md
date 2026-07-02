# 设计:skills-daily-layout-responsive

> 在现有 SKILLS 证据导向 dashboard 上调整主分析区布局。核心不是改统计口径,而是让不同时间窗口有合适的阅读形态。

## 锁定口径
- **短窗口定义**:`dayCount <= 14`。覆盖 `today`、`this_week`、`last_week`、`7d`、`14d`、
  以及有效自选窗口中天数 `<=14` 的场景。
- **长窗口定义**:`dayCount >= 30` 或自选窗口 `>14` 天。现有预设主要是 `30d`、`90d`。
- **短窗口布局**:桌面 `>1080px` 下,主分析区整宽分两列:左为「排行 Bar / 操作员排行」,
  右为「每日使用」。每日使用不再作为排行卡片下半区,也不再被右侧待处理侧栏挤窄。
- **长窗口布局**:桌面 `>1080px` 下,主分析区整宽上下排列:先排行,再每日使用。每日使用保留
  固定单日槽宽和 `.chart-box` 内部横滚,默认显示最新日期。
- **待处理线索独立行**:不再放在主分析区右侧。Skill 视角下 3 类线索
  (有使用但未收录 / 装了 W 内没用 / 收录但零装机)各自是一个独立区块;Operator 视角保留同类治理信号,
  也作为同一治理行内的独立区块。
- **窄屏降级**:平板 `601px-1080px` 与手机 `<=600px` 均单列:排行 -> 每日使用 -> 待处理线索。
  页面根不得横向滚动。
- **数据口径不变**:筛选、Top N、`sel` 选中态、evidence 链接和 governance 数据来源沿用现状。

## 实现方案

### 1. `/skills` 主分析区拆块
`frontend/src/views/Skills.tsx` 当前结构是:

```
skills-main-split
  left frame: 排行 + 每日使用
  right frame: GovernanceTodo
```

改为:

```
skills-analysis skills-analysis--short|skills-analysis--long
  frame skills-rank-panel: 排行 / 操作员排行
  frame skills-trend-panel: 每日使用

frame skills-governance-row-frame
  GovernanceTodo(独立区块行)
```

布局类由 `chartDays` 或 `data.window` 推导:

- `isShortWindow = chartDays <= 14`
- short:CSS grid 两列,例如 `minmax(0, 0.95fr) minmax(360px, 1.05fr)`。
- long:CSS grid 单列。

Operator 视角下排行行继续点击进入 `/operator/:name`,不新增行选中态;趋势图展示当前筛选后的 operator 分布。

### 2. 短窗口趋势图自适应宽度
现有 `resolveSkillsChartLayout(dayCount)` 对所有窗口使用固定单日槽宽,导致 7d 轨道只有约 250px。

改为引入可视宽度参与布局:

```
resolveSkillsChartLayout(dayCount, viewportWidth)
```

建议返回:

- `mode: "fit"` when `dayCount <= 14`
- `mode: "scroll"` when `dayCount > 14`
- short fit:
  - `trackWidth = max(axisPad + dayCount * minDaySlot, viewportWidth)`
  - `scrollToEnd = false`
  - `rightAlign = false`
  - bar width 使用上限,避免 `today` 单柱被拉成粗块,例如 `bw = min(30, max(8, step * .64))`
- long scroll:
  - 沿用固定 `SKILLS_CHART_DAY_SLOT`
  - `scrollToEnd = true`
  - 页面根不横滚,仅 `.chart-box` 横滚

`StackedSkillChart` 用 `ResizeObserver` 或轻量 `useLayoutEffect` 读取 `chartBoxRef.current.clientWidth`,
传入 layout helper。首帧宽度未知时使用现有固定宽度兜底,测量后重排。

### 3. 待处理线索区块化
`frontend/src/components/skills/GovernanceTodo.tsx` 保留现有分组和动作,但样式改为可独立铺开的区块:

```
skills-governance-blocks
  skills-governance-block: 有使用但未收录
  skills-governance-block: 装了 W 内没用
  skills-governance-block: 收录但零装机
```

桌面三列;宽度不足时自动换为两列/一列。每个区块内部保留 Top items、计数、`看证据`、`找人`、`忽略`、`查看全部` 等非破坏动作。

### 4. CSS 响应式规则
新增或替换关键类:

```
.skills-analysis{display:grid;gap:16px;min-width:0}
.skills-analysis--short{grid-template-columns:minmax(0,.95fr) minmax(360px,1.05fr)}
.skills-analysis--long{grid-template-columns:1fr}
.skills-trend-panel,.skills-rank-panel{min-width:0}
.skills-governance-blocks{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
```

`<=1080px`:

```
.skills-analysis--short,
.skills-analysis--long,
.skills-governance-blocks{grid-template-columns:1fr}
```

手机下保留摘要行和图表内部滚动约束。

## 方案权衡
- **不用只拉宽 7d**:拉宽只能修当前截图,但待处理侧栏仍然挤占主分析区。按窗口切换布局更符合阅读任务。
- **短窗口左右,长窗口上下**:短窗口适合把排行和日变化并排对照;长窗口需要更长时间轴,上下布局给趋势图完整宽度和内部滚动空间。
- **待处理线索独立行**:治理动作不再抢主分析区右列,代价是页面纵向高度增加一行;但信息层次更清楚。
- **平板/手机不强行左右布局**:虽然短窗口桌面左右并列,但窄屏强行两列会让排行和图表都难读,因此降级单列。

## 风险与回滚
- 短窗口图表测量宽度若首帧为 0,可能出现一次布局跳动。用固定宽度兜底并在测量后重排可接受。
- `GovernanceTodo` 样式调整可能影响 Operator 视角治理列表。实现时需同时看 skill/operator 两视角。
- 回滚路径:还原 `Skills.tsx` 主分析区结构、`skillsChartLayout` 短窗口 fit 逻辑和 CSS 类即可,无数据迁移。

## 验证计划
- 单元测试:
  - `resolveSkillsChartLayout(7, 800)` / `14, 800` 为 fit 模式且 `scrollToEnd=false`。
  - `resolveSkillsChartLayout(30, 800)` / `90, 800` 为 scroll 模式且 `scrollToEnd=true`。
  - 短窗口 bar width 有上限,避免 1 天窗口柱体过宽。
- 构建:
  - `npm --prefix frontend run test:unit`
  - `npm --prefix frontend run build`
- 视觉验证:
  - `/skills?w=7d` 1440x900:排行和每日使用左右并列,每日使用填满右侧面板。
  - `/skills?w=14d` 1280x800:同短窗口布局,无大面积空白。
  - `/skills?w=30d` 1440x900:排行在上,每日使用全宽在下,图表内部横滚并默认显示最新日期。
  - `/skills?w=90d` 375x812:页面根无横向滚动,仅图表内部横滚。
  - `/skills?view=operator&w=7d`:操作员排行可跳详情,趋势图展示 operator 分布,待处理线索独立行。
