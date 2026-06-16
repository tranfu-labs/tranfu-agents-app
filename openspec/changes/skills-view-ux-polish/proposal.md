# 变更提案:skills-view-ux-polish(SKILLS 视图交互与布局打磨)

- 状态:Proposed
- 关联:skills-operator-view(前身:按人视角 / 双向下钻已落地)、skills-stats-page(SKILLS 总览/详情骨架)

## 背景 / 问题
skills-operator-view 上线后,试用中发现一批交互与布局细节不到位,影响"运营一眼看懂、随手点开"的体验:

1. **操作员详情 ⑨ 区主次颠倒**:当前左边放"用过哪些 Skill"宽表、右边放 RUNTIME 分布。
   运营进单人页第一眼想先看"这人主要在哪个 runtime",skill 明细是其次,左右主次反了。
2. **视角切换太轻**:`[ 按 skill ] / [ 按人 ]` 和筛选条挤在同一个卡片里,分量轻、不显眼,
   而它其实是"整页换主语"的主操作,地位被低估。
3. **"用过哪些 Skill"语义偏弱**:它本质是一张排行,且运营更关心近期(最新 7 天)谁在被用,
   当前命名与默认排序都没体现"排行 + 近期"。
4. **最近记录只到天**:操作员详情与 skill 详情的"最近记录"首列只显示 UTC 日期,
   排查"同一天内谁先谁后"时分辨不出,而 `skill_uses.first_seen` 本就有到秒的时间戳。
5. **表格只有标题可点**:多张可下钻表格整行是 `cursor:pointer`(看起来整行可点),
   实际只有标题列的 `<Link>` 能跳转,点行内其它位置无反应,交互预期与实现不一致。

## 目标(经访谈逐项拍板,口径见 design.md)
- 操作员详情 ⑨ 区改为**左 RUNTIME 分布(窄)/ 右 Skill 排行(宽)**,左窄右宽。
- Skill 明细更名为**「使用 Skill 排行」**,**默认按最近 7 天使用次数降序**;保留 7天/30天列。
- /skills 顶部把视角切换抽成**独立标准 frame 卡片**:标题栏左侧「视角」、右侧 `cnt` 说明,
  内容行放 32px 高分段按钮;筛选条留原卡。
- 操作员详情与 skill 详情的"最近记录"首列改为显示到秒(`first_seen`,UTC 墙钟)。
- 所有可下钻表格**整行可点**;局部存在自身交互时(如表头排序)以局部交互为准(阻止冒泡)。

## 非目标
- 不动后端 `server/app.py` 与任何接口契约(`first_seen` 已在 `records` 返回,数据已就绪)。
- 不改按人/按 skill 既有口径(去重计量、only used、空 operator 排除、漏斗常驻、双向下钻)。
- 不改总览页两张主表(SkillsTable / OperatorTable)的列与默认排序口径(仍默认 30 天);
  "默认 7 天"仅作用于**操作员详情页内**的 skill 排行。
- 不给"最近记录"表加跳转(无明确目标),仅修正其指针态。

## 方案概述(详见 design.md)
纯前端改动,集中在 4 个文件 + 一段 CSS:
- [OperatorDetail.tsx](../../../frontend/src/views/OperatorDetail.tsx):⑨ 区左右对调 + 新增左窄右宽布局类;
  skill 表更名、组件内按 7 天降序重排。
- [Skills.tsx](../../../frontend/src/views/Skills.tsx):`ViewSwitch` 抽成独立 frame 卡片,标题栏 `cnt` 放说明文案,
  内容行放 32px 高品牌色分段按钮;
  四张可下钻表(此处含 SkillsTable / OperatorTable)整行 `useNavigate` 跳转、表头排序 `stopPropagation`。
- [SkillDetail.tsx](../../../frontend/src/views/SkillDetail.tsx):最近记录首列改 `first_seen` 到秒。
- [utils.ts](../../../frontend/src/lib/utils.ts):新增 `fmtTs(iso)` 时间到秒格式化。
- [styles.css](../../../frontend/src/styles.css):新增 `.dist-mirror`(左窄右宽)、`.viewcard` / `.viewbody .seg`、
  修正 `.skills-wrap tbody tr` 与"最近记录"表的指针态。

## 影响
- specs/board:补充操作员详情 skill 排行默认窗口、最近记录时间精度、整行可点、视角卡片等可验证行为。
- 仅前端;不触碰 ingest / 读侧接口契约,向后兼容。
