# spec-delta：board（redesign-skills-page）

> 本 delta 描述 SKILLS 总览页从「过滤条 + 堆叠柱 + 排行+漏斗」升级为「KPI 环带 + 治理健康 + 主视图并列 + 归因 Donut + 明细抽屉 + 漏斗下沉」的仪表盘结构。归档时把下面的 **ADDED / MODIFIED / REMOVED** 三节合并回 `openspec/specs/board/spec.md`。

## 接口（MODIFIED）

- `GET /api/skills?w={window}[&wstart=&wend=]&…` → 在现有响应基础上，**可选**新增：
  - `period_comparison`：本期 vs 同长度上一周期的 `sessions / operators / avg_skills_per_session / top3_share / untracked_share`
  - `governance.idle_installed`：装机 30 天内 0 触发的 skill 列表（含 `installed_at`、`installers`）
  - `governance.cataloged_not_installed`：收录但零装机的 skill 列表（含 `cataloged_at`）
  - `attribution.by_source`：按来源（own / meta / external / non_catalog）加权的 sessions 分布
  - `attribution.by_runtime`：按 runtime 加权的 sessions 分布
  - **兼容**：`days` 查询参数保留并 fallback 到 `w`；`win` URL 参数在前端仍被解析，等价于 `w`。
  - **降级**：新增字段可选返回；前端读不到时降级为「—」或隐藏对应 UI 段。

## 前端规则（ADDED）

- SKILLS 总览页采用**八层仪表盘结构**（自上而下）：
  1. **控制条**（视角切换 + 时间窗 + 环比开关 + 搜索 + runtime + 来源 + Top N + 隐藏 0 使用 + 导出）——视角切换从独立 frame 收进这一行
  2. **KPI 环带（8 格）**：总触发次数 / 公司库覆盖率 / 活跃操作员数 / 平均每会话 skill 数 / 未收录使用占比 / 闲置 skill 数 / 装了没用比例 / Top3 集中度
  3. **治理健康条（5 项）**：未收录占比 / 装了没用 / 覆盖率 / Top3 集中度 / 平均 skill/会——每项 good/warn/bad 三色，只做信号不承载点击
  4. **每日堆叠柱（全宽独占一层）**：Top8 + 「其他」堆叠；桌面 100% 内容宽（有效绘图区 1160-1200px）、高度 280px；平板全宽；手机 7d 铺满 / 30d、90d 在 `.chart-box` 内横滚；选中 skill 时该段落加粗描边、其他段落 α=.4；与第 5 层排行 Bar 通过全局 `sel` 联动
  5. **主视图并列**：左（排行 Bar Top N + 长尾聚合 「其他 N 个」）| 右（治理待办 3 组：有使用但未收录 / 装了 W 内没用 / 收录但零装机）
  6. **归因 Donut（2 张）**：按来源占比（双层 Sunburst） / 按 runtime 占比（单层）
  7. **明细表 + 抽屉**：动态列（W 内 / W′ 上期 / Δ%）；点行**打开右侧抽屉**，不再跳页；抽屉有「前往详情页 →」逃逸口
  8. **公司库采纳漏斗**：下沉到页面底部，默认折叠

- **KPI 环带口径**（分子 / 分母 / 环比策略）：
  - 总触发次数 = `sum(sessions in W)`；vs W′ ±%
  - 公司库覆盖率 = `used_own_meta_in_W / total_own_meta_in_catalog`；vs W′ ±%
  - 活跃操作员数 = `distinct operators with ≥1 trigger in W`；vs W′ ±%
  - 平均每会话 skill 数 = `distinct(session, skill) pairs / distinct sessions`；vs W′ ±%
  - 未收录使用占比 = `untracked_used_sessions / total_used_sessions`；vs W′ ±%
  - 闲置 skill 数 = `installed AND ¬used_in_W`（own+meta）；**无 delta（快照）**
  - 装了没用比例 = `闲置 / installed`（own+meta）；**无 delta（快照）**
  - Top3 集中度 CR3 = `Top3_sessions / total_sessions`；vs W′ ±%
  - Delta 计算：`(current - previous) / max(1, previous)`；previous=0 且 current>0 → `+∞%`；两边 0 → `—`

- **治理健康阈值**（可 tune 但不影响设计）：
  - 未收录占比：good <10% / warn 10–25% / bad >25%
  - 装了没用比例：good <20% / warn 20–40% / bad >40%
  - 公司库覆盖率：good >50% / warn 30–50% / bad <30%
  - Top3 集中度：good 30–60% / warn 60–80% 或 <30% / bad >80%
  - 平均 skill/会：good >1.5 / warn 0.8–1.5 / bad <0.8

- **治理待办 3 组**：
  - A. 有使用但未收录：`sessions_in_W > 0 AND source == non_catalog`，按 `sessions_in_W desc` 排序
  - B. 装了 W 内没用：`installed AND sessions_in_W == 0`（own+meta），按 `installed_at desc` 排序
  - C. 收录但零装机：`source ∈ {own, meta} AND installed_count == 0`，按 `cataloged_at asc` 排序
  - 每组 Top 8 + 「查看全部 N」链接；每条右侧「忽略」按钮；组头「恢复已忽略」链接
  - 忽略状态只保存在当前页面会话内，不写后端、不写 localStorage

- **主视图排行 Bar**（左侧下半部）：
  - Top N（默认 8，可选 5/10/20）之外合并成「其他 N 个 skill」一行；点击可展开成 popover 显示完整列表
  - 值口径：`sessions_in_W`；条宽 = value / max；每行右侧显示来源徽章
  - 点行 = 设置全局 sel；再点取消；选中时其他行变灰

- **归因 Donut**：
  - 权重用 `sessions_in_W`（非 skill 数）
  - **按来源** = 双层 Donut（sunburst）：
    - 内环（2 分片）：已收录（own+meta+external 合计） ｜ 未收录（non_catalog）
    - 外环（4 分片，紧贴对应内环父块）：自研 own ｜ 核心 meta ｜ 外部 external ｜ 未收录 non_catalog
    - 「未收录」在外环占的角度 = 内环「未收录」角度（父子 1 对 1，不再细分）
    - 已收录用冷色系（own 蓝 / meta 青 / external 绿），未收录用暖色警戒色（non_catalog 橙红）
    - 中心大字 = Donut 总量；下方小字显示「未收录 X%」（治理红线前置）
    - 父子角度一致性：内环「已收录」= 外环 own+meta+external 之和，容差 <0.5°
    - 交互：点内环「未收录」等价于全局筛选 `src=non_catalog`；点外环细分等价于 `src=<own|meta|external>`；再点取消
  - **按 runtime** = 单层 Donut：分片 claude-code / codex / openclaw / hermes / cursor
  - 无选中 skill：两张 Donut 显示全局分布
  - 有选中 skill：两张 Donut 都切成「该 skill 的 runtime 分布」（skill 只有单一来源，双层 Donut 画不出来源分布）
  - 零值扇区不画（避免 0 角度空隙）

- **明细表 + 抽屉**：
  - 表列：名称 / 来源 / **W 内触发 / W′ 上期 / Δ%** / 用户 / runtime / 趋势 / 最近
  - 点行 → 打开右侧抽屉（桌面 480px 侧滑 / 平板 80% 宽 / 手机全屏）
  - 抽屉内容：KPI4 格（W 触发 / 环比 / 活跃者 / 装机数）+ 趋势 bar（14d/30d/90d 三档切换）+ runtime 拆分 + 使用 Top / 装机 vs 使用差集（差集红标）+ 最近 5 次触发 + 「前往详情页 →」按钮
  - 抽屉复用 `/api/skills/:name`，按当前 W 切片；首次打开加 skeleton，第二次同 skill 走内存 cache
  - CSV 导出：明细表 header 提供「导出当前筛选」「导出全量」两个入口；字段含 skill 名 / 来源 / W 内 / W′ / Δ% / 用户数 / runtime 分布（管道分隔）/ 最近一次触发

- **公司库采纳漏斗（下沉）**：
  - 挪到页面底部，默认**折叠**（`<details>`）；标题栏显示汇总数字：`采集 N · 已装 N · W 用 N · 闲置 N`
  - 展开后规则不变（采集 → 已装 → W 用 → 闲置，四层横条 + 每层展开清单）
  - `catalog.stale` / `catalogUnavailable` 状态显示不变

- **贯穿式选中态**：URL query `sel=<skill_name>` 全局共享；柱图 / 排行 Bar / Donut / 明细表 / 抽屉五处组件从同一 hook 读；点排行 Bar 或明细行 → 设置 sel；再点取消

- **URL query 新增**（写入用 replace，不污染历史）：
  - `w`（`today / this_week / last_week / 7d / 14d / 30d / 90d / custom`）
  - `wstart` / `wend`（`w=custom` 时的起止 unix）
  - `cmp`（`1|0`）环比开关
  - `topn`（`5|8|10|20`）排行 Top N
  - `hz`（`1|0`）隐藏 0 使用
  - `sel`（选中的 skill 名，URL-encoded）
  - `win` 向下兼容：读到 `win` 但没有 `w` → 映射到 `w`
  - `lens` no-op 兼容：读到 `lens=untracked` 不再切换主视图，改由治理待办组 A 呈现

- **响应式**（延续现有 `>1080 / 601–1080 / ≤600` 三档）：
  - 桌面：KPI 环带 8 格一横排；主视图左右并列；Donut 两张并列
  - 平板：KPI 4×2 网格；主视图上下堆叠；Donut 上下堆叠；抽屉 80% 宽
  - 手机：KPI 2×4 网格；主视图三段单列（趋势 → 排行 → 治理待办各 details 折叠）；Donut 缩为胶囊；抽屉全屏；漏斗仍在底部
  - 页面根节点不得横向滚动；只允许 `.chart-box` 内部横滚

- **状态健壮**：
  - 首次加载：只保留控制条 + Skeleton
  - 增量刷新：cnt 显示 loading；旧数据保留 + 半透明（`is-refreshing`）
  - 后端降级：`period_comparison` 缺失 → KPI delta 显示「—」，主值仍在；`attribution.*` 缺失 → 对应 Donut 显示 Empty；`governance.idle_installed` / `cataloged_not_installed` 缺失 → 对应治理组隐藏
  - 新版直接替换原 `/skills` 页面；出问题通过回滚提交或部署上一版镜像恢复，不引入新的 build-time/runtime 开关

## 前端规则（MODIFIED）

- **原「使用排行卡片内部展示管理者筛选 Lens `[全部 Skill] [未收录使用占比 X% · used/total]`」规则**（原 spec 第 86-89 行）——**废弃**：Lens 语义被 KPI 环带（未收录占比一格）+ 治理健康条 + 治理待办组 A 共同替代；URL `lens` 参数保留但不再驱动 UI（no-op）
- **原「排行优先于漏斗，不得在窄屏下把漏斗挤到排行右侧」规则**（原 spec 第 127 行）——**修订**：漏斗不再与排行并列，桌面下漏斗下沉到页面底部；「排行 vs 漏斗」左右布局改为「排行 vs 治理待办」左右布局；「排行优先」精神保留
- **原「柱状图取窗口内使用量前 8 的 skill 分色，其余合并为"其它"段」规则**（原 spec 第 79-80 行）——**扩展**：Top N 可配（5/8/10/20），默认 8；长尾聚合规则同步应用到排行 Bar
- **原「主表固定 7 天/30 天/累计三列，漏斗第 3 层固定 30 天」规则**（原 spec 第 80 行）——**修订**：主表三列从「7 天 / 30 天 / 累计」改为「W 内 / W′ 上期 / Δ%」，跟随当前时间窗动态；漏斗第 3 层同样跟随 W，「30d 固定」语义废止
- **原「视角切换须呈现为页面顶部的独立标准 frame 卡片」规则**（原 spec 第 84-85 行）——**修订**：视角切换收进控制条这一行，不再独立 frame；「32px 高分段按钮，选中态用 `--brand`」样式约束保留
- **原「整行可点跳转到对应详情」规则**（原 spec 第 109-111 行）——**修订**：Skill 主榜整行点击**默认打开右侧抽屉**，不再跳页；「前往详情页」作为抽屉内的显式按钮保留跳转路径；键盘可达（Enter/Space）行为不变——Enter/Space 触发抽屉，长按或 `Ctrl+Enter` 触发跳页（键盘等价语义待前端确认）；操作员主榜行为保持不变（仍跳 `/operator/:name`）
