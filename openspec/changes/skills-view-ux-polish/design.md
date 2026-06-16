# 设计:skills-view-ux-polish

> 在 skills-operator-view / skills-stats-page 已落地的 SKILLS 总览/详情之上,只做交互与布局打磨。
> 不改后端、不改聚合口径,本文件只描述前端增量。

## 锁定口径(2026-06-16 访谈逐项拍板,实现时不得擅改)
- **后端零改动**:`first_seen` 是服务端写入的完整 UTC ISO 时间戳(= `recv`,如
  `2026-06-16T12:34:56.789+00:00`),`/api/operator/{name}` 与 `/api/skill/{name}` 的 `records`
  均已 `SELECT first_seen`,前端 `types` 已有 `first_seen?: string`。本变更不碰 `server/app.py`。
- **操作员详情 ⑨ 区左右对调**:左 = RUNTIME 分布(窄,固定列宽 ~320–360px),右 = 使用 Skill 排行
  (宽,占剩余)。≤1080px 降级单列(沿用现有断点)。
- **操作员详情 skill 排行默认 7 天**:命名「使用 Skill 排行」,表内保留 7天/30天 列;
  **默认按 7 天使用次数降序**,平手按累计、再按名称。这是详情页内部默认,不影响总览两张主表(仍 30 天)。
- **视角切换独立卡片**:把 `[ 按 Skill ] / [ 按人 ]` 抽到页面最顶部的独立标准 `frame` 卡片;
  标题栏左侧为「视角」、右侧 `cnt` 带随视角变化的一行说明文案。内容行放 32px 高分段按钮,
  选中态用品牌红 `--brand`;筛选条(搜索/runtime/来源/时间窗)留在原统计卡,口径不变。
- **最近记录到秒**:操作员详情与 skill 详情的"最近记录"首列由 `day` 改为 `first_seen` 截到秒
  (`YYYY-MM-DD HH:MM:SS`,直接切片 = UTC 墙钟,与现有 `day` 同口径,不做时区转换);`first_seen` 缺失回退到 `day`。
- **整行可点 + 局部优先**:所有有下钻目标的表格(总览 SkillsTable→`/skill/:name`、总览 OperatorTable→
  `/operator/:name`、操作员详情的 skill 排行→`/skill/:name`)整行可点。行内若有自身交互(表头排序在 thead;
  未来行内若加按钮/链接)以局部交互为准,`stopPropagation` 阻止触发整行跳转。"最近记录"表无跳转目标,
  指针改回 `default`,不做整行可点。

## 实现要点

### 1+3 操作员详情 ⑨ 区(OperatorDetail.tsx + styles.css)
- 把现有 `<div className="dist">`(50/50:左 skill 表 / 右 runtime)替换为新 `<div className="dist-mirror">`:
  CSS `grid-template-columns: 360px minmax(0,1fr)`(左窄右宽),≤1080px 单列。
- 左栏 = `runtimeDist`(`<Distribution items={data.runtime}>`),右栏 = 原 skill 明细表。
- 右栏标题文案改为「使用 Skill 排行」(新增 i18n key,如 `skillRank`)。
- 渲染前对 `data.skills` 在组件内重排:`sessions_7d desc`,平手 `sessions_total desc`,再 `name`。
  (可选增强:给该表头加和总览表一致的可点排序,默认列=7d、desc;最小实现只重排即可。)

### 2 视角切换独立卡片(Skills.tsx + styles.css)
- 把 `ViewSwitch` 从统计卡内移出,单独包一层 `<section className="frame viewcard">`,置于页面顶部
  (统计/筛选卡之上)。
- 卡片沿用标准 `frame` 结构:`h2` 左侧标题为「视角」,右侧 `.cnt` 放说明文案;
  `.viewbody` 内容行只放 32px 高分段按钮。
- 分段按钮选中态用 `--brand` 背景 + 白字,按钮尺寸贴近现有设计规范而非大号 CTA。
- 切视角仍沿用现有逻辑(`setParams({ view, sort:'sessions_30d', dir:'desc' })`,时间窗不重置)。

### 4 最近记录到秒(utils.ts + OperatorDetail.tsx + SkillDetail.tsx)
- `utils.ts` 新增 `fmtTs(iso?: string)`:`iso ? iso.slice(0,19).replace('T',' ') : ''`(空回退由调用处补 `day`)。
- 两个详情页"最近记录"首列:`{fmtTs(record.first_seen) || record.day || ''}`。

### 5 整行可点(Skills.tsx + OperatorDetail.tsx + SkillDetail.tsx + styles.css)
- 三张下钻表用 `useNavigate()`,`<tr onClick={() => navigate(to)}>`,`to` = 原 `<Link>` 的目标
  (含 `location.search` 透传)。行内原 `<Link><b>name</b></Link>` 降级为 `<b>name</b>`。
- 可访问性:`<tr role="link" tabIndex={0} onKeyDown>`(Enter/Space 触发)。
- 表头排序 `<th onClick>` 加 `e.stopPropagation()`(虽在 thead 不在行内,统一规则;未来行内交互照此)。
- CSS:删/改 `.skills-wrap tbody tr{cursor:default}`(styles.css:102),让 `.skill-table tbody tr{cursor:pointer}` 生效;
  "最近记录"表(走通用 `tbody tr{cursor:pointer}`,styles.css:159)单独设 `cursor:default`(无跳转)。

## 线框图(只画改动处;基线见 skills-operator-view/design.md 屏 A/屏 B)

### 改动 A:/skills 顶部 —— 视角切换抽成独立标准卡片(问题 2)
```
改前(挤在统计/筛选卡里,分量轻):
┌─ 统计标题卡 ──────────────────────────────────────────────
│  // SKILLS 统计
│  视角:[ 按 skill ] [ 按人 ]      ← 小号分段,和筛选挤一起
│  [搜索…] [runtime ▾] [来源 ▾] [时间窗 ▾]
└───────────────────────────────────────────────────────────

改后(独立标准 frame 卡片置顶;标题栏说明 + 内容行 32px 分段按钮):
┌─ ⓪ 视角                                      按 Skill:看哪个能力最热 ──┐
│   [ 按 Skill ] [ 按人 ]  ← 32px 高分段按钮,选中态用 --brand              │
└──────────────────────────────────────────────────────────────
┌─ 统计标题卡(筛选条留这,口径不变)──────────────────────────
│  // SKILLS 统计
│  [搜索…] [runtime ▾] [来源 ▾] [时间窗:30天 ▾]
└──────────────────────────────────────────────────────────────
```

### 改动 B:操作员详情 ⑨ 区 —— 左右对调 + 更名 + 默认 7 天(问题 1+3)
```
改前(.dist 50/50:左 skill 宽表 / 右 runtime,默认 30 天):
├─ ⑨ 分布 ────────────────────────────────────────────────────
│   用过哪些 skill(默认 30天降序)      跨 runtime 分布
│   web-search  own   30天 22 →         claude-code ▓▓▓▓▓ 62
│   pdf         …                       codex       ▓▓ 24

改后(.dist-mirror 左窄右宽:左 RUNTIME / 右 使用 Skill 排行,默认 7 天降序):
├─ ⑨ 分布(左窄 ~360px / 右宽,≤1080px 单列)──────────────────
│   跨 runtime 分布          使用 Skill 排行(默认按 7天 降序;整行可点→skill 详情)
│   claude-code ▓▓▓▓▓ 62     skill        来源    7天 30天  runtime分布  最近
│   codex       ▓▓ 24        web-search   own      8   22   ▓▓▓░░       06-16
│   hermes      ▓ 10         pdf          非公司库  5    9   ▓▓░░░       06-15
│   (装备态不计入)           skill-create meta     3    8   ▓░░░░       06-14
└──────────────────────────────────────────────────────────────
```

### 改动 C:两个详情页 ⑩ 最近记录 —— 时间到秒 + 整行交互(问题 4+5)
```
改前(首列只到天;只有标题列可点):
│   日期     skill         runtime       session
│   06-16   web-search    claude-code   abc12345

改后(首列到秒;此表无下钻目标,指针为 default、不可整行点):
│   时间                  skill         runtime       session
│   2026-06-16 14:32:07  web-search    claude-code   abc12345
│   2026-06-16 09:18:55  pdf           codex         def67890
│   (取 first_seen,UTC 墙钟;缺失回退到日期)
```
> 注:可下钻表格(总览技能主表 / 操作员主表 / ⑨ 区使用 Skill 排行)整行可点;
> 表头排序等行内交互 stopPropagation,以局部为准。"最近记录"无跳转目标,保持指针 default。

## 权衡
- **直接切片得 UTC 墙钟,不做本地时区转换**:与现有 `day`(`recv[:10]`,亦 UTC)口径一致,避免
  `new Date()` 解析/时区坑;代价是中国运营看到的是 UTC 时间。若后续要本地时区,只需改 `fmtTs` 一处。
- **整行可点用 onClick+navigate 而非把 `<Link>` 撑满单元格**:跨多列、含右对齐数字列与 `RuntimeBars`,
  撑满链接难处理;onClick 行 + 局部 stopPropagation 更干净,代价是需手动补键盘可达性。
- **"默认 7 天"只在详情页内**:不动总览主表口径,避免与 skills-operator-view 已锁定的"主表默认 30 天"冲突。

## 风险
- 整行可点可能误触发(行内未来新增交互忘记 stopPropagation)→ 在 design 与 spec 写明"局部优先"规则。
- 左窄右宽后宽表在窄屏可能仍需横向滚动 → 沿用 `.skills-wrap` 的 `overflow-x:auto` 兜底。
- 回滚:纯前端,`git revert` 即可,无数据/接口副作用。
