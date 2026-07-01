# 规格:board(看板与计算域)

事实来源:`server/routes/board.py`(`/api/state` / `/api/skills` / `/api/skill` / `/api/operator` / `/api/agent` 端点 + `_snapshot` / `metrics` / `leverage` / `skill_usage` / `skills_overview` / `*_payload` / `_state_compute_or_cache`)、`server/profile.py`(`load_profiles` / `load_shim_versions` / `reuse_map`)、共用模块 `server/db.py`、`server/catalog.py`(skill 来源标记)、以及 `frontend/` React 看板。缓存状态 `_state_cache` / `_state_cache_lock` 由 `server/routes/board.py` 持有,`server/app.py` re-export 给测试 monkeypatch。

## 接口
- `GET /api/state` → `{ now, sessions[], feed[], leverage, skills[], shim, totals }`。服务端对响应做进程内 TTL 缓存,
  默认 `STATE_TTL_SECONDS=1.5`,可由 `TF_STATE_TTL` 环境变量覆盖;同一 TTL 窗口内复用上一次快照,
  因此 `now` 表示"上次服务端计算时间",而非"本次请求的服务端时间"。
- `GET /api/skills?days={7|30|90}` 或 `GET /api/skills?w={today|this_week|last_week|7d|14d|30d|90d|custom}[&wstart=&wend=]` →
  `{ today, daily[], table[], operator_daily[], operator_table[], governance, period_comparison?, attribution?, funnel, catalog }`(SKILLS 总览;
  `today` 为服务端统计时区 `Asia/Shanghai` 当日;`days` 为旧兼容参数,`w` 为新版仪表盘时间窗;两者影响 daily/operator_daily、
  governance、period_comparison 与 attribution 窗口,默认 30 天。新增字段均为可选返回,前端读不到时降级。)
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
4. 活跃统计窗口 `WINDOW_DAYS=90`,按服务端统计时区 `Asia/Shanghai` 日;跨天会话按该时区当天边界拆分。
5. `totals.live` 仅计 `status ∈ {running, started, waiting}`。
6. `feed` 为真实状态转变(非心跳),倒序。
7. leverage = `{assets: 不同技能数, skills_week: 近 7 天首次出现的技能数}`。
8. `skills` 为 Skill 使用/装备排行数组,每项含 `name`、`mode`(`used`/`equipped`)、`sessions_7d`、`sessions_30d`、
   `sessions_total`、`users_30d`、`last_day`;按 `sessions_30d` 降序,平手按 `sessions_total`。
9. Skill 计数口径:一个会话用过/装备某 skill 的某个 mode 算一次(来源即 `skill_uses` 的会话×skill×mode 粒度,
   读侧不再去重);时间窗口按服务端统计时区 `Asia/Shanghai` 日切,与活跃统计口径一致。`used` 与 `equipped` 必须分条呈现,不得相加。
10. `shim.version` 为服务端当前分发的 shim 内容版本;看板按"三态"比较每张卡的 `shim_version`:
    - `current` —— `agent.shim_version` 等于服务端 `shim.version`(常态显示)。
    - `outdated` —— `agent.shim_version` 存在但不等于 `shim.version`(显示"旧 shim",橙色)。
    - `unknown` —— `agent.shim_version` 缺失/空(显示"等待客户端心跳",灰色)。
    **不允许把 `unknown` 误判为 `outdated`**——字段缺失只代表客户端尚未上报版本,不能代表"旧"。
11. SKILLS 为第三个顶级视图(看板 / Agents / SKILLS),含总览与单 skill 详情(独立视图 + 返回)两级。
12. `/api/skills` 总览页所有聚合(`daily`、`table`)只统计 `mode=used`;`equipped` 仅在 `/api/skill/{name}`
    详情页展示,并与 used 分列,任何位置不得相加。
13. `/api/skills.table` 每行含来源字段,取值 own / meta / external / 非公司库;来源由服务端 catalog 缓存按名字映射。
14. `/api/skills.governance.untracked_usage` 输出"未收录使用占比"管理口径:当前 `days/w` 窗口内
    `source=非公司库` 且 `mode=used` 的会话×skill 记录数 / 当前窗口全部 `mode=used` 记录数;空分母为 0。
    catalog 中 `external` 不算未收录;`equipped` 不得进入分母、分子或 Top 列表。`top[]` 按窗口内
    used 会话数降序(平手按最近使用日、再按名称),每项含 `name/source/sessions/share/users_30d/runtime_counts/trend_14d/trend_days/last_day`;
    `users_30d` 固定保持近 30 天用户数语义。
15. `/api/skills.funnel` 只统计 catalog 中 `type ∈ {own, meta}` 的 skill,三层为 catalog 收录名单、
    已安装名单(出现在 ≥1 个 agent 的 profiles 安装态快照)、当前 `days/w` 窗口有人使用名单(按 `Asia/Shanghai` 日切;
    字段名 `used_30d` 保留兼容);并返回闲置名单 = 已安装 − 当前窗口使用。三层均返回名单而非仅数字。
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
- SKILLS 总览筛选绑定到 URL search params:`w`(`today`/`this_week`/`last_week`/`7d`/`14d`/`30d`/`90d`/`custom`)、
  `wstart`、`wend`、`cmp`、`topn`(`5|8|10|20`)、`hz`、`sel`、`rt`、`src`、`q`、`sort`、`dir`、`view`(`skill`/`operator`)。
  旧参数 `win` 保留向下兼容并在没有 `w` 时映射为 `w`;旧参数 `lens` 保留但不再驱动 UI。筛选变化使用 replace,
  不污染浏览器历史;详情跳转使用 push。
- Pods 看板不再展示 Skills 排行区;`/api/state.skills` 字段保留用于协议兼容,前端看板不消费。
- SKILLS 总览进入时加载 `/api/skills`,之后低频刷新;加载失败显示错误态。柱状图横轴按所选 `Asia/Shanghai` 统计日窗口逐日铺满:
  右端取服务端 `today`,左端为 `today-(N-1)`;每一天占一个槽位,有 used 数据才长堆叠柱,无数据留空槽。
  前端取窗口内使用量 Top N(`topn`,默认 8)分色,其余合并为"其它"段;窗口选择器不含"全部"档。
- SKILLS 总览采用八层仪表盘结构:控制条 → KPI 环带(8 格) → 治理健康条(5 项) → 每日堆叠柱(全宽独占) →
  主视图并列(排行 Bar | 治理待办) → 归因 Donut(来源+runtime) → 明细表+抽屉 → 公司库采纳漏斗(下沉、默认折叠)。
  首次加载只保留控制条和 skeleton/Empty;增量刷新保留旧数据并在标题 `cnt` 标记 loading/error。
- 控制条承载视角切换、时间窗、环比开关、搜索、runtime、来源、Top N、隐藏 0 使用和导出入口。视角切换使用 32px 高分段按钮,
  选中态使用品牌色 `--brand`;切换视角不重置时间窗。公司库漏斗常驻且始终使用 skill/catalog 口径。
- 按 Skill 视角 KPI 环带 8 格口径:总触发次数、公司库覆盖率、活跃操作员数、平均每会话 skill 数、未收录使用占比、闲置 skill 数、
  装了没用比例、Top3 集中度。除闲置 skill 数和装了没用比例两个快照指标外,其余展示本期 vs 上期同长度窗口 delta;
  `previous=0,current>0` 显示 `+∞%`,两边 0 显示 `—`。按人视角 KPI 环带换为 operator 口径快照,至少包含使用记录、活跃操作员、
  活跃率、人均 skill、人均会话、Top3 集中度、runtime 覆盖和来源覆盖。
- 按 Skill 视角治理健康条 5 项:未收录占比、装了没用比例、公司库覆盖率、Top3 集中度、平均 skill/会。每项按 good/warn/bad 三色展示,
  只做信号不承载点击;阈值为未收录 `<10%/10-25%/>25%`、装了没用 `<20%/20-40%/>40%`、覆盖率 `>50%/30-50%/<30%`、
  Top3 `30-60% good,60-80% 或 <30% warn,>80% bad`、平均 skill/会 `>1.5 good,0.8-1.5 warn,<0.8 bad`。
  按人视角治理健康条换为 operator 使用健康信号,至少包含活跃率、人均 skill、Top3 集中度、runtime 覆盖和活跃操作员数。
- 主视图排行 Bar 在按 Skill 视角显示 Top N + 长尾「其他 N 个 skill」聚合,值口径为当前窗口 used sessions;点行设置全局 `sel`,
  再点取消,并与每日堆叠柱和 Donut 联动。按人视角主视图显示操作员排行表并继续下钻 `/operator/:name`。
- 按 Skill 视角治理待办 3 组:有使用但未收录、装了窗口内没用、收录但零装机。按人视角待办换为重度使用者、近 7 天沉睡、
  低覆盖使用者。每组 Top 8 + 查看全部/忽略入口;忽略是当前页面会话态,不写入浏览器持久化,避免突破 ADR-0023 的 localStorage 边界。
- 归因 Donut 两张:按来源为双层 Sunburst(内环=已收录 vs 未收录;外环=own/meta/external/non_catalog),按 runtime 为单层 Donut;
  权重均为当前窗口 used sessions。零值扇区不画;来源父子角度一致性容差 <0.5°;点击来源扇区联动全局 `src`。
- 明细表列为名称/来源/W 内/W′ 上期/Δ%/用户/runtime/趋势/最近。按 Skill 视角点行默认打开右侧抽屉而不是直接跳详情;
  抽屉显示 KPI4 格、趋势、runtime 拆分、最近 5 次触发,并提供「前往详情页」按钮作为 `/skill/:name` 逃逸口。
- SKILLS 柱状图悬停某日列时,该列高亮、其余列降透明,并显示锚定柱子的明细浮窗(日期、当天各 skill 降序明细、
  Top8 外并"其它"、合计);浮窗锚定柱子几何而非光标——默认贴柱子右侧、顶部对齐图表绘图区顶,
  碰视口右边界翻到柱子左侧、碰下边界上移贴视口底。今日列作为最后一格,以进行中视觉区分并在浮窗标注。
  移动端点击列显示浮窗,点击别处或横向滚动图表时关闭。整窗全空或筛选后全空时显示空态,不渲染一排空轴。
- Skill 详情趋势图固定最近 30 个 `Asia/Shanghai` 统计日逐日铺满(右端同服务端 `today`),used 柱与 equipped 折线分列展示,
  不相加;空天留白,今日列进行中,悬停/点击浮窗显示 used/equipped,且使用与 SKILLS 总览一致的柱子锚定、
  视口翻转和点击别处关闭规则。
- 单操作员详情的 skill 排行在界面上呈现为「使用 Skill 排行」,默认按最近 7 天使用次数降序(平手按累计、再按名称);
  此默认仅作用于操作员详情页内,不改变 SKILLS 总览页按当前窗口 `W` 降序的口径。
  操作员详情的 runtime 分布与 skill 排行采用左窄(runtime)/右宽(skill 排行)布局,窄屏(≤1080px)降级为单列。
- 操作员详情与单 skill 详情的"最近记录"列表,时间列须以浏览器本地时区展示 `first_seen`:
  浏览器本地今天内显示克制相对时间(中文 `刚刚` / `N分钟前` / `N小时前`,英文 `just now` / `Nm ago` / `Nh ago`);
  浏览器本地昨天显示 `昨天 HH:mm` / `yesterday HH:mm`;本地 2-6 天前显示星期标签加本地时刻
  (中文 `周一 HH:mm` 等,英文 `Mon HH:mm` 等);本地今年更早显示 `MM-DD HH:mm`;跨年显示 `YYYY-MM-DD HH:mm`;
  鼠标悬浮时间单元格时,title 显示完整本地绝对时间到秒与浏览器时区名
  (时区名不可得时省略)。`first_seen` 缺失时按原始统计日期 `day` 与服务端返回的 `Asia/Shanghai` `today`
  显示 date-only 日期层级:中文 `今天` / `昨天` / `周一` / `MM-DD` / `YYYY-MM-DD`,
  英文 `today` / `yesterday` / `Mon` / `MM-DD` / `YYYY-MM-DD`;
  hover title 保留原始 `day`,不得把 date-only 值强行按浏览器时区换算或补造具体时刻。
- 所有具有详情动作的表格须整行可点且键盘可达(Enter / Space 触发):总览 Skill 明细表打开同页抽屉,
  抽屉内的显式按钮跳 `/skill/:name`;总览操作员主表与操作员详情的使用 Skill 排行跳转到对应详情。整行可点与局部交互冲突时以局部交互为准,
  局部交互元素须阻止冒泡,不触发整行跳转。无下钻目标的表格(如"最近记录")不得呈现为整行可点。
- 详情数据优先取 session 的服务端字段(`cf/skills/mcp/integrations/about/...`);演示映射仅用于独立预览。
- 卡片/详情显示本机上报的 `shim_version` 短码,并按三态(current/outdated/unknown)切换样式:
  current 为常态;outdated 显示"旧 shim"橙色角标;unknown 显示"等待客户端心跳"灰色虚线角标,
  且字段位置渲染占位符(如 "—"),不显示空字符串。
- 主题模式为 `system` / `light` / `dark` 三态:`system` 为默认并跟随浏览器 `prefers-color-scheme`;
  `light` / `dark` 为显式模式,不受系统偏好变化影响。顶部导航须提供可键盘操作的三态主题控件,
  当前模式须有明确选中态;前端须在 root 元素反映 `data-theme-mode` 与实际 `data-theme`,
  CSS 主题变量以 root 实际主题为准,并设置 `color-scheme`。主题变化时须同步当前文档
  `<meta name="theme-color">`,深色 `#0b0b0c`,浅色 `#f6f7f8`;`manifest.json.theme_color`
  与静态默认 meta 保持一致,运行时不动态改写 manifest。
- 通用手机窄屏(≤600px)头部分行、表格横向滚动、详情单栏。
- SKILLS 统计域(`/skills`、`/skill/:name`、`/operator/:name`)使用专用响应式规则:
  桌面 `>1080px` 保持现有信息架构;平板 `601px-1080px`;手机 `≤600px`。
  该域页面根节点不得出现横向滚动;趋势图只允许在 `.chart-box` 内部横向滚动。
- `/skills` 在平板与手机下必须保持单列主内容流:控制条 → KPI 环带 → 治理健康条 → 趋势图 → 排行/治理待办 →
  归因 → 明细 → 公司库漏斗。漏斗下沉到底部,不得在窄屏下挤到排行右侧导致主体过窄。
- `/skills` 的控制条在手机下仍须显示当前视角说明文案;分段按钮等分占满可用宽度。
  搜索框和所有下拉控件宽度为 100%;checkbox 控件保持 16px 级别,不得被通用输入样式拉伸;平板下允许换行但不得撑出页面横向滚动。
- `/skills` 的 7 天趋势图在手机下应铺满图表容器,不得强制用户横向滚动才能看到完整 7 天槽位;
  30/90 天趋势图和详情页固定 30 天趋势图允许在 `.chart-box` 内部横向滚动。
- `/skills` 的排行 Bar、Skill 明细表和按人主榜在手机下须从桌面表格/横条压缩为摘要行或单列条:
  首行展示主语名称与来源/占比,后续行展示 W 内、W′、Δ%、用户/会话、最近使用日等关键指标。
  Skill 明细整行可点打开抽屉且键盘可达;按人主榜整行可点进入 `/operator/:name` 且键盘可达。
- `/skill/:name` 与 `/operator/:name` 的指标卡在平板下应压缩为 3-4 列,手机下为 2 列;
  数字和标签不得重叠或溢出卡片。`/skill/:name` 的 runtime/operator 分布区在平板和手机下为单列。
  `/operator/:name` 的 runtime 分布与使用 Skill 排行在平板和手机下为单列,使用 Skill 排行位于 runtime 分布之后。
- `/skill/:name` 与 `/operator/:name` 的最近记录表在手机下须展示为摘要行;
  最近记录无下钻目标,仍不得呈现为可点击行。
- 除 `/admin` 管理钥匙的 `sessionStorage` 例外外,前端仅可使用 `localStorage` 固定 key
  `tf-theme-mode` 保存主题模式 `system | light | dark`;不得保存语言、筛选条件、业务数据、身份数据、
  上报内容或任意其它前端状态。读取或写入失败时须静默回退,不得阻塞看板渲染。
- 不得写死后端端口(同源相对路径)。
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
- 服务端当前 UTC 时间为 `2026-06-12T16:05:00+00:00` 时,`/api/skills` 与 `/api/skill/{name}` 均返回 `today=2026-06-13`。
- `days=7` 或 `w=7d` → daily 仅含最近 7 个 `Asia/Shanghai` 统计日;`w=14d` 可返回 14 天窗口;
  `days=0` 返回 400。`w` 变化会影响 daily/operator_daily、governance、period_comparison、attribution 与漏斗使用层。
- `/api/skills` 与 `/api/skill/{name}` 均返回 `Asia/Shanghai` `today`;前端以它作为时间轴右端,不得用浏览器本地日期推算。
- 只有今天有 used → 主图 7/30/90 日槽位完整铺开,仅最后一槽有今日进行中柱;中间缺数据的日期保留空槽。
- 悬停某柱 → 浮窗锚定该柱右侧、顶部与图表绘图区顶对齐;最右侧柱 → 浮窗翻到柱子左侧,不溢出视口;
  手机窄屏点击柱子也显示同一浮窗,横向滚动或点击非柱区域关闭。
- 进入任一 skill 详情 → 趋势图铺满最近 30 个 `Asia/Shanghai` 统计日,used/equipped 分列展示且不相加。
- 按人视角中,同一操作员在同一会话内多次使用同一 skill 只计 1;仅 equipped 或空 operator 的记录不进入
  `operator_table`、`operator_daily` 与 `/api/operator/{name}`。
- `days=7` → `operator_daily` 仅含最近 7 个 `Asia/Shanghai` 统计日;`operator_table` 三列不受影响。
- 单操作员详情的 skill 排行行点击 → 进入对应 `/skill/{name}` 详情。
- `GET /api/operator/不存在的人` → 404。
- SKILLS 总览 Skill 明细表默认按当前窗口 `W` 内会话数降序,平手按累计;按人主表保留 30 天会话数降序,平手按累计。
- 进入某操作员详情 → 左侧为 runtime 分布、右侧为「使用 Skill 排行」,排行默认按 7 天列降序。
- /skills 视角切换位于控制条内,内容行按钮为 32px 高分段控件;切换后整页换主语且说明文案随之变化,时间窗不重置。
- `/skills?view=skill&w=7d&topn=8` 显示 KPI 环带 8 格、治理健康 5 项、全宽每日柱、排行 Bar、治理待办、两张 Donut、明细表和下沉漏斗。
- `/skills?view=skill&lens=untracked` 中 `lens` 为 no-op 兼容参数;未收录使用通过 KPI、健康条和治理待办 A 组呈现。
- 点击 Skill 明细表任意行 → 同页打开右侧抽屉并写入 `sel=<skill>`;抽屉内点「前往详情页」才跳 `/skill/:name`。
- 浏览器时区为 Asia/Shanghai,当前本地时间为 `2026-06-28 01:00:00`,记录
  `first_seen=2026-06-27T16:30:00+00:00` → 最近记录可见文本为 `30分钟前`,hover title 为
  `2026-06-28 00:30:00 Asia/Shanghai`。
- 同一当前时间,记录 `first_seen=2026-06-27T15:00:00+00:00` → 最近记录可见文本为
  `昨天 23:00`,hover title 为 `2026-06-27 23:00:00 Asia/Shanghai`。
- 当前本地时间为 `2026-06-30 12:00:00`,记录本地时间为 `2026-06-25 09:18:55`
  → 最近记录可见文本为 `周四 09:18`,hover title 为 `2026-06-25 09:18:55 Asia/Shanghai`。
- 当前本地时间为 `2026-06-30 12:00:00`,记录本地时间为 `2026-06-02 09:18:55`
  → 最近记录可见文本为 `06-02 09:18`。
- 当前本地时间为 `2026-06-30 12:00:00`,记录本地时间为 `2025-12-30 09:18:55`
  → 最近记录可见文本为 `2025-12-30 09:18`。
- 操作员详情/skill 详情"最近记录"构造仅有 `day` 无 `first_seen` 的记录,且 `today=2026-06-30`:
  `day=2026-06-30` → 显示 `今天`;`day=2026-06-29` → 显示 `昨天`;
  `day=2026-06-25` → 显示 `周四`;`day=2026-06-02` → 显示 `06-02`;
  `day=2025-12-30` → 显示 `2025-12-30`;hover title 均保留原始 `day`。
- 在 SKILLS 明细表、操作员主表、操作员详情 skill 排行表中,点击行内非标题位置(如数字列空白处)
  → Skill 明细表打开抽屉,操作员主表与操作员详情 skill 排行跳转到对应详情;点击可排序表头 → 仅排序、不触发行操作。
- 键盘聚焦某可操作行并按 Enter/Space → 触发与点击相同的抽屉或跳转行为。
- "最近记录"表行 hover/点击 → 不跳转,指针为默认。
- 375x812 打开 `/skills?view=skill&w=7d` → 页面根无横向滚动,控制条说明可见,筛选控件逐行铺满,
  7 天趋势图铺满图表容器且无需横向滚动即可看到全部 7 天槽位,排行 Bar 与明细表为移动摘要/单列样式,点 Skill 明细行打开全屏抽屉。
- 375x812 打开 `/skills?view=skill&w=30d` → 页面根无横向滚动,30 天趋势图只在 `.chart-box` 内横滚,
  治理待办位于排行之后,公司库漏斗位于页面底部。
- 375x812 打开 `/skills?view=operator&w=30d` → 页面根无横向滚动,按人榜为摘要行且整行点击进入 `/operator/:name`,
  公司库漏斗仍位于页面底部。
- 768x1024 打开 `/skills` → 主视图上下堆叠,Donut 上下堆叠,筛选条可换行但页面无横向滚动,
  表格/图表横滚限制在组件内部。
- 375x812 打开任一 `/skill/:name` → 指标卡为 2 列,趋势图内部横滚,runtime/operator 分布单列,
  最近记录为摘要行且不可点击。
- 375x812 打开任一 `/operator/:name` → 指标卡为 2 列,趋势图内部横滚,runtime 分布在上、使用 Skill 排行在下,
  使用 Skill 排行摘要行可点击,最近记录摘要行不可点击。
- 1440x900 打开 `/skills`、`/skill/:name`、`/operator/:name` → 桌面布局与各自信息架构保持一致,
  不因移动端样式退化。
- 首次打开看板且无主题偏好时,实际主题跟随浏览器 `prefers-color-scheme`。
- 选择 `light` 后刷新页面,页面在 React 应用启动前即呈现浅色主题,`data-theme="light"`、
  `color-scheme: light` 与 `theme-color=#f6f7f8` 一致。
- 选择 `dark` 后刷新页面,页面在 React 应用启动前即呈现深色主题,`data-theme="dark"`、
  `color-scheme: dark` 与 `theme-color=#0b0b0c` 一致。
- 选择 `system` 后,浏览器系统偏好从深色切到浅色时,看板无需刷新即可更新为浅色;从浅色切到深色亦然。
- localStorage 不可用或存储值非法时,看板仍能渲染,并回退为 `system`。
- `manifest.json.theme_color` 与静态默认 meta 均为 `#0b0b0c`;浅色运行时只更新当前文档 meta 为 `#f6f7f8`。
- 375x812 打开 `/` 与 `/skills` → 顶部三态主题控件可见且不造成页面根横向滚动。
- 看板页面不再渲染 skills 区块,原有卡片与轮询行为不变。
- 同一 `TF_STATE_TTL` 窗口内连续请求 `/api/state` → 响应可完全相同,`now` 不随每次请求刷新;超过 TTL 后重新计算。
- 100 并发 `/api/state` 期间请求 `/healthz` → 返回 `ok`,且不因 `/api/state` 聚合占用 threadpool 而排队超时。
