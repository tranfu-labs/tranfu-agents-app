# 设计：redesign-skills-page

本文件只谈**产品口径与实现权衡**。字符图见 `wireframes.md`，任务拆解见 `tasks.md`，spec 增删改见 `spec-delta/board/spec.md`。

## 一、页面结构总览

从上到下 8 层。第 1-2 层是控制/结论层，第 3-6 层是切片层，第 7-8 层是明细/全景层。

| 层 | 组件 | 主要职责 |
|---|---|---|
| ① 控制条 | `SkillsToolbar` | 视角切换（skill/人）+ 时间窗 + 环比开关 + 分片器 + Top N + 隐藏 0 使用 |
| ② KPI 环带 | `KpiStrip`（8 格） | 一屏结论：使用量 / 覆盖 / 活跃 / 治理 / 集中度 |
| ③ 治理健康条 | `HealthBar`（5 项） | 每项 good/warn/bad 三色，替代原单 Lens |
| ④ **每日堆叠柱（全宽独占一层）** | `DailyStackedChart` | 时间序列主图；Top8 + 「其他」分色；选中 skill 加粗描边、其他 α=.4 |
| ⑤ 主视图并列 | `MainSplit`（左排行 Bar、右治理待办） | 左：Top N + 「其他 N 个」聚合的排行 Bar；右：3 组待办列表 |
| ⑥ 归因 Donut | `AttributionDonuts`（2 张） | 按来源双层 sunburst / 按 runtime 单层 |
| ⑦ 明细表 + 抽屉 | `SkillsDetailTable` + `SkillDrawer` | 点行开抽屉、不跳页；有逃逸口 |
| ⑧ 漏斗（下沉、可折叠） | `FunnelSection` | 全景快照，默认折叠 |

**为什么把每日堆叠柱抬到独占一层**：它是这个页面唯一的时间序列图、也是信息密度最高的图；30d/90d 窗口下若挤在半列会挤到看不清（半列约 700-800px，90 根柱每根 ~8px）。对齐 Token Usage 页「KPI → 健康 → 排行+风险并列 → **趋势独占** → Donut → 明细」的层次感。

**排行 Bar 和每日柱分层的额外好处**：两者本是不同的阅读节奏——柱看时间、Bar 看排名——分层后用户不会不知道先看哪个；选中 skill 时两者仍通过全局 `sel` 状态联动（柱加粗、Bar 高亮）。

**「按人」视角**下：② KPI 换算成人相关（活跃人数、平均每人 skill 数……）；③ 健康条部分失效项隐藏；④ 每日柱分段改为按 operator；⑤ 右侧治理换成「重度使用者 / 沉睡使用者 / 新入职首次使用者」三组；⑦ 明细表切成 `OperatorTable`；⑥⑧ 结构不变，语义不同。

---

## 二、KPI 环带（8 格）· 具体统计口径

**通用约定**：
- 时间窗 W = 用户选中的窗口（今日/本周/上周/7d/14d/30d/90d/自选）。默认 30d。
- 对比周期 W′ = W 之前紧邻的同长度窗口（30d → 上一个 30d；本周 → 上周）。
- 「本期 vs 上期 ±%」= `(current - previous) / max(1, previous)`；分母为 0 且分子 > 0 → 显示 `+∞%`；两边都 0 → 显示 `—`。
- **静态快照类**指标（如 catalog 数、installed 数、闲置数）**不显示 delta**——它们只有「当下值」，比较没有产品意义。

| # | 卡片 | 分子 / 分母 | 数据源 | 环比 |
|---|---|---|---|---|
| 1 | **总触发次数** | `sum(sessions in W)`（skill 触发的会话次数总和，一个会话触发 N 个 skill 算 N 次） | `skill_uses` 按 W 聚合 | vs W′ ±% |
| 2 | **公司库覆盖率** | 分子：W 内被触发过至少 1 次的 own+meta skill 数；分母：catalog 里 own+meta 总数 | `funnel.used_30d ∩ catalog.own_meta` / `catalog.own_meta` | vs W′ ±%（分子随 W 变） |
| 3 | **活跃操作员数** | `distinct operators with ≥1 skill trigger in W` | `skill_uses` distinct operator | vs W′ ±% |
| 4 | **平均每会话 skill 数** | `sum(session-skill pairs in W) / distinct sessions in W`；「session-skill pair」按 `(session_id, skill_name)` 去重后计数 | `skill_uses` | vs W′ ±% |
| 5 | **未收录使用占比** | 分子：W 内未收录 skill 的触发会话数；分母：W 内所有 skill 触发会话总数 | `governance.untracked_usage.used_sessions / total_sessions` 按 W 重算 | vs W′ ±% |
| 6 | **闲置 skill 数** | 已装但 W 内 0 触发的 skill 数（own+meta） | `installed ∩ ¬used_in_W` | **无 delta**（快照） |
| 7 | **装了没用比例** | `闲置 / installed`（own+meta） | 同上 | **无 delta**（快照） |
| 8 | **Top3 集中度 CR3** | Top3 skill 的触发次数之和 / 总触发次数 | `sort(sessions desc)[:3].sum / total` | vs W′ ±% |

**卡片视觉**：
- 主值大字（`.v`）；下方 `.delta`（up/down 着色 + 箭头）；再下方 `.l` 标签。
- 无 delta 的卡片（6、7）用「快照」灰色小字替代 delta 位置，避免视觉空缺不平衡。

**为什么选这 8 项**：涵盖 3 类判断——**用量趋势**（1、8）、**覆盖健康**（2、5、6、7）、**用户参与**（3、4）。Top Usage 页对应的是「成本 / 健康 / 风险 / 规模」，Skills 这里对应「用量 / 覆盖 / 参与 / 集中」——语义映射清晰。

---

## 三、治理健康条（5 项）· 阈值与颜色

每项一颗指示灯（good=绿 / warn=黄 / bad=红）+ 当前值 + 一句解释。

| # | 指标 | 计算 | good | warn | bad |
|---|---|---|---|---|---|
| 1 | 未收录使用占比 | KPI #5 | <10% | 10–25% | >25% |
| 2 | 装了没用比例 | KPI #7 | <20% | 20–40% | >40% |
| 3 | 公司库覆盖率 | KPI #2 | >50% | 30–50% | <30% |
| 4 | Top3 集中度 | KPI #8 | 30–60% | 60–80% 或 <30% | >80% |
| 5 | 平均每会话 skill 数 | KPI #4 | >1.5 | 0.8–1.5 | <0.8 |

**说明**：
- 阈值不是硬科学，是「运营看到红灯会想动手」的经验值。可在 `spec.md` 里以常量出现，允许后续 tune 而不改设计。
- 集中度低 <30% 也算 warn——太分散意味着没有形成「共识 skill」，反而反常。
- 健康条不承担点击/下钻，仅做「红黄绿」信号。想深挖的用户会去看 KPI 环带或治理待办。

---

## 四、治理待办（右侧 3 组）· 排序与聚合口径

替代原 `Funnel` 在右侧的位置。3 组独立列表，每组 Top 8 + 「查看全部 N」链接。

| 组 | 定义 | 排序 | 数据源 | 交互 |
|---|---|---|---|---|
| **A. 有使用但未收录** | `sessions_in_W > 0 AND source == non_catalog` | `sessions_in_W desc` | `governance.untracked_usage.top`（后端已算） | 点行 → 打开抽屉（含「起草纳入 PR」按钮跳到 tranfu-skills 仓库 issue 模板） |
| **B. 装了 W 内没用** | `installed AND sessions_in_W == 0`（own+meta） | `installed_at desc`（越新装越显眼——装了才刚没用是常态；装了 3 个月还没用才是问题）| `funnel.idle` + 装机时间戳 | 点行 → 打开抽屉；显示装机操作员列表 |
| **C. 收录但零装机** | `source ∈ {own, meta} AND installed_count == 0` | `catalog_at asc`（越早收录越显眼）| `catalog.own_meta - installed` | 点行 → 打开抽屉；显示收录时间 + 内容概览 |

**严重度着色**：A 组默认 warn，触发量 top 3 升 bad；B 组闲置 >30d 升 warn，>90d 升 bad；C 组收录 >30d 未装升 warn，>90d 升 bad。

**可忽略 + 可恢复**：仿 Token Usage 风险列表——每条待办右侧「忽略」按钮，忽略后从视图消失；组头有「恢复已忽略」链接。忽略状态只保存在当前页面会话内，不写后端、不写 localStorage；这是 ADR-0023 对前端持久化边界的硬约束，刷新后恢复完整待办列表。

---

## 五、每日堆叠柱（第 ④ 层）· 全宽独占

### 5.1 结构
- 沿用现有 `StackedSkillChart`（Top8 + 「其他」堆叠柱），提升到独占一层、全宽铺满。
- 宽度：桌面 100% 内容宽（1160-1200px 有效绘图区），平板 100% 内容宽，手机 7d 铺满 / 30d、90d 在 `.chart-box` 内横滚。
- 高度：桌面 280px（比 Token Usage 的趋势线 300px 略矮，因为柱状比线图更容易读）。

### 5.2 交互
- 悬停某日列：该列加高亮、其余列 α=.4，弹出锚定浮窗（日期 + 当天各 skill 降序 + 「其他」+ 合计）——沿用现有规则。
- **选中 skill** 时：该 skill 的堆叠段加粗描边、其他 skill 的堆叠段 α=.4——跟 Token Usage 趋势线选中态一致。
- 全空时显示 Empty，不画空轴。

### 5.3 未做（Phase 2）
- 「柱 / 折线」切换开关：MVP 先保留堆叠柱；折线视图留到 Phase 2 视情再做。

## 六、主视图并列（第 ⑤ 层）· 排行 Bar + 治理待办

### 6.1 排行 Bar（左半列，替代旧方案里的重排行表位置）
现有的 `SkillsTable` 太重（9 列），不适合放在主视图黄金位。抽出一个轻量排行 Bar 组件：

```
Skill A ████████████████████████████████ 1,234 次  [源徽章]
Skill B ██████████████████████░░░░░░░░░░ 856 次   [源徽章]
...
其他 42 个 skill ████░░░░░░░░░░░░░░░░░░ 312 次   ▸ 展开
```

- Top N（默认 8，可选 5/10/20）之外合并成「其他 N 个 skill」一行，点击可展开成 popover 显示完整列表。
- 点行 = 设置全局选中态 `sel`；再点一次取消选中；选中时其他行变灰。
- 值口径：`sessions_in_W`；条宽 = value / max。
- 每行右侧的「源徽章」= own/meta/external/non_catalog 四色小圆点（跟明细表来源列一致）。
- **与第 ④ 层每日柱通过 `sel` 联动**：点 Bar 选中时，柱状图对应段落加粗描边。

### 6.2 治理待办（右半列）
见 §四（三组：A 有使用但未收录 / B 装了 W 内没用 / C 收录但零装机）。放在这一层的右半列，与排行 Bar 视觉并列。

### 6.3 平板 / 手机布局
- 平板：左右并列改为上下堆叠（排行 Bar 上、治理待办下），跟现有响应式规则一致。
- 手机：单列，排行 Bar → 治理待办 3 组各自 `<details>` 折叠。

明细表下沉到第 ⑦ 层，作为「排行 Bar 的完整视图 + 抽屉入口」。

---

## 七、归因 Donut（2 张）· 加权口径

替换掉原本没有的归因维度。仿 Token Usage 的类型/模型 Donut，但**「按来源」用双层 Donut（sunburst）** 表达父子关系。

### 7.1 按来源占比（双层 Donut）

**为什么双层**：来源在业务里天然是两级——「是不是已收录进公司库」是治理关心的第一问，「已收录里是自研 / 核心 / 外部哪一类」是第二问。单层 Donut 把这 4 类平铺，运营看不出「未收录占比」这条最重要的红线；双层则内环一眼给出 own+meta+external 合计 vs non_catalog 的对比，外环再展开细分。

**结构**：
- **内环（父类，2 分片）**：已收录（own+meta+external 合计）｜ 未收录（non_catalog）
- **外环（子类，4 分片，紧贴内环对应父块）**：自研 own ｜ 核心 meta ｜ 外部 external ｜ 未收录 non_catalog
  - 「未收录」在外环占的角度 = 内环「未收录」的角度（父子 1 对 1，不再细分）
  - 「已收录」的父角度 = own / meta / external 三个子块角度之和

**加权**：都用 `sessions_in_W`（触发量加权，非 skill 数）。

**着色语系**：
- 已收录用**冷色系**渐变：own 蓝 → meta 青 → external 绿
- 未收录用**暖色警戒色**：non_catalog 橙红（跟治理待办 A 组视觉呼应）
- 内外环同一父类用同色相不同明度：内环稍暗做「底座」感，外环稍亮做「细分」感

**中心大字**：Donut 总量（触发次数）；下方一行小字显示「未收录 X%」——**最重要的治理数字前置到中心**。

**交互（加分项，非 MVP 必须）**：
- 点内环「未收录」扇区 → 等价于全局筛选 `src=non_catalog`
- 点外环某个细分（如 own）→ 等价于 `src=own`
- 再点一次取消筛选；跟当前来源下拉筛选联动

**选中 skill 时的行为**（跟 6.2 一致）：切换成「该 skill 的 runtime 分布」——skill 只有单一来源，双层 Donut 画不出来。

### 7.2 按 runtime 占比（单层 Donut）

不变：
- 分片：claude-code / codex / openclaw / hermes / cursor
- 权重：`sessions_in_W`
- 无选中 skill：显示全局
- 有选中 skill：显示「该 skill 的 runtime 分布」
- 中心大字 = 该 Donut 总量

### 7.3 通用约定

- **六色以上处理**：runtime 目前 5 种、来源 4 种（其中双层结构本身消化了「多类」问题），都不用 Top N 聚合
- **零值扇区**：某分片 sessions=0 时不画（避免 0 角度扇区留出色条空隙）
- **父子一致性检查**：内环「已收录」角度 = 外环 own+meta+external 三块之和，误差 <0.5° 视为一致（浮点round-off 容忍）

---

## 八、明细表 + 抽屉

### 8.1 明细表
- 列基本保留当前 `SkillsTable`（名称、来源、7d、30d、总、用户、runtime、趋势、最近），但：
  - **7d / 30d / 总 三列换成基于当前时间窗 W 的动态列**：`W 内`、`W′ 上期`、`Δ%`——三列联动时间窗，比死列更贴仪表盘思路。
  - 「总触发数」（不受 W 影响）挪到抽屉里，明细表不放。
- 点行**打开右侧抽屉**（现在是跳页）；抽屉右上角保留「前往详情页 →」按钮做逃逸口。
- 表头排序仍支持；排序不影响选中态。

### 8.2 抽屉内容
复用 `/api/skills/:name` 数据集，按当前 W 切片：

```
┌─ Skill 名称 ─────────────────────────  [来源徽章] [× 关闭]
│ [前往详情页 →]
├──────────────────────────────────────
│ KPI 卡（4 格）
│   本期触发 / 环比 / 活跃操作员 / 装机数
├──────────────────────────────────────
│ 趋势 bar（14d / 30d / 90d 切换）
├──────────────────────────────────────
│ runtime 拆分（横向堆叠柱）
├──────────────────────────────────────
│ 使用操作员 Top（表）
│ 装机操作员 vs 使用操作员对比（差集显红）
├──────────────────────────────────────
│ 最近 5 次触发（session_id · operator · runtime · time）
└──────────────────────────────────────
```

### 8.3 CSV 导出
沿用 Token Usage 的 `exportTokenRows` 模式，在明细表 header 加：
- 「导出 CSV（当前筛选）」
- 「导出 CSV（全量）」

字段：skill 名 / 来源 / W 内触发 / W′ 触发 / Δ% / 用户数 / runtime 分布（管道分隔）/ 最近一次触发。

---

## 九、URL query 参数（选中态贯穿）

现有：`view / q / rt / src / win / sort / dir / lens`。
新增：
- `w`（时间窗名，替代 `win`；`win` 保留兼容并 fallback 到 `w`）——支持 `today / this_week / last_week / 7d / 14d / 30d / 90d / custom`
- `wstart / wend`（`w=custom` 时的自选起止 unix 时间戳）
- `cmp`（`1|0`）是否显示环比
- `topn`（`5|8|10|20`）排行 Top N
- `hz`（`1|0`）隐藏 0 使用
- `sel`（选中的 skill 名，URL-encoded）——**新增，五组件共享**

变更时 URL 立即写入；刷新页面保留完整状态。原来的 `lens`（治理 Lens 单开关）语义废弃，被 KPI 环带 + 健康条 + 治理待办替代——URL 里保留 `lens` 参数但不再驱动 UI（做 no-op 兼容）。

---

## 十、后端聚合字段增补（`/api/skills` 响应）

现有响应包含 `daily / operator_daily / table / operator_table / funnel / catalog / governance.untracked_usage`。

新增（可选返回，前端读到就用、读不到降级为「—」）：

```jsonc
{
  "period_comparison": {
    "window": "30d",
    "previous_window_start": 1720000000,
    "previous_window_end": 1722592000,
    "current_sessions": 12345,
    "previous_sessions": 10234,
    "current_operators": 42,
    "previous_operators": 38,
    "current_avg_skills_per_session": 1.7,
    "previous_avg_skills_per_session": 1.4,
    "current_top3_share": 0.58,
    "previous_top3_share": 0.61,
    "current_untracked_share": 0.28,
    "previous_untracked_share": 0.31
  },
  "governance": {
    "untracked_usage": { /* 现有 */ },
    "idle_installed": {
      "count": 14,
      "top": [ { "name": "...", "installed_at": 1720000000, "installers": 3 } ]
    },
    "cataloged_not_installed": {
      "count": 8,
      "top": [ { "name": "...", "cataloged_at": 1710000000 } ]
    }
  },
  "attribution": {
    "by_source": [
      { "source": "own",         "sessions": 6234 },
      { "source": "meta",        "sessions": 3120 },
      { "source": "external",    "sessions": 890 },
      { "source": "non_catalog", "sessions": 2101 }
    ],
    "by_runtime": [
      { "runtime": "claude-code", "sessions": 8123 },
      { "runtime": "codex",       "sessions": 2456 },
      { "runtime": "openclaw",    "sessions": 987 },
      { "runtime": "hermes",      "sessions": 612 },
      { "runtime": "cursor",      "sessions": 167 }
    ]
  }
}
```

前端算 KPI 5-8 是可以基于现有字段本地算的（省一趟接口），但 1-4 需要后端提供上一周期基线；不然 delta 只能显示「—」。

## 十一、权衡

| 决策 | 方案 A（选用） | 方案 B（未选）| 为什么选 A |
|---|---|---|---|
| 抽屉 vs 跳页 | 点行开右侧抽屉，保留「前往详情页」 | 保持现有跳页 | 抽屉支持横向对比多个 skill，跳页不支持；跳页仍作逃逸口不损失能力 |
| 治理放右侧 vs 保留漏斗 | 治理待办 3 组放右侧，漏斗下沉底部 | 保持漏斗在右侧 | 漏斗是低频看的静态快照；治理待办是「今天该动的事」，配得上黄金位 |
| 每日柱独占一层 vs 与排行 Bar 共占半列 | 每日柱全宽独占第 ④ 层 | 每日柱与排行 Bar 共占左半列 | 每日柱是页面唯一时间序列图；半列 700-800px 装不下 90d 每根柱（~8px）；分层后柱看时间、Bar 看排名，阅读节奏不冲突；两者仍通过 `sel` 联动 |
| KPI 显示环比 | 强制显示（除快照类）| 环比作为开关默认关 | 「本期 vs 上期」是运营看数字的第一反应，默认可见符合仪表盘直觉 |
| 长尾聚合位置 | 前端算 | 后端算 | 后端已返回排序好的 top，前端合并简单；不用为此加接口版本 |
| 选中态存 URL | URL query `sel` | 组件内 state | 存 URL 才能刷新保留、才能分享给同事「看这个 skill 的状况」|
| 时间窗名 `w` 覆盖 `win` | 新参数 `w`，`win` 兼容 fallback | 直接换 | 已有分享的旧 URL 里用的是 `win`；平滑过渡 |
| 治理忽略状态 | 当前页面会话态 | localStorage 或后端存储 | 治理判断是运营个人视角，但 ADR-0023 禁止新增业务 localStorage key；后端存又会互相干扰，所以只做本页临时忽略 |

## 十二、风险 & 回滚

- **风险 1：后端 `period_comparison` 未上线，前端 KPI delta 全「—」**——前端做完整降级：读不到就隐藏 delta 行，不留空白，主值仍显示。
- **风险 2：抽屉复用 `/api/skills/:name` 但接口耗时较高**——首次打开加 skeleton，第二次同 skill 走内存 cache（组件 state），不重复请求。
- **风险 3：治理阈值定得不合适，红灯常亮或永远绿灯**——阈值以常量集中在一个文件（例如 `frontend/src/lib/skillsThresholds.ts`），tune 不改设计。
- **回滚**：新页面直接替换原 `/skills` 实现；出问题通过回滚分支提交或部署上一版镜像恢复，不增加新的 build-time/runtime 开关。
