# 规格:board(看板与计算域)

事实来源:`server/app.py`(`/api/state`、`metrics`、`leverage`、`reuse_map`、`_snapshot`)与 `frontend/` React 看板。

## 接口
- `GET /api/state` → `{ now, sessions[], feed[], leverage, skills[], shim, totals }`。
- `GET /api/skills?days={7|30|90}` → `{ today, daily[], table[], operator_daily[], operator_table[], funnel, catalog }`(SKILLS 总览;`today` 为 UTC 当日,`days` 仅影响 daily/operator_daily,默认 30)。
- `GET /api/skill/{name}` → 单 skill 详情(含 `today`、指标、used/equipped 分列日级序列、runtime/operator 分布、最近记录、来源);查无此名 → 404。
- `GET /api/operator/{name}` → 单操作员详情(含 `today`、used-only 指标、按 skill 分段日级序列、skill 排行、runtime 分布、最近记录);查无 used 记录 → 404。
- `GET /api/agent/{key}`(key = `operator::agentOrRuntime`)→ 单 agent 详情(可选)。
- `GET /`、`/agents`、`/agent/{key}`、`/skills`、`/skill/{name}`、`/operator/{name}` → React 看板 SPA;
  `GET /assets/*` → Vite 指纹化静态资源;`GET /healthz` → `ok`。

## 规则(MUST)
1. **卡片按身份合并**:每个 `(operator, agent‖runtime)` 只输出**一张**卡,保留 `last_seen` 最新的 session(见 ADR-0006)。
2. 每张卡合并:计算所得活跃(today/week/series7/`active_days`[90])、质量(runs/success/error/avg_sec/auto_rate)、
   复用(跨人技能重叠),以及该身份最新 profile 字段。
3. **掉线判定**:`running/started` 且距 `last_seen` 超过 `STALE_SECONDS=180` 秒 → 展示为 `idle`。
4. 活跃统计窗口 `WINDOW_DAYS=90`,按 UTC 日;跨天会话按当天边界拆分。
5. `totals.live` 仅计 `status ∈ {running, started, waiting}`。
6. `feed` 为真实状态转变(非心跳),倒序。
7. leverage = `{assets: 不同技能数, skills_week: 近 7 天首次出现的技能数}`。
8. `skills` 为 Skill 使用/装备排行数组,每项含 `name`、`mode`(`used`/`equipped`)、`sessions_7d`、`sessions_30d`、
   `sessions_total`、`users_30d`、`last_day`;按 `sessions_30d` 降序,平手按 `sessions_total`。
9. Skill 计数口径:一个会话用过/装备某 skill 的某个 mode 算一次(来源即 `skill_uses` 的会话×skill×mode 粒度,
   读侧不再去重);时间窗口按 UTC 日切,与活跃统计口径一致。`used` 与 `equipped` 必须分条呈现,不得相加。
10. `shim.version` 为服务端当前分发的 shim 内容版本;看板用它与每张卡的 `shim_version` 比较,缺失或不一致时显示旧版提示。
11. SKILLS 为第三个顶级视图(看板 / Agents / SKILLS),含总览与单 skill 详情(独立视图 + 返回)两级。
12. `/api/skills` 总览页所有聚合(`daily`、`table`)只统计 `mode=used`;`equipped` 仅在 `/api/skill/{name}`
    详情页展示,并与 used 分列,任何位置不得相加。
13. `/api/skills.table` 每行含来源字段,取值 own / meta / external / 非公司库;来源由服务端 catalog 缓存按名字映射。
14. `/api/skills.funnel` 只统计 catalog 中 `type ∈ {own, meta}` 的 skill,三层为 catalog 收录名单、
    已安装名单(出现在 ≥1 个 agent 的 profiles 安装态快照)、30 天有人使用名单(UTC 日切);
    并返回闲置名单 = 已安装 − 30 天使用。三层均返回名单而非仅数字。
15. catalog 由服务端定时拉取并缓存;拉取失败时 `/api/skills` 仍须 200,funnel 携带旧缓存与过期标记;
    从未成功拉取时 funnel 为"目录不可达"态,其余字段正常。
16. `/api/skills.operator_table` 与 `operator_daily` 只统计 `mode=used`,且排除空 `operator`;人维度计量单位是
    会话×skill 去重使用次数(一行 `skill_uses` used 记录),语义为"此人在多少个会话里用过 skill",非真实调用次数。
    `operator_table` 固定输出 7 天 / 30 天 / 累计、用过 skill 数、会话数、runtime 计数、来源计数、近 14 天趋势和最近使用日;
    默认按 30 天降序,平手按累计。`days` 只影响 `operator_daily`,不影响 `operator_table`。
17. `/api/operator/{name}` 只统计该操作员的 `mode=used` 记录,不输出 equipped 指标;返回指标、按 skill 分段日级序列、
    skill 排行(含来源)、runtime 分布和最近 50 条记录。

## 前端规则(MUST)
- 轮询 `/api/state`(约 3s),取不到时退回内置演示数据并显示"未连接服务端"。
- 视图:Pods 看板(按 operator 分组,人=调度员,其 agent=编队)/ Agents 列表 / SKILLS 总览 / 治理详情 / Skill 详情 / Operator 详情。
- 路由:Pods 看板 `/`;Agents 列表 `/agents`;治理详情 `/agent/:key`;SKILLS 总览 `/skills`;
  Skill 详情 `/skill/:name`;Operator 详情 `/operator/:name`;刷新、前进后退、复制链接必须保持当前视图。
- SKILLS 总览筛选绑定到 URL search params:`win`(7/30/90)、`rt`、`src`、`q`、`sort`、`dir`、`view`(`skill`/`operator`);
  筛选变化使用 replace,不污染浏览器历史;详情跳转使用 push。
- Pods 看板不再展示 Skills 排行区;`/api/state.skills` 字段保留用于协议兼容,前端看板不消费。
- SKILLS 总览进入时加载 `/api/skills`,之后低频刷新;加载失败显示错误态。柱状图横轴按所选 UTC 日窗口逐日铺满:
  右端取服务端 `today`,左端为 `today-(N-1)`,N ∈ {7,30,90};每一天占一个槽位,有 used 数据才长堆叠柱,
  无数据留空槽。前端取窗口内使用量前 8 的 skill 分色,其余合并为"其它"段;时间窗筛选只作用于柱状图,
  主表固定 7 天/30 天/累计三列,漏斗第 3 层固定 30 天;窗口选择器不含"全部"档。
- SKILLS 总览提供按 skill / 按人视角切换。切换后柱状图、主表、行级下钻必须整页同一主语:
  skill 视角按 skill 分段并下钻 `/skill/:name`;按人视角按 operator 分段并下钻 `/operator/:name`。
  筛选条复用同一套 query,搜索框提示语随视角变;切换视角不重置 `win`。公司库漏斗常驻且始终使用 skill/catalog 口径。
  视角切换须呈现为页面顶部的独立标准 `frame` 卡片,与筛选条分离;标题栏左侧为"视角"、右侧 `cnt`
  随当前视角给出说明文案,内容行使用 32px 高分段按钮,选中态使用品牌色 `--brand`。
- SKILLS 柱状图悬停某日列时,该列高亮、其余列降透明,并显示锚定柱子的明细浮窗(日期、当天各 skill 降序明细、
  Top8 外并"其它"、合计);浮窗锚定柱子几何而非光标——默认贴柱子右侧、顶部对齐图表绘图区顶,
  碰视口右边界翻到柱子左侧、碰下边界上移贴视口底。今日列作为最后一格,以进行中视觉区分并在浮窗标注。
  移动端点击列显示浮窗,点击别处或横向滚动图表时关闭。整窗全空或筛选后全空时显示空态,不渲染一排空轴。
- Skill 详情趋势图固定最近 30 个 UTC 日逐日铺满(右端同服务端 `today`),used 柱与 equipped 折线分列展示,
  不相加;空天留白,今日列进行中,悬停/点击浮窗显示 used/equipped,且使用与 SKILLS 总览一致的柱子锚定、
  视口翻转和点击别处关闭规则。
- 单操作员详情的 skill 排行在界面上呈现为「使用 Skill 排行」,默认按最近 7 天使用次数降序(平手按累计、再按名称);
  此默认仅作用于操作员详情页内,不改变 SKILLS 总览页两张主表"默认 30 天降序"的既有口径。
  操作员详情的 runtime 分布与 skill 排行采用左窄(runtime)/右宽(skill 排行)布局,窄屏(≤1080px)降级为单列。
- 操作员详情与单 skill 详情的"最近记录"列表,时间列须显示到秒级(取 `first_seen`,UTC 墙钟,
  格式 `YYYY-MM-DD HH:MM:SS`);`first_seen` 缺失时回退到 UTC 日期。
- 所有具有下钻目标的表格(总览技能主表、总览操作员主表、操作员详情的使用 Skill 排行)须整行可点,
  并跳转到对应详情;且须键盘可达(Enter / Space 触发)。整行可点与局部交互冲突时以局部交互为准,
  局部交互元素须阻止冒泡,不触发整行跳转。无下钻目标的表格(如"最近记录")不得呈现为整行可点。
- 详情数据优先取 session 的服务端字段(`cf/skills/mcp/integrations/about/...`);演示映射仅用于独立预览。
- 卡片/详情显示本机上报的 `shim_version` 短码;落后于服务端 `shim.version` 时标记过期。
- 暗/亮双主题;手机窄屏(≤600px)头部分行、表格横向滚动、详情单栏。
- 不得使用浏览器本地存储;不得写死后端端口(同源相对路径)。
- 前端源码在 `frontend/`;生产由 Docker/CI 构建 `frontend/dist`,运行容器不依赖 node,仓库不提交 dist。

## 可验证行为
- 同一 agent 跑多次/多 session → 看板仅一张卡,随最新状态刷新。
- 某 agent 3 分钟无心跳 → 卡片转 `idle`(灰)。
- 造数据:skill A 的 `used` 在 31 天前 1 个会话、5 天前 2 个会话(2 个不同 operator)使用 →
  `mode=used` 条目 `sessions_7d=2`、`sessions_30d=2`、`sessions_total=3`、`users_30d=2`。
- 同一 skill A 同时有 `used` 与 `equipped` → `skills` 出现两条同名不同 mode 条目,计数互不相加。
- 空库 → `skills: []`,看板显示空态。
- 服务端 `shim.version` 与某 agent 的 `shim_version` 不一致或缺失 → 看板显示旧版角标。
- 同名 skill 同时有 `used` 与 `equipped` → `/api/skills` 的 table 与 daily 只含 used;
  `/api/skill/{name}` 两种模式并列展示且任何字段不相加。
- 造安装态:某 own skill 装于 ≥1 个 agent 且 30 天零使用 → funnel 闲置名单含之。
- catalog 拉取失败 → `/api/skills` 返回 200,funnel 带过期标记与旧名单。
- `days=7` → daily 仅含最近 7 个 UTC 日;`days` 变化不影响 table 与 funnel;`days=0` 返回 400。
- `/api/skills` 与 `/api/skill/{name}` 均返回 UTC `today`;前端以它作为时间轴右端,不得用浏览器本地日期推算。
- 只有今天有 used → 主图 7/30/90 日槽位完整铺开,仅最后一槽有今日进行中柱;中间缺数据的日期保留空槽。
- 悬停某柱 → 浮窗锚定该柱右侧、顶部与图表绘图区顶对齐;最右侧柱 → 浮窗翻到柱子左侧,不溢出视口;
  手机窄屏点击柱子也显示同一浮窗,横向滚动或点击非柱区域关闭。
- 进入任一 skill 详情 → 趋势图铺满最近 30 个 UTC 日,used/equipped 分列展示且不相加。
- 按人视角中,同一操作员在同一会话内多次使用同一 skill 只计 1;仅 equipped 或空 operator 的记录不进入
  `operator_table`、`operator_daily` 与 `/api/operator/{name}`。
- `days=7` → `operator_daily` 仅含最近 7 个 UTC 日;`operator_table` 三列不受影响。
- 单操作员详情的 skill 排行行点击 → 进入对应 `/skill/{name}` 详情。
- `GET /api/operator/不存在的人` → 404。
- 主表默认按 30 天会话数降序,平手按累计。
- 进入某操作员详情 → 左侧为 runtime 分布、右侧为「使用 Skill 排行」,排行默认按 7 天列降序。
- /skills 视角切换位于独立卡片,标题栏显示"视角"与当前视角说明,内容行按钮为 32px 高分段控件;
  切换后整页换主语且说明文案随之变化,时间窗不重置。
- 操作员详情/skill 详情"最近记录"首列显示到秒;构造仅有 `day` 无 `first_seen` 的记录 → 回退显示日期。
- 在总览技能主表、操作员主表、操作员详情 skill 排行表中,点击行内非标题位置(如数字列空白处)
  → 正确跳转到对应详情;点击可排序表头 → 仅排序、不跳转。
- 键盘聚焦某可下钻行并按 Enter → 跳转到对应详情。
- "最近记录"表行 hover/点击 → 不跳转,指针为默认。
- 看板页面不再渲染 skills 区块,原有卡片与轮询行为不变。
