# 设计：skills-first-screen-polish

## 方案
本变更是前端展示层打磨，围绕 `/skills` 首屏的 3 个用户确认项和自查项实现：

- 时间窗口随中英文切换。
- 搜索 Skill 名不换行。
- “总触发次数”等 KPI 的核心数字和证据 icon 在同一行。
- 首屏核心区域避免英文态混中文，并保持桌面、平板、手机断点的既有信息流。

### 1. SKILLS 首屏 i18n 收口
涉及文件：
- `frontend/src/lib/i18n.ts`
- `frontend/src/lib/skillsPresentation.ts`
- `frontend/src/views/Skills.tsx`
- `frontend/src/components/skills/KpiStrip.tsx`
- `frontend/src/components/skills/HealthBar.tsx`
- `frontend/src/components/skills/GovernanceTodo.tsx`

实现策略：
- 在 `i18n.ts` 增加 `/skills` 首屏专用 key：
  - 时间窗口：`window_today`、`window_this_week`、`window_last_week`、`window_7d`、`window_14d`、`window_30d`、`window_90d`、`window_custom`。
  - 控制条：`compareToggle`、`hideZeroUsage`、`filterAction`、`customStart`、`customEnd`。
  - KPI：`kpiPeriodChange`、`kpiTotalTriggers`、`kpiCoverage`、`kpiActiveOperators`、`kpiAvgSkillPerSession`、`kpiUntrackedShare`、`kpiIdleSkills`、`kpiUnusedRatio`、`kpiTop3Share`、`snapshot`、`comparisonOff`。
  - 线索与动作：`healthIssues`、`usageSignals`、`todoSignals`、`heavyUsers`、`sleeping7d`、`lowCoverageUsers`、`untrackedUsed`、`installedUnused`、`catalogZeroInstall`、`viewRawRecords`、`viewByOperatorEvidence`、`ignoreInPage`、`moreActions`、`restoreIgnored`、`noTodo`、`showAll`、`collapse`。
- `skillsPresentation.ts` 新增 `windowDisplayLabel(key, t)`，并把 `mobileFilterSummary(params, view)` 改为 `mobileFilterSummary(params, view, t)`。
- `SkillsToolbar` 的窗口 `<option>` 使用 `windowDisplayLabel`，custom 日期 label、环比、隐藏 0 使用、移动摘要都走 `t`。
- `KpiStrip`、`HealthBar`、`GovernanceTodo` 接收 `t`，首屏可见文案和 tooltip/aria-label 不再硬编码中文。

### 2. 控制条搜索字段不换行
涉及文件：
- `frontend/src/views/Skills.tsx`
- `frontend/src/styles.css`

实现策略：
- 给搜索 field 添加稳定结构：label 文案为不可换行的小标签，input 使用 `min-width: 0` 吃剩余宽度。
- 桌面/平板下 `.skills-dashboard-toolbar .search-field` 保持 `flex-direction: row`、`align-items: center`、`white-space: nowrap`，避免“搜索 skill 名”拆行。
- 手机断点保留完整筛选展开后的 100% 宽度单列输入，不强行单行，避免 375px 宽度溢出。

### 3. KPI 卡片首行合并数值与证据 icon
涉及文件：
- `frontend/src/components/skills/KpiStrip.tsx`
- `frontend/src/styles.css`

实现策略：
- 每张 KPI 卡片改为：
  ```text
  ┌──────────────┐
  │ 12,345    ↗  │  ← `.skills-kpi-top`
  │ 总触发次数   │
  │ 12,345 records│
  │ ▲ +20.6%     │
  └──────────────┘
  ```
- 证据入口仍使用 `.evidence-icon-link`，只改变位置，不改变跳转和 aria-label。
- `.skills-kpi-card .v` 禁止挤压 icon，超长数字允许缩小/截断规则不影响按钮；短结论继续截断，不铺长 skill 串。
- 环比关闭时显示本语言的 `comparisonOff`；快照显示本语言的 `snapshot`。

### 4. 响应式首屏顺序与密度
涉及文件：
- `frontend/src/styles.css`
- `openspec/changes/skills-first-screen-polish/wireframes.md`

实现策略：
- 桌面 `>1080px`：控制条 → KPI 8 格 → 问题线索 → 排行/趋势左右并列 → 待处理线索。
- 平板 `601px-1080px`：控制条可换行；KPI 4×2；主体单列，页面根无横向滚动。
- 手机 `≤600px`：控制摘要 → 问题线索 → 待处理线索 → 排行/趋势 → KPI 2×4；完整筛选只在展开后显示。
- 清理或修正当前 CSS 中对旧 `.skills-main-split` 的无效排序选择器，避免后续维护误判。

## 字符图
基线：`docs/wireframes/pages/skills.md`。

### 桌面 1440×900 首屏增量
```
┌─ 控制条 ───────────────────────────────────────────────────────────────────────────────┐
│[按Skill|按人] 时间[7 天▾] [环比✓] 🔍 搜索 skill 名[____________] runtime[全部▾] 来源[全部▾]│
│Top[8▾] [隐藏0使用]                                                   cnt: 7d             │
└────────────────────────────────────────────────────────────────────────────────────────┘

┌─ 过去 W 变化 ──────────────────────────────────────────────────────────────────────────┐
│┌──────────────┐┌──────────────┐┌──────────────┐┌──────────────┐┌──────────────┐...    │
││ 12,345    ↗  ││ 42/60     ↗  ││ 42 人     ↗  ││ 1.70      ↗  ││ 28.0%     ↗  │       │
││ 总触发次数   ││ 公司库覆盖率 ││ 活跃操作员数 ││ 平均skill/会 ││ 未收录占比   │       │
││ 12,345 records││ 42/60 in use ││ 42 operators ││ 1.70 / session││ 2 skills · 4 records│   │
││ ▲ +20.6%     ││ ▲ +5.0%      ││ ▲ +10.5%     ││ ▲ +21.4%     ││ ▼ -3.0%      │       │
│└──────────────┘└──────────────┘└──────────────┘└──────────────┘└──────────────┘...    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 平板 768×1024 增量
```
┌─ 控制条 ────────────────────────────────────────────────┐
│[按Skill|按人] 时间[7 天▾] [环比✓]                       │
│🔍 搜索 skill 名 [________________________] Top[8▾]       │
│runtime[全部▾] 来源[全部▾] [隐藏0使用]                    │
└─────────────────────────────────────────────────────────┘

┌─ 过去 W 变化：4×2 ───────────────────────────────────────┐
│┌────────┐┌────────┐┌────────┐┌────────┐                │
││12,345 ↗││42/60 ↗ ││42人  ↗ ││1.70 ↗  │                │
││总触发  ││覆盖率  ││活跃者  ││均skill │                │
│└────────┘└────────┘└────────┘└────────┘                │
│┌────────┐┌────────┐┌────────┐┌────────┐                │
││28.0% ↗ ││14个  ↗ ││23.3% ↗ ││58.0% ↗ │                │
││未收录  ││闲置数  ││装未用  ││Top3集  │                │
│└────────┘└────────┘└────────┘└────────┘                │
└─────────────────────────────────────────────────────────┘
```

### 手机 375×812 增量
```
┌─ 控制摘要 ───────────────┐
│7 天 · 按 Skill · 全部    │
│runtime/source · [筛选⌄] │
└──────────────────────────┘
┌─ 问题线索 ───────────────┐
│figma 正在被自发使用      │
│4 records · 2 operators ↗ │
└──────────────────────────┘
┌─ 待处理线索 ─────────────┐
│有使用但未收录            │
│figma · 3 次 · alice/bob ⋯│
└──────────────────────────┘
┌─ 排行 / 趋势 ────────────┐
│Skill A █████ 1,234       │
│每日趋势 ▆ ▅ ▇ ▃ ▆ ▅ ▇    │
└──────────────────────────┘
┌─ 过去 W 变化：2×4 ───────┐
│12,345 ↗ 总触发   42/60 ↗ │
│42 人 ↗ 活跃者    1.70 ↗  │
└──────────────────────────┘
```

## 测试方案
单元测试：
- `frontend/src/lib/skillsPresentation.test.ts`
  - `windowDisplayLabel` 中英文输出。
  - `mobileFilterSummary` 中英文输出，含 runtime/source 筛选。
  - 继续保证 `compactNameList` 不生成长 slash 串。

AI 验证流程：
- `npm --prefix frontend run test:unit`
- `npm --prefix frontend run build`
- 本地 dev server 打开 `/skills?view=skill&w=7d&topn=8`：
  - 1440×900：中英文切换后时间窗口、KPI、线索文案同步切换；搜索 label 不换行；总触发次数数值与证据 icon 同行。
  - 768×1024：控制条可换行但搜索字段内部不拆行；KPI 为 4×2；页面根无横向滚动。
  - 375×812：默认只显示控制摘要；首屏顺序为问题线索、待处理线索、排行/趋势、KPI；页面根无横向滚动。

## 权衡
- 这次把 `/skills` 首屏核心硬编码文案一起纳入 i18n，而不是只修窗口下拉。代价是 i18n key 较多，但能避免英文模式下首屏仍混中文。
- KPI 卡片不改为更大的 hero 数字，只做行内合并和密度优化，避免破坏既有 8 格信息架构。
- 搜索字段在手机展开态仍允许 label 在上、input 在下，这是为了 375px 宽度不溢出；“不换行”约束主要针对桌面/平板首屏控制条。

## 风险
- i18n key 遗漏会显示 key 名：通过 unit test 覆盖关键展示 helper，并在构建后截图验证中英文态。
- KPI 卡片压缩后可能在极长数字下拥挤：CSS 使用 `min-width:0`、`font-variant-numeric`、短结论截断，证据 icon 固定宽度。
- 平板控制条控件较多：允许整条 toolbar 换行，但单个搜索 field 内部不换行，避免横向溢出。
