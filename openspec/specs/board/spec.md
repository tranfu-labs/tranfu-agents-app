# 规格:board(看板与计算域)

事实来源:`server/routes/board.py`(`/api/state` / `/api/skills` / `/api/skill` / `/api/operator` / `/api/agent` 端点 + `_snapshot` / `metrics` / `leverage` / `skill_usage` / `skills_overview` / `*_payload` / `_state_compute_or_cache`)、`server/profile.py`(`load_profiles` / `load_shim_versions` / `reuse_map`)、共用模块 `server/db.py`、`server/catalog.py`(skill 来源标记)、以及 `frontend/` React 看板。缓存状态 `_state_cache` / `_state_cache_lock` 由 `server/routes/board.py` 持有,`server/app.py` re-export 给测试 monkeypatch。

## 接口
- `GET /api/state` → `{ now, sessions[], feed[], leverage, skills[], shim, totals }`。服务端对响应做进程内 TTL 缓存,
  默认 `STATE_TTL_SECONDS=1.5`,可由 `TF_STATE_TTL` 环境变量覆盖;同一 TTL 窗口内复用上一次快照,
  因此 `now` 表示"上次服务端计算时间",而非"本次请求的服务端时间"。
- `GET /api/skills?days={7|30|90}` → `{ today, daily[], table[], operator_daily[], operator_table[], governance, funnel, catalog }`(SKILLS 总览;`today` 为 UTC 当日,`days` 影响 daily/operator_daily 与 governance 窗口,默认 30)。
- `GET /api/skill/{name}` → 单 skill 详情(含 `today`、指标、used/equipped 分列日级序列、runtime/operator 分布、最近记录、来源);查无此名 → 404。
- `GET /api/operator/{name}` → 单操作员详情(含 `today`、used-only 指标、按 skill 分段日级序列、skill 排行、runtime 分布、最近记录);查无 used 记录 → 404。
- `GET /api/agent/{key}`(key = `operator::agentOrRuntime`)→ 单 agent 详情(可选)。
- `GET /`、`/agents`、`/agent/{key}`、`/skills`、`/skill/{name}`、`/operator/{name}` → React 看板 SPA;
  `GET /assets/*` → Vite 指纹化静态资源;`GET /healthz` → `ok`。`/healthz` 必须是 async handler,
  不打开 DB 连接、不触发 IO,在事件循环直接返回。

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
10. `shim.version` 为服务端当前分发的 shim 内容版本;看板按"三态"比较每张卡的 `shim_version`:
    - `current` —— `agent.shim_version` 等于服务端 `shim.version`(常态显示)。
    - `outdated` —— `agent.shim_version` 存在但不等于 `shim.version`(显示"旧 shim",橙色)。
    - `unknown` —— `agent.shim_version` 缺失/空(显示"等待客户端心跳",灰色)。
    **不允许把 `unknown` 误判为 `outdated`**——字段缺失只代表客户端尚未上报版本,不能代表"旧"。
11. SKILLS 为第三个顶级视图(看板 / Agents / SKILLS),含总览与单 skill 详情(独立视图 + 返回)两级。
12. `/api/skills` 总览页所有聚合(`daily`、`table`)只统计 `mode=used`;`equipped` 仅在 `/api/skill/{name}`
    详情页展示,并与 used 分列,任何位置不得相加。
13. `/api/skills.table` 每行含来源字段,取值 own / meta / external / 非公司库;来源由服务端 catalog 缓存按名字映射。
14. `/api/skills.governance.untracked_usage` 输出"未收录使用占比"管理口径:当前 `days` 窗口内
    `source=非公司库` 且 `mode=used` 的会话×skill 记录数 / 当前窗口全部 `mode=used` 记录数;空分母为 0。
    catalog 中 `external` 不算未收录;`equipped` 不得进入分母、分子或 Top 列表。`top[]` 按窗口内
    used 会话数降序(平手按最近使用日、再按名称),每项含 `name/source/sessions/share/users_30d/runtime_counts/trend_14d/trend_days/last_day`;
    `users_30d` 固定保持近 30 天用户数语义。
15. `/api/skills.funnel` 只统计 catalog 中 `type ∈ {own, meta}` 的 skill,三层为 catalog 收录名单、
    已安装名单(出现在 ≥1 个 agent 的 profiles 安装态快照)、30 天有人使用名单(UTC 日切);
    并返回闲置名单 = 已安装 − 30 天使用。三层均返回名单而非仅数字。
16. catalog 由服务端定时拉取并缓存;拉取失败时 `/api/skills` 仍须 200,funnel 携带旧缓存与过期标记;
    从未成功拉取时 funnel 为"目录不可达"态,其余字段正常。
17. `/api/skills.operator_table` 与 `operator_daily` 只统计 `mode=used`,且排除空 `operator`;人维度计量单位是
    会话×skill 去重使用次数(一行 `skill_uses` used 记录),语义为"此人在多少个会话里用过 skill",非真实调用次数。
    `operator_table` 固定输出 7 天 / 30 天 / 累计、用过 skill 数、会话数、runtime 计数、来源计数、近 14 天趋势和最近使用日;
    默认按 30 天降序,平手按累计。`days` 只影响 `operator_daily`,不影响 `operator_table`。
18. `/api/operator/{name}` 只统计该操作员的 `mode=used` 记录,不输出 equipped 指标;返回指标、按 skill 分段日级序列、
    skill 排行(含来源)、runtime 分布和最近 50 条记录。
19. `/api/state` 必须在服务端做 TTL 缓存复用,缓存 TTL 由 `TF_STATE_TTL`(秒,float)配置,默认 1.5;
    前端可见的所有字段(包括 `now`/`sessions`/`feed`/`leverage`/`skills`/`shim`/`totals`)
    可以在一个 TTL 窗口内相同;不允许任何路径(包括 `/api/skills`、`/api/skill/{name}` 等)
    依赖"`/api/state.now` 必须是请求当下时间"的假设。
20. `/healthz` 必须是 async handler,响应体固定 `ok`,不依赖 DB 或重模块状态;其响应时间不得受
    `/api/state` 聚合压力影响。在 100 并发 `/api/state` 期间,`/healthz` 单请求响应时间应 < 50ms。

## 部署/运维
- `TF_STATE_TTL`:`/api/state` 缓存 TTL(秒,float),默认 `1.5`。区间建议 `0.5~3.0`。
- Docker healthcheck 配置目标:`Timeout=10s`、`Retries=5`、`Interval=30s`、`StartPeriod=10s`。
  配置入口取决于部署方式;根目录 `compose.yml` 托管默认值,若由 Coolify UI 覆盖,以 Coolify 配置为准。
- uvicorn `--workers` 默认 1;启用多 worker 前必须先解决 `_catalog_loop` 多进程并发拉取与写
  `catalog_cache` 表的潜在竞争,该事项需走独立 change。

## 前端规则(MUST)
- 轮询 `/api/state`(约 3s),取不到时退回内置演示数据并显示"未连接服务端"。
- 视图:Pods 看板(按 operator 分组,人=调度员,其 agent=编队)/ Agents 列表 / SKILLS 总览 / 治理详情 / Skill 详情 / Operator 详情。
- 路由:Pods 看板 `/`;Agents 列表 `/agents`;治理详情 `/agent/:key`;SKILLS 总览 `/skills`;
  Skill 详情 `/skill/:name`;Operator 详情 `/operator/:name`;刷新、前进后退、复制链接必须保持当前视图。
- SKILLS 总览筛选绑定到 URL search params:`win`(7/30/90)、`rt`、`src`、`q`、`sort`、`dir`、`view`(`skill`/`operator`)、`lens`(`all`/`untracked`);
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
- SKILLS 总览在按 Skill 视角的"使用排行"卡片内部展示管理者筛选 Lens:
  `[全部 Skill] [未收录使用占比 X% · used/total]`。默认 `lens=all`,显示现有完整 Skill 主榜;
  `lens=untracked` 只把该排行表切为未收录占比列表,不得影响每日趋势图、全局过滤条或公司库漏斗。
  按人视角不展示该 Lens;若 URL 保留 `lens=untracked`,切回按 Skill 视角时可恢复该 Lens。
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
- 操作员详情与单 skill 详情的"最近记录"列表,时间列须以浏览器本地时区展示 `first_seen`:
  浏览器本地今天内显示克制相对时间(中文 `刚刚` / `N分钟前` / `N小时前`,英文 `just now` / `Nm ago` / `Nh ago`);
  浏览器本地昨天及更早显示相对日期加本地时刻(中文 `昨天 HH:mm:ss` / `N天前 HH:mm:ss`,
  英文 `yesterday HH:mm:ss` / `Nd ago HH:mm:ss`);鼠标悬浮时间单元格时,title 显示完整本地绝对时间与浏览器时区名
  (时区名不可得时省略)。`first_seen` 缺失时按原始 UTC 日期 `day` 与服务端返回的 UTC `today`
  显示相对日期:中文 `今天` / `昨天` / `N天前`,英文 `today` / `yesterday` / `Nd ago`;
  hover title 保留原始 `day`,不得把 date-only 值强行按浏览器时区换算或补造具体时刻。
- 所有具有下钻目标的表格(总览技能主表、总览操作员主表、操作员详情的使用 Skill 排行)须整行可点,
  并跳转到对应详情;且须键盘可达(Enter / Space 触发)。整行可点与局部交互冲突时以局部交互为准,
  局部交互元素须阻止冒泡,不触发整行跳转。无下钻目标的表格(如"最近记录")不得呈现为整行可点。
- 详情数据优先取 session 的服务端字段(`cf/skills/mcp/integrations/about/...`);演示映射仅用于独立预览。
- 卡片/详情显示本机上报的 `shim_version` 短码,并按三态(current/outdated/unknown)切换样式:
  current 为常态;outdated 显示"旧 shim"橙色角标;unknown 显示"等待客户端心跳"灰色虚线角标,
  且字段位置渲染占位符(如 "—"),不显示空字符串。
- 暗/亮双主题;通用手机窄屏(≤600px)头部分行、表格横向滚动、详情单栏。
- SKILLS 统计域(`/skills`、`/skill/:name`、`/operator/:name`)使用专用响应式规则:
  桌面 `>1080px` 保持现有信息架构;平板 `601px-1080px`;手机 `≤600px`。
  该域页面根节点不得出现横向滚动;趋势图只允许在 `.chart-box` 内部横向滚动。
- `/skills` 在平板与手机下必须保持单列主内容流:视角卡 → 筛选卡 → 趋势图 → 使用排行 → 公司库漏斗。
  排行优先于漏斗,不得在窄屏下把漏斗挤到排行右侧导致主体过窄。
- `/skills` 的视角切换卡在手机下仍须显示当前视角说明文案;分段按钮等分占满可用宽度。
  筛选条在手机下必须单列展示,搜索框和所有下拉控件宽度为 100%;平板下允许换行但不得撑出页面横向滚动。
- `/skills` 的 7 天趋势图在手机下应铺满图表容器,不得强制用户横向滚动才能看到完整 7 天槽位;
  30/90 天趋势图和详情页固定 30 天趋势图允许在 `.chart-box` 内部横向滚动。
- `/skills` 的 Skill 主榜、未收录占比榜、按人主榜在手机下须从桌面表格压缩为摘要行:
  首行展示主语名称与来源/占比,后续行展示 7d、30d、总计、用户/会话、最近使用日等关键指标。
  其整行可点与键盘可达行为必须保留。
- `/skill/:name` 与 `/operator/:name` 的指标卡在平板下应压缩为 3-4 列,手机下为 2 列;
  数字和标签不得重叠或溢出卡片。`/skill/:name` 的 runtime/operator 分布区在平板和手机下为单列。
  `/operator/:name` 的 runtime 分布与使用 Skill 排行在平板和手机下为单列,使用 Skill 排行位于 runtime 分布之后。
- `/skill/:name` 与 `/operator/:name` 的最近记录表在手机下须展示为摘要行;
  最近记录无下钻目标,仍不得呈现为可点击行。
- 不得使用浏览器本地存储;不得写死后端端口(同源相对路径)。
- 网站 head 的浏览器 favicon 链路须本地化 `https://tranfu.com/` 当前实际使用的版本化 ico/png 文件名,
  并使用同源根绝对路径引用,如 `/favicon-20260626.ico`、`/favicon-32x32-20260530.png`、
  `/favicon-16x16-20260530.png`、`/apple-touch-icon-20260530.png`;不得直接引用 `https://tranfu.com/...`
  远端 favicon 资源,也不得同时声明 SVG favicon 抢优先级。PWA `manifest.json` 保留 TRANFU//AGENTS 自己的
  name/description/theme 语义,icons 可引用同一组版本化本地资源;`theme_color` 必须与 HTML
  `<meta name="theme-color">` 一致。
- 前端源码在 `frontend/`;生产由 Docker/CI 构建 `frontend/dist`,运行容器不依赖 node,仓库不提交 dist。

## 可验证行为
- 同一 agent 跑多次/多 session → 看板仅一张卡,随最新状态刷新。
- 某 agent 3 分钟无心跳 → 卡片转 `idle`(灰)。
- 造数据:skill A 的 `used` 在 31 天前 1 个会话、5 天前 2 个会话(2 个不同 operator)使用 →
  `mode=used` 条目 `sessions_7d=2`、`sessions_30d=2`、`sessions_total=3`、`users_30d=2`。
- 同一 skill A 同时有 `used` 与 `equipped` → `skills` 出现两条同名不同 mode 条目,计数互不相加。
- 空库 → `skills: []`,看板显示空态。
- 服务端 `shim.version=X`,某 agent 上报 `shim_version=X` → 卡片为 current,无角标。
- 同一 agent 上报 `shim_version=Y(≠X)` → 卡片为 outdated,显示"旧 shim"角标。
- 某 agent 从未上报过 `shim_version` → 卡片为 unknown,显示"等待客户端心跳"灰色虚线角标(不得标"旧 shim")。
- 已上报过的 agent 后续事件不再带 `shim_version` → 卡片仍呈现最近一次非空值,**不退回 unknown**。
- 同名 skill 同时有 `used` 与 `equipped` → `/api/skills` 的 table 与 daily 只含 used;
  `/api/skill/{name}` 两种模式并列展示且任何字段不相加。
- 造数据:7 天内 own used 6、external used 2、非公司库 used 4、非公司库 equipped 3 →
  `/api/skills?days=7` 的 `governance.untracked_usage.total_sessions=12`、`used_sessions=4`、
  `ratio≈0.333`,Top 不含 external/equipped。
- `days=30` 包含更多历史非公司库 used 时,`governance.untracked_usage` 的分母、分子、Top 列表随窗口扩大更新。
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
- `/skills?view=skill&lens=all` 显示完整 Skill 主榜;`lens=untracked` 显示未收录占比列表,
  且每日趋势图与公司库漏斗不随 Lens 改变。
- `/skills?view=operator&lens=untracked` 不显示管理者 Lens,操作员排行行为不变。
- 浏览器时区为 Asia/Shanghai,当前本地时间为 `2026-06-28 01:00:00`,记录
  `first_seen=2026-06-27T16:30:00+00:00` → 最近记录可见文本为 `30分钟前`,hover title 为
  `2026-06-28 00:30:00 Asia/Shanghai`。
- 同一当前时间,记录 `first_seen=2026-06-27T15:00:00+00:00` → 最近记录可见文本为
  `昨天 23:00:00`,hover title 为 `2026-06-27 23:00:00 Asia/Shanghai`。
- 操作员详情/skill 详情"最近记录"构造仅有 `day` 无 `first_seen` 的记录,且 `today=2026-06-30`:
  `day=2026-06-30` → 显示 `今天`;`day=2026-06-29` → 显示 `昨天`;
  `day=2026-06-25` → 显示 `5天前`;hover title 均保留原始 `day`。
- 在总览技能主表、操作员主表、操作员详情 skill 排行表中,点击行内非标题位置(如数字列空白处)
  → 正确跳转到对应详情;点击可排序表头 → 仅排序、不跳转。
- 键盘聚焦某可下钻行并按 Enter → 跳转到对应详情。
- "最近记录"表行 hover/点击 → 不跳转,指针为默认。
- 375x812 打开 `/skills?view=skill&lens=all&win=7` → 页面根无横向滚动,视角说明可见,筛选控件逐行铺满,
  7 天趋势图铺满图表容器且无需横向滚动即可看到全部 7 天槽位,Skill 主榜为摘要行且整行点击进入 `/skill/:name`。
- 375x812 打开 `/skills?view=skill&lens=untracked&win=30` → 页面根无横向滚动,治理 Lens 按钮可换行且不溢出,
  30 天趋势图只在 `.chart-box` 内横滚,未收录占比榜为摘要行,公司库漏斗位于排行之后。
- 375x812 打开 `/skills?view=operator&win=30` → 页面根无横向滚动,按人榜为摘要行且整行点击进入 `/operator/:name`,
  Lens 不显示,公司库漏斗仍位于排行之后。
- 768x1024 打开 `/skills` → 排行与公司库漏斗上下堆叠,筛选条可换行但页面无横向滚动,
  表格/图表横滚限制在组件内部。
- 375x812 打开任一 `/skill/:name` → 指标卡为 2 列,趋势图内部横滚,runtime/operator 分布单列,
  最近记录为摘要行且不可点击。
- 375x812 打开任一 `/operator/:name` → 指标卡为 2 列,趋势图内部横滚,runtime 分布在上、使用 Skill 排行在下,
  使用 Skill 排行摘要行可点击,最近记录摘要行不可点击。
- 1440x900 打开 `/skills`、`/skill/:name`、`/operator/:name` → 桌面布局与既有信息架构保持一致,
  不因移动端样式退化。
- 看板页面不再渲染 skills 区块,原有卡片与轮询行为不变。
- 构建后的 `index.html` head 含 `/favicon-20260626.ico`、`/favicon-32x32-20260530.png`、
  `/favicon-16x16-20260530.png` 与 `/apple-touch-icon-20260530.png`,且不含 `rel="icon"` 的 `favicon.svg`。
- `manifest.json` 的 icons 指向版本化本地资源,且 `theme_color` 与 HTML `<meta name="theme-color">` 一致。
- 同一 `TF_STATE_TTL` 窗口内连续请求 `/api/state` → 响应可完全相同,`now` 不随每次请求刷新;超过 TTL 后重新计算。
- 100 并发 `/api/state` 期间请求 `/healthz` → 返回 `ok`,且不因 `/api/state` 聚合占用 threadpool 而排队超时。
