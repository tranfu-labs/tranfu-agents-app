# 规格:board(看板与计算域)

事实来源:`server/routes/board.py`(`/api/state` / `/api/skills` / `/api/skill` / `/api/operator` / `/api/agent` 端点 + `_snapshot` / `metrics` / `leverage` / `skill_usage` / `skills_overview` / `*_payload` / `_state_compute_or_cache`)、`server/profile.py`(`load_profiles` / `load_shim_versions` / `reuse_map`)、共用模块 `server/db.py`、`server/catalog.py`(skill 来源标记)、以及 `frontend/` React 看板。缓存状态 `_state_cache` / `_state_cache_lock` 由 `server/routes/board.py` 持有,`server/app.py` re-export 给测试 monkeypatch。

## 接口
- `GET /api/state` → `{ now, sessions[], feed[], leverage, skills[], shim, totals }`。服务端对响应做进程内 TTL 缓存,
  默认 `STATE_TTL_SECONDS=1.5`,可由 `TF_STATE_TTL` 环境变量覆盖;同一 TTL 窗口内复用上一次快照,
  因此 `now` 表示"上次服务端计算时间",而非"本次请求的服务端时间"。
- `GET /api/state/stream` → `text/event-stream`。连接建立后先发送一条 `event: state` 完整快照,
  payload 与 `/api/state` 同结构;后续由写侧 dirty 标记触发合并推送,长时间无业务事件时发送 SSE comment keepalive。
  SSE 失败不得影响 `/api/state` 普通 HTTP 请求。
- `GET /api/skills?days={7|30|90}` 或 `GET /api/skills?w={today|this_week|last_week|7d|14d|30d|90d|custom}[&wstart=&wend=&rt=&src=&scope=all|new]` →
  `{ today, window, daily[], table[], operator_daily[], operator_table[], governance, period_comparison?, attribution?, funnel, published_skills?, catalog }`(SKILLS 总览;
  `today` 为服务端统计时区 `Asia/Shanghai` 当日;`window` 显式返回本期/上期起止日;`days` 为旧兼容参数,`w` 为新版仪表盘时间窗;两者影响 daily/operator_daily、
  governance、period_comparison 与 attribution 窗口;服务端无参兼容默认 30 天,SKILLS 前端无 URL 窗口参数时默认请求 `7d`。
  可选 `rt/src` 只影响 `operator_table` / `operator_daily` 的证据范围,用于按人视角;可选 `scope=new` 将总览收敛到当前窗口内历史首次 used 的 skill 名单。
  `published_skills[]` 为当前窗口内按 catalog `published_at` 统计的新发布公司库 skill 列表,每项至少含
  `name/source/version/author/published_at/published_day/updated_at/path/sha/installers/window_sessions/last_day`;
  `period_comparison` 同步返回 `current_published_skill_count` 与 `previous_published_skill_count`。
  skill 搜索词、Top N、隐藏 0 使用不得进入该 overview 请求。
  新增字段均为可选返回,前端读不到时降级。)
- `GET /api/skills/evidence?kind={total|untracked|coverage|operators|avg_per_session|idle|unused_ratio|zero_install|top3|runtime|source}[&days=7|30|90][&w=today|this_week|last_week|7d|14d|30d|90d|custom][&wstart=&wend=&q=&rt=&src=&skill=&operator=&limit=&offset=]`
  → 当前时间窗下的 SKILLS 证据 payload,字段含 `today/window/summary/actions/applied_filters/ignored_filters/top_skills/top_operators/daily/records/items/catalog`;
  只统计 `mode=used` records,`equipped` 不得进入 `summary.records`、`top_*`、`daily` 或 `records`。
  `kind=idle|unused_ratio` 的 `items[]` 必须包含 `installers_detail[]`,每项至少包含 `operator/agent_key/runtime/profile_updated_at`;
  `kind=zero_install` 的 `items[]` 必须返回 `installers=0` 与空 `installers_detail=[]`。
  `/api/skills` 与 `/api/skills/evidence` 可返回 `ETag` 并处理 `If-None-Match`;ETag 必须按路径、归一化 query 参数与稳定响应 payload 计算。
  命中时只允许同 URL / 同参数返回 `304` 且无 body,客户端只能复用本次服务端校验通过的同 URL payload;未经独立业务确认不得为这两个 API 引入跳过服务端校验的 TTL。
- `GET /api/skill/{name}` → 单 skill 详情(含 `today`、指标、used/equipped 分列日级序列、runtime/operator 分布、最近记录、来源);查无此名 → 404。
- `GET /api/operator/{name}` → 单操作员详情(含 `today`、used-only 指标、按 skill 分段日级序列、skill 排行、runtime 分布、最近记录);查无 used 记录 → 404。
- `GET /api/agent/{key}`(key = `operator::agentOrRuntime`)→ 单 agent 详情(可选)。
- `GET /`、`/agents`、`/agent/{key}`、`/skills`、`/skills/new`、`/skills/evidence`、`/skills/clues/{kind}`、`/skill/{name}`、`/operator/{name}` → React 看板 SPA;
  `GET /assets/*` → Vite 指纹化静态资源,成功响应必须可长期缓存(`public, max-age=31536000, immutable`);
  SPA HTML 必须保持 `no-cache` 或等价 revalidate 策略,避免旧入口 HTML 长期引用过期 bundle;`GET /healthz` → `ok`。`/healthz` 必须是 async handler,
  不打开 DB 连接、不触发 IO,在事件循环直接返回。

## 规则(MUST)
1. **卡片按身份合并**:每个 `(operator, agent‖runtime)` 只输出**一张**卡,保留 `last_seen` 最新的 session(见 ADR-0006)。
2. 每张卡合并:计算所得活跃(today/week/series7/`active_days`[90])、质量(runs/success/error/avg_sec/auto_rate)、
   复用(跨人技能重叠),以及该身份最新 profile 字段。
3. **掉线判定**:`running/started` 且距 `last_seen` 超过 `STALE_SECONDS=180` 秒 → 展示为 `idle`。
4. 活跃统计窗口 `WINDOW_DAYS=90`,按服务端统计时区 `Asia/Shanghai` 日;跨天会话按该时区当天边界拆分。
5. `totals.live` 仅计 `status ∈ {running, started, waiting}`。
6. `feed` 为真实状态转变(非心跳),倒序。
7. leverage = `{assets, skills_week}`。`assets` 为 `skill_uses WHERE mode='used'` 的 distinct skill 数;
   `skills_week` 为当前 7 天窗口内历史首次 `used` 的 distinct skill 数。历史首次日定义为该 skill 在
   `skill_uses WHERE mode='used'` 的最小 `day`;profile installed、`skills_seen` only、`equipped` only
   均不得计入 nav 展示数字。`skills_seen` 仅保留为内部发现/安装痕迹派生态。
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
14. `/api/skills?scope=new` 只返回当前窗口内历史首次 `used` 的 skill 名单:其 `table`、`daily`、
    `operator_table`、`operator_daily`、`period_comparison`、`attribution` 与 `governance.untracked_usage`
    均收敛到该名单;`funnel` 保持公司库整体口径。响应必须包含 `scope` 与 `new_skill_count`;非法 `scope`
    返回 400。该名单态是可行动列表入口,不得默认跳 raw evidence。
    `/api/skills.published_skills` 是不同口径:只统计 catalog 中 `type ∈ {own, meta}` 且 `published_at`
    可解析的 skill;`published_at` 必须按 UTC instant 解析并转换为服务端统计时区 `Asia/Shanghai` 的 date-only
    `published_day` 后再与 `window.start..window.end` 比较。当前窗口内发布但没有任何 `mode=used`
    记录的 skill 仍必须进入 `published_skills[]`,其 `window_sessions=0`;`external`、缺失或非法
    `published_at` 均不得计入。`previous_published_skill_count` 使用上一同长窗口同口径计算。
15. `/api/skills.governance.untracked_usage` 输出"未收录使用占比"管理口径:当前 `days/w` 窗口内
    `source=非公司库` 且 `mode=used` 的会话×skill 记录数 / 当前窗口全部 `mode=used` 记录数;空分母为 0。
    catalog 中 `external` 不算未收录;`equipped` 不得进入分母、分子或 Top 列表。`top[]` 按窗口内
    used 会话数降序(平手按最近使用日、再按名称),每项含 `name/source/sessions/share/users_30d/runtime_counts/trend_14d/trend_days/last_day`;
    `users_30d` 固定保持近 30 天用户数语义。
16. `/api/skills.funnel` 只统计 catalog 中 `type ∈ {own, meta}` 的 skill,三层为 catalog 收录名单、
    已安装名单(出现在 ≥1 个 agent 的 profiles 安装态快照)、当前 `days/w` 窗口有人使用名单(按 `Asia/Shanghai` 日切;
    字段名 `used_30d` 保留兼容);并返回闲置名单 = 已安装 − 当前窗口使用。三层均返回名单而非仅数字。
17. `/api/skills/evidence` 的 `kind` 是强制证据口径,用户筛选是附加约束。`q/rt/skill/operator` 与 `kind`
    取交集;`src` 只有在不与 `kind` 的强制 source 口径冲突时才生效。若冲突,后端必须忽略冲突 `src`
    并在 `ignored_filters` 说明。`src=non_catalog` 等价于服务端来源 `非公司库`;catalog 中 `external` 不算未收录。
18. `/api/skills/evidence?kind=total` 的 `summary.records` 必须等于同一窗口 `/api/skills` 响应里的
    `period_comparison.current_sessions`;`kind=untracked` 必须只包含 `source=非公司库` 的 used records。
    `kind=idle` / `kind=unused_ratio` 的名单口径为 company catalog `own|meta` 中的 installed names 减去当前窗口 used company names;
    `kind=zero_install` 的名单口径为 company catalog `own|meta` names 减去 installed names。
    `limit` 默认 100,上限 500;非法 kind、limit、offset 返回 400。
19. catalog 由服务端定时拉取并缓存;拉取失败时 `/api/skills` 仍须 200,funnel 携带旧缓存与过期标记;
    从未成功拉取时 funnel 为"目录不可达"态,其余字段正常。
20. `/api/skills.operator_table` 与 `operator_daily` 只统计 `mode=used`,且排除空 `operator`;人维度计量单位是
    会话×skill 去重使用次数(一行 `skill_uses` used 记录),语义为"此人在多少个会话里用过 skill",非真实调用次数。
    `operator_table` 必须输出当前 `window.start..window.end` 的 `sessions_window`,以及上一同长窗口的
    `previous_sessions`;默认按 `sessions_window desc, sessions_total desc, operator asc` 排序。兼容字段
    `sessions_7d`、`sessions_30d`、`sessions_total`、`skill_count`、`session_count`、runtime 计数、来源计数、
    近 14 天趋势和最近使用日仍保留。`rt` 与 `src` 查询参数只应用于 `operator_table` / `operator_daily`;
    二者同时存在时必须取交集,并在 `window_runtime_counts` 与 `window_source_counts` 中反映当前窗口内的已过滤计数。
21. `/api/skills` overview 聚合必须保持 used-only 与窗口语义不变,并避免无必要的 raw `skill_uses` 全历史逐行扫描;
    实现应优先使用 SQLite 组合索引与 SQL 预聚合降低 Python 侧处理行数。性能验证以同一环境 before/after 为准:
    `/api/skills?w=7d` TTFB/总耗时 P95 应小于 800ms,且相对变更前同环境采样至少 3x 改善;若生产库规模或生产
    `EXPLAIN QUERY PLAN` 不可得,不得声称已验证生产 P95,只能报告可复现环境和合成样本数据。不得优先用缓存掩盖聚合根因;
    只有 SQL/索引优化后仍无法达到性能目标时,才允许引入 `/api/skills` 短 TTL 缓存。若引入缓存,默认 TTL 为 5 秒
    (允许 3-10 秒),缓存键必须归一化 `days/w/wstart/wend/rt/src/scope`,且缓存容量必须有上限。
22. `/api/operator/{name}` 只统计该操作员的 `mode=used` 记录,不输出 equipped 指标;返回指标、按 skill 分段日级序列、
    skill 排行(含来源)、runtime 分布和最近 50 条记录。
23. `/api/state` 与 `/api/state/stream` 必须共用同一份进程内快照缓存,缓存 TTL 由 `TF_STATE_TTL`(秒,float)配置,默认 1.5;
    前端可见的所有字段(包括 `now`/`sessions`/`feed`/`leverage`/`skills`/`shim`/`totals`)
    可以在一个 TTL 窗口内相同;不允许任何路径(包括 `/api/skills`、`/api/skill/{name}` 等)
    依赖"`/api/state.now` 必须是请求当下时间"的假设。
    快照重算必须具备 single-flight 保护:同一进程内同一时刻最多一个执行单元运行 `_snapshot`;缓存仍有效时直接复用;
    缓存过期但已有重算在途时,若旧缓存存在,其它请求可返回旧缓存(stale-while-revalidate);首次无缓存且已有重算在途时,
    其它请求等待该次重算结果。
24. `/api/state/stream` 必须由 board 域统一 broadcaster 复用缓存与 single-flight 结果,不得每个 SSE client 各自独立重算。
    写侧在真实事件行插入、纯心跳 batch flush 更新 `last_seen`、profile/skill/shim version 发生实际写入、
    管理清理或恢复完成后标记 state dirty;服务端合并短时间内的多次 dirty 后最多重算一次快照并推送。
    慢 SSE client 不得拖慢全局推送;实现优先保留最新快照,允许丢弃该 client 队列里的旧快照。
25. `/healthz` 必须是 async handler,响应体固定 `ok`,不依赖 DB 或重模块状态;其响应时间不得受
    `/api/state` 聚合压力影响。在 100 并发 `/api/state` 期间,`/healthz` 单请求响应时间应 < 50ms。

## 部署/运维
- `TF_STATE_TTL`:`/api/state` 与 `/api/state/stream` 共用快照缓存 TTL(秒,float),默认 `1.5`。区间建议 `0.5~3.0`。
- Docker healthcheck 配置目标:`Timeout=10s`、`Retries=5`、`Interval=30s`、`StartPeriod=10s`。
  配置入口取决于部署方式;根目录 `compose.yml` 托管默认值,若由 Coolify UI 覆盖,以 Coolify 配置为准。
- uvicorn `--workers` 默认 1;启用多 worker 前必须先解决 `_catalog_loop` 多进程并发拉取与写
  `catalog_cache` 表的潜在竞争,该事项需走独立 change。

## 前端规则(MUST)
- 看板 state 数据读取优先使用 `/api/state/stream` SSE;SSE 不可用、断开或解析失败时回退到 `/api/state`
  adaptive polling,取不到时退回内置演示数据并显示"未连接服务端"。
  fallback polling 首次加载立即请求;页面可见且 `totals.live > 0` 时约 3 秒刷新;页面可见且 `totals.live == 0`
  时约 15 秒刷新;页面隐藏时暂停或降到约 60 秒刷新;任一时刻不得并发叠加多个 `/api/state` 请求。
  TopBar、Pods、Agents 与 AgentDetail 必须复用同一份 state 数据源,不得各自建立独立 `/api/state` 轮询。
- 视图:Pods 看板(按 operator 分组,人=调度员,其 agent=编队)/ Agents 列表 / SKILLS 总览 / 治理详情 / Skill 详情 / Operator 详情。
- 路由:Pods 看板 `/`;Agents 列表 `/agents`;治理详情 `/agent/:key`;SKILLS 总览 `/skills`;新增发布 Skill 列表 `/skills/new`;SKILLS 记录页 `/skills/evidence`;SKILLS 治理线索详情 `/skills/clues/:kind`;
  Skill 详情 `/skill/:name`;Operator 详情 `/operator/:name`;刷新、前进后退、复制链接必须保持当前视图。
- SKILLS 总览筛选绑定到 URL search params:`w`(`today`/`this_week`/`last_week`/`7d`/`14d`/`30d`/`90d`/`custom`)、
  `wstart`、`wend`、`cmp`、`topn`(`5|8|10|20`)、`hz`、`sel`、`rt`、`src`、`q`、`sort`、`dir`、`view`(`skill`/`operator`)、`scope`(`all|new`)。
  旧参数 `win` 保留向下兼容并在没有 `w` 时映射为 `w`;旧参数 `lens` 保留但不再驱动 UI。筛选变化使用 replace,
  不污染浏览器历史;详情跳转使用 push。`cmp` 保留为向下兼容 no-op,不得驱动可见开关。`/skills` 无 `w` 且无合法旧 `win`
  参数时前端默认 `w=7d`;无效 custom 也回退 `7d`。
- Pods 看板不再展示 Skills 排行区;`/api/state.skills` 字段保留用于协议兼容,前端看板不消费。
- SKILLS 总览进入时加载 `/api/skills`,之后低频刷新;加载失败显示错误态。柱状图横轴按服务端返回的 `window.start..window.end`
  逐日铺满;旧 `days` 兼容窗口等价于以服务端 `today` 为右端的最近 N 天。每一天占一个槽位,有 used 数据才长堆叠柱,
  无数据留空槽;只有 `window.end == today` 的最后一列标记"今日进行中"。前端取窗口内使用量 Top N(`topn`,默认 8)分色,
  其余合并为"其它"段;窗口选择器不含"全部"档。
- `/skills`、`/skills/new`、`/skills/evidence`、`/skills/clues/:kind`、`/skill/:name` 与 `/operator/:name` 不得被全局 `/api/state` 首包阻塞;这些路由必须先挂载自身 loading/skeleton,
  并行请求 SKILLS API。Pods、Agents 与 AgentDetail 仍复用 `/api/state` gate。SKILLS GET 请求层必须按完整 URL 做 in-flight 去重和 ETag revalidate;
  可把同 URL 已校验 payload 作为返回页/刷新过渡态先展示,但后台仍必须向服务端校验,不得用前端 TTL 命中跳过请求。刷新或筛选切换时优先保留旧列表并用 refreshing/loading 状态表达后台刷新中,
  不得把旧数据伪装成已完成刷新结果。
- SKILLS 总览采用证据导向仪表盘结构:控制条 → 当前时间窗变化(8 格,标题由时间窗 i18n label 派生,每格可追证据) → 问题线索(5 项) →
  主分析区(排行 Bar/操作员排行 + 每日使用趋势图,按窗口长度切布局) → 待处理线索治理行 →
  归因 Donut(来源+runtime) → 明细表+抽屉 → 公司库采纳漏斗(下沉、默认折叠)。手机首屏优先呈现问题线索和待处理线索,
  不得让完整筛选表单占据第一屏主体。
  首次加载只保留控制条和 skeleton/Empty;增量刷新保留旧数据并在标题 `cnt` 标记 loading/error。
- 控制条承载视角切换、时间窗、搜索、runtime、来源、Top N、隐藏 0 使用和加载状态。不得显示环比开关;previous-window 变化默认始终展示。
  视角切换使用 32px 高分段按钮,
  选中态使用品牌色 `--brand`;切换视角不重置时间窗。时间窗口选项与首屏核心文案必须随当前中英文语言切换,
  不得直接把 `7d` / `30d` 等 query key 作为用户可见选项文案。桌面与平板下搜索 Skill 名字段内部必须单行展示:
  label 与 input 同行、label 不换行、input 使用剩余宽度。公司库漏斗常驻且始终使用 skill/catalog 口径。
- 顶部导航的 `+N 7天新发现` 必须可键盘聚焦并跳转 `/skills?w=7d&scope=new`;顶部 `N Skill 资产`
  必须使用 used-only distinct skill 口径,不得暗示安装量或已发现量。手机端可隐藏顶部新增数字,但 `/skills`
  首屏控制摘要旁必须提供一键/键盘可达的新增名单入口。
- 按 Skill 视角「当前时间窗变化」8 格口径:总触发次数、公司库覆盖率、活跃操作员数、新增发布 Skill 数、未收录使用占比、闲置 skill 数、
  装了没用比例、Top3 集中度。每格必须提供证据入口,但摘要格只展示短结论,不得直接铺长 skill/operator 名单;
  长名单只能出现在待处理线索、`/skills/evidence` 或展开详情中。若必须露对象,只能露 1 个短名且超长名截断,
  不能用 `/` 拼接多个长名。证据入口使用 icon button,默认态为浅灰弱提示色,悬浮和键盘 `focus-visible` 时恢复高亮色,
  并通过 tooltip / `aria-label` 暴露 `查看记录`、`查看名单` 等语义,不得在每格重复显示可见文字「证据」。每格核心数值与证据 icon 必须在同一行,不得让 icon 被挤到下一行。
  标题必须由当前时间窗 i18n label 派生,例如「上周变化」「本周变化」「近 7 天变化」或 `Last 7 days changes`。
  除闲置 skill 数和装了没用比例两个快照指标外,其余默认展示本期 vs 上期同长度窗口 delta;
  `previous=0,current>0` 显示 `+∞%`,两边 0 显示 `—`。按人视角换为 operator 口径摘要,至少包含使用记录、活跃操作员、
  活跃率、人均 skill、人均会话、Top3 集中度、runtime 覆盖和来源覆盖。
- 按 Skill 视角「问题线索」5 项:未收录占比、装了没用比例、公司库覆盖率、Top3 集中度、新增发布 Skill。每项主句优先对象驱动或事实驱动,
  百分比只作次级说明,不得作为唯一主句。问题线索卡不得在首屏直接渲染具体 skill 名名单;具体 records/items/names
  只能出现在待处理线索、证据页或详情抽屉中。每项只展示当前事实值和 icon 证据入口,不得显示「看未收录 used 名单」、
  「看已装未用名单」「看集中使用分布」等可见动作文案;不得显示 `良好`、`偏高`、`需关注` 作为考核标签,
  也不得使用红绿箭头、达成率或庆祝式增长文案;其职责是提示"哪里断了、下一步看哪份名单"。
  「新增发布 Skill」入口必须跳 `/skills/new`,不得跳 `/skills/evidence?kind=avg_per_session`。
  按人视角问题线索换为 operator 使用信号,至少包含活跃率、人均 skill、Top3 集中度、runtime 覆盖和活跃操作员数;
  使用信号同样只展示当前事实值和 icon 证据入口,不得显示「看操作员名单」「看 runtime 分布」等可见动作文案。
- 主分析区按当前时间窗口长度切换布局:短窗口(`today`、`this_week`、`last_week`、`7d`、`14d`、有效 `custom<=14天`)
  在桌面 `>1080px` 下使排行 Bar/操作员排行与每日使用趋势图左右并列并占满整宽,同排两张卡片外框底边须对齐;长窗口(`30d`、`90d`、有效 `custom>14天`)
  在桌面 `>1080px` 下使排行 Bar/操作员排行独占一行、每日使用趋势图独占下一行。按 Skill 视角排行 Bar 显示 Top N +
  长尾「其他 N 个 skill」聚合,值口径为当前窗口 used sessions;排行长 skill 名在桌面默认可读,不得只依赖 hover/title,
  窄屏下不得造成根级横滚或与数值、记录动作、条形轨道重叠,必要时用换行、软断行、`title`/`aria-label` 或行详情提供完整可读路径;
  点行设置全局 `sel`,再点取消,并与每日使用趋势图和 Donut 联动。
  按人视角主分析区显示操作员排行表并继续下钻 `/operator/:name`,不得新增与行跳转冲突的选中态;排行和趋势图继承当前
  `w/days` 以及定义证据范围的 `runtime/source`,但不得继承 skill 搜索词、Skill Top N、隐藏 0 使用或选中 skill。趋势图展示当前筛选后的 operator 分布。
- 按 Skill 视角待处理线索为独立治理行,3 组固定顺序:有使用但未收录、装了当前时间窗内没用、收录但零装机。每一组必须呈现为独立区块;
  `有使用但未收录` 是第一优先线索,必须展示 Top items、触发次数和至少一个查看动作。按人视角待办换为重度使用者、近 7 天沉睡、低覆盖使用者,
  同样使用独立治理行,不得重新挤占排行或趋势图宽度。
  待处理线索行正文只讲事实且按 kind 使用独立模板:`untracked` 显示 `N 条记录 · M 人 · 上次使用 MM-DD`,不得重复展示 `非公司库`;
  `idle` 显示 `N 人安装 · 当前窗口 0 次 · 上次使用 MM-DD|从未使用`;`zero_install` 显示 `0 人安装 · 收录 MM-DD`。
  桌面主操作必须收敛为查看图标 + 可见文字 `忽略`,不得继续用 `×` 作为忽略按钮;界面不得使用可见文案 `找人`。
  mobile 行点击进入 clue 详情,次级动作进入 `...` 菜单。每组 Top 8 + 查看全部/忽略入口;行动作必须是非破坏操作。
  分组摘要不得使用 `8/48` 这类裸分数,必须显示为 `48 个未收录,展示前 8` 或 `5 个零装机,已全量展示` 这类明文。
  忽略只允许当前页面内临时隐藏,刷新、重新进入页面或重新 mount 后恢复;不得写入 localStorage、sessionStorage 或后端。
- `/skills/clues/untracked`、`/skills/clues/idle`、`/skills/clues/zero-install` 是三类待处理线索的用户可见详情页,底层可复用
  `/api/skills/evidence` payload。旧 `/skills/evidence?kind=untracked|idle|zero_install` 链接必须兼容并重定向到对应 clue 路由。
  `/skills/clues/untracked` 必须第一屏先展示 Top Operators,并显示 `records/total · percent`,分母是当前 clue 记录总数;
  当 URL 已带 `skill=` 时必须隐藏 Top Skills。`/skills/clues/idle` 必须第一屏展示安装者名单,字段至少包含
  skill、安装人数、安装者、上次使用;不得展示 Top Skills / Top Operators。`/skills/clues/zero-install`
  必须第一屏展示零装机名单;不得展示 Top Skills / Top Operators。clue 详情页筛选 chip 必须展示用户语义,
  不得暴露 `window_start`、`window_end`、`src: non_catalog` 等内部字段名或枚举值;相关用户可见文案必须使用
  `记录 / 名单 / 分组`,不得使用 `证据` 描述这些线索。
- `/skills/evidence` 必须保留当前 SKILLS 时间窗和筛选语义;刷新、复制链接和前进后退必须保持 evidence `kind` 与筛选。
  证据页必须展示返回 SKILLS 的入口、当前窗口、紧凑上下文摘要、icon toolbar 或紧凑 tabs、原始记录表或名单证据。
  证据页不是另一个 dashboard,第一职责是回答「这批事实到底是什么」:有 raw records 的 evidence kind
  (`total`、`untracked`、`runtime`、`source`、`top3`、`coverage`、`operators`、`avg_per_session`)默认停在「原始记录」,
  1440x900 第一屏必须露出 records 表头和前几行;无 raw records 的 evidence kind (`idle`、`unused_ratio`、`zero_install`)默认停在「名单」,
  1440x900 第一屏必须露出名单表表头和前几行。
  摘要不得固定渲染 `RECORDS / SKILLS / OPERATORS / SESSIONS / UNTRACKED / COMPANY` KPI cards,必须按 kind 收敛为上下文句。
  `kind=total` 的未收录数量必须作为总证据摘要里的上下文切片展示,例如 `其中 N 条来自未收录 skill`,
  并能跳转到保留当前窗口和筛选语义的 `kind=untracked`;不得单独以 `UNTRACKED N` 指标卡形式站着。
  `Top skills / Top operators` 是辅助分组,不得排在主表之前把 raw records 或名单表挤出第一屏;若并排导致主表过窄,
  分组必须放到主表下方,主表至少要能读清 `time / skill / operator / runtime / source`。
  原始记录的具体时间 `first_seen` 按浏览器本地时区展示;缺失 `first_seen` 时按服务端 `day` date-only 语义展示,
  规则与 `/skill/:name`、`/operator/:name` 最近记录一致。最近记录/证据记录无下钻目标时不得呈现可点态。
- 归因 Donut 两张:按来源为双层 Sunburst(内环=已收录 vs 未收录;外环=own/meta/external/non_catalog),按 runtime 为单层 Donut;
  权重均为当前窗口 used sessions。零值扇区不画;来源父子角度一致性容差 <0.5°;点击来源扇区联动全局 `src`。
- 明细表列为名称/来源/当前时间窗/上期/Δ%/用户/runtime/趋势/最近,当前时间窗列的可见文案必须使用对应时间窗 label 派生。
  按 Skill 视角点行默认打开右侧抽屉而不是直接跳详情;
  抽屉显示 KPI4 格(当前时间窗触发、上期变化、活跃者、装机数)、14/30/90 趋势切换、runtime 拆分、使用操作员 Top、
  装备但未使用差集和最近 5 次触发,并提供「前往详情页」按钮作为 `/skill/:name` 逃逸口。
- SKILLS 柱状图悬停某日列时,该列高亮、其余列降透明,并显示锚定柱子的明细浮窗(日期、当天各 skill 降序明细、
  Top8 外并"其它"、合计);浮窗锚定柱子几何而非光标——默认贴柱子右侧、顶部对齐图表绘图区顶,
  碰视口右边界翻到柱子左侧、碰下边界上移贴视口底。今日列作为最后一格,以进行中视觉区分并在浮窗标注。
  移动端点击列显示浮窗,点击别处或横向滚动图表时关闭。整窗全空或筛选后全空时显示空态,不渲染一排空轴。
- Skill 详情趋势图固定最近 30 个 `Asia/Shanghai` 统计日逐日铺满(右端同服务端 `today`),used 柱与 equipped 折线分列展示,
  不相加;空天留白,今日列进行中,悬停/点击浮窗显示 used/equipped,且使用与 SKILLS 总览一致的柱子锚定、
  视口翻转和点击别处关闭规则。
- 单操作员详情的 skill 排行在界面上呈现为「使用 Skill 排行」,默认按最近 7 天使用次数降序(平手按累计、再按名称);
  此默认仅作用于操作员详情页内,不改变 SKILLS 总览页按当前时间窗 `sessions_window` 降序的口径。
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
- `/skills` 在平板下必须保持单列主内容流:控制条 → 当前时间窗变化 → 问题线索 →
  排行/操作员排行 → 趋势图 → 待处理线索 → 归因 → 明细 → 公司库漏斗。漏斗下沉到底部,不得在窄屏下挤到排行右侧导致主体过窄。
  `/skills` 在手机下必须优先首屏判断流:控制摘要 → 问题线索 → 待处理线索 → 排行/操作员排行 → 趋势图 →
  当前时间窗变化 → 归因 → 明细 → 公司库漏斗。
- `/skills` 的控制条在手机下默认折叠为一行摘要,摘要至少包含当前窗口、视角、runtime/source 筛选摘要和筛选入口,
  例如中文 `7 天 · 按 Skill · 全部 runtime/source · 筛选` 或英文 `7 days · By skill · all runtime/source · Filter`;
  `scope=new` 时摘要须体现新增名单态,并在摘要旁显示新增名单入口;
  完整筛选控件只能在用户展开后显示。
  展开后搜索框和所有下拉控件宽度为 100%;checkbox 控件保持 16px 级别,不得被通用输入样式拉伸;平板下允许换行但不得撑出页面横向滚动。
- `/skills` 的趋势图日期轨道长度与图表视窗尺寸解耦:短窗口(`today`/`this_week`/`last_week`/`7d`/`14d`/有效 `custom<=14天`)
  必须填满自身面板可视宽度,不得只按固定 30d 单日槽宽渲染成右侧窄条,同时柱体宽度必须有上限,避免 `today` 单柱过粗;
  长窗口(`30d`/`90d`/有效 `custom>14天`)使用固定单日槽宽(按 30d 观感定标),允许在 `.chart-box` 内部横向滚动,
  并默认显示最新日期。页面根不得因趋势图横向滚动。
- `/skills` 的排行 Bar、Skill 明细表和按人主榜在手机下须从桌面表格/横条压缩为摘要行或单列条:
  首行展示主语名称与来源/占比,后续行展示当前时间窗、上期、Δ%、用户/会话、最近使用日等关键指标。
  排行 Bar 摘要行中的长 skill 名必须允许断行或保留完整可读路径,数值、记录动作和条形轨道不得重叠。
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
- 同一 session 对同一 skill 重复上报 used,或多个 session 上报同一 skill used → `/api/state.leverage.assets`
  只按 distinct skill 计 1;当前 7 天内首次 used 时 `skills_week` 也只计 1。
- 仅 profile installed、仅 `skills_seen` 或仅 `skill_mode=equipped` 的 skill → 不计入 `/api/state.leverage.assets`
  或 `skills_week`。
- 某 skill 首次 used 在 9 天前、当前 7 天再次 used → 不出现在 `/api/skills?w=7d&scope=new`,但出现在默认
  `/api/skills?w=7d`。
- 某 skill 首次 used 在当前 7 天,且 alice/bob 各有一个会话 → `/api/skills?w=7d&scope=new`
  的 table 只含该 skill,operator_table 只含 alice/bob,该 skill `previous_sessions=0`。
- `GET /api/skills?w=7d&scope=weird` → 400。
- catalog 中 `own` 或 `meta` skill 的 `published_at` 落在当前 7 天窗口,且没有任何 `skill_uses`
  记录 → `/api/skills?w=7d` 的 `period_comparison.current_published_skill_count` 计入该 skill,
  `published_skills[]` 包含该 skill,且该项 `window_sessions=0`。
- catalog 中 `meta` skill 的 `published_at` 落在上一同长窗口 → 当前窗口
  `period_comparison.previous_published_skill_count` 计入该 skill,但当前窗口 `published_skills[]` 不包含它。
- catalog 中 `external` skill 的 `published_at` 落在当前窗口,或 catalog item 缺失/非法 `published_at`
  → `/api/skills` 仍返回 200,且不计入 `current_published_skill_count` 或 `published_skills[]`。
- 造数据:7 天内 own used 6、external used 2、非公司库 used 4、非公司库 equipped 3 →
  `/api/skills?days=7` 的 `governance.untracked_usage.total_sessions=12`、`used_sessions=4`、
  `ratio≈0.333`,Top 不含 external/equipped。
- 造数据:7 天内 `alpha own used=2`、`beta external used=1`、`ghost non_catalog used=3`、`ghost equipped=2` →
  `/api/skills/evidence?kind=total&w=7d` 的 `summary.records=6`,records 不含 equipped;
  `/api/skills/evidence?kind=untracked&w=7d` 的 `summary.records=3`,records 只含 `ghost`,不含 `beta` 或 equipped。
- `/api/skills/evidence?kind=total&w=7d` 的 `summary.records` 与同一窗口 `/api/skills?w=7d`
  响应里的 `period_comparison.current_sessions` 相同。
- 从 `/skills?src=own&w=7d` 点击 `有使用但未收录` 的查看入口 → clue 页仍展示 non_catalog used records,
  payload 的 `ignored_filters` 标明 `src=own` 被 `kind=untracked` 覆盖。
- `days=30` 包含更多历史非公司库 used 时,`governance.untracked_usage` 的分母、分子、Top 列表随窗口扩大更新。
- 造安装态:某 own skill 装于 ≥1 个 agent 且 30 天零使用 → funnel 闲置名单含之。
- 造安装态:`idle-own` 在 profile installed,窗口内未 used,且 catalog type 为 `own` →
  `/api/skills/evidence?kind=idle&w=7d` 的 `items` 含 `idle-own`,并带 `installers` 与 `installers_detail`。
- 造公司库收录但未安装态:`meta-tool` 在 company catalog `meta` 中,未出现在 profile installed →
  `/api/skills/evidence?kind=zero_install&w=7d` 的 `items` 含 `meta-tool`,`installers=0`,`installers_detail=[]`。
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
- `w=7d` 或 `days=7` → `operator_daily` 仅含最近 7 个 `Asia/Shanghai` 统计日;`operator_table.sessions_window`
  使用同一当前窗口,并提供上一同长窗口 `previous_sessions`;兼容的 7 天 / 30 天 / 累计字段仍保留。
- 造数据:operator A 最近 7 天 3 条 used、operator B 最近 30 天 10 条但最近 7 天 1 条 →
  `/api/skills?w=7d` 的 `operator_table` 中 A 排在 B 前,且 A 的 `sessions_window=3`。
- 同一造数查 `/api/skills?w=30d` → 操作员排序可随 30 天窗口变化。
- `/api/skills?w=7d&rt=codex&src=own` → `operator_table.sessions_window`、`operator_daily`、`window_runtime_counts`
  与 `window_source_counts` 只统计当前窗口内 `codex + own` 交集。
- `/skills?view=operator&w=7d&rt=codex&src=own` → 操作员排行使用当前窗口内 `codex + own` 计数;改变 skill 搜索词、
  Skill Top N、隐藏 0 使用或选中 skill 不改变操作员排行。
- 单操作员详情的 skill 排行行点击 → 进入对应 `/skill/{name}` 详情。
- `GET /api/operator/不存在的人` → 404。
- SKILLS 总览 Skill 明细表默认按当前时间窗内会话数降序,平手按累计;按人主表按 `sessions_window` 降序,
  平手按累计、再按操作员名。
- 进入某操作员详情 → 左侧为 runtime 分布、右侧为「使用 Skill 排行」,排行默认按 7 天列降序。
- /skills 视角切换位于控制条内,内容行按钮为 32px 高分段控件;切换后整页换主语且说明文案随之变化,时间窗不重置。
- `/skills` 无窗口参数 → 前端默认 `w=7d`。
- 1440x900 中文/英文分别打开 `/skills?view=skill&w=7d&topn=8` → 时间窗口选项、移动摘要等窗口文案随当前语言变化,
  仍使用同一个 `w=7d` query;英文模式下控制条、当前时间窗变化、问题线索、待处理线索和 icon action 可访问名称不得混入中文硬编码。
- `/skills?view=skill&w=last_week` 中文首屏显示「上周变化」,英文首屏显示 `Last week changes`,不出现裸 `过去 W 变化`。
- `/skills` 工具栏不得显示环比开关;KPI 卡仍显示 previous-window delta 或空态。
- 1440x900 打开 `/skills?view=skill&w=7d&topn=8` → 搜索 Skill 名字段 label 与 input 同行,
  `搜索 skill 名` / `Search skill` 自身不换行;`总触发次数` / `Total triggers` 的核心数值和证据 icon 位于同一行。
- 1440x900 打开 `/skills?view=skill&w=7d&topn=8` → 显示「近 7 天变化」8 格、问题线索 5 项;
  主分析区中排行 Bar 与每日使用趋势图左右并列,每日使用填满右侧面板;待处理线索位于其下一行且每类为独立区块;
  下方还有两张 Donut、明细表和下沉漏斗。
- 固定 `/api/skills?w=7d` fixture 让 `openspec-driven-development` 成为榜首,1440x900 打开 `/skills?w=7d` →
  使用排行首行默认可见文本完整包含 `openspec-driven-development`,不能只靠 `title` 或 `aria-label` 才能读到。
- 固定同一 fixture,1440x900 打开 `/skills?w=7d` → `.skills-rank-panel` 与 `.skills-trend-panel` 外框
  `getBoundingClientRect().bottom` 差值不超过 `4px`;1280x800 截图作为防回归记录。
- 固定同一 fixture,375x812 打开 `/skills` → `document.scrollingElement.scrollWidth <= clientWidth`,
  排行首行名称、数值、记录动作和条形轨道 bounding box 不重叠;若可见文本截断,完整名称存在于 `title`、`aria-label` 或行详情。
- 将榜首替换为 `openspec-driven-development-with-extra-long-suffix-0123456789`,375x812 与 600px 宽度打开 `/skills?w=7d` →
  页面根无横向滚动,关键元素不重叠,且完整名称有可读路径。
- 1081x800 打开 `/skills?w=7d` → 仍按桌面短窗口左右布局且页面根不溢出;1080x800 打开同 URL →
  降级为单列,不得保留造成空白或横滚的等高副作用。
- 1280x800 打开 `/skills?view=skill&w=14d` → 主分析区仍为排行 Bar/每日使用左右布局,每日使用填满右侧面板,不出现右侧窄条或大面积空白。
- 1440x900 打开 `/skills?view=skill&w=30d` → 排行 Bar 独占一行,每日使用趋势图在其下方独占一行,待处理线索再下一行独立呈现。
- 1440x900 打开 `/skills?view=skill&w=90d` → 每日使用趋势图全宽区域内部横向滚动,默认显示最新日期,页面根无横向滚动。
- 1440x900 打开 `/skills?view=operator&w=7d` → 操作员排行与每日使用按短窗口规则左右布局;点击操作员排行行进入 `/operator/:name`;
  待处理线索独立行不拦截行跳转;排行与趋势图正常渲染,短窗口等高样式不得破坏行点击/键盘下钻。
- `/skills?view=skill&w=7d` 首屏不显示旧 KPI / 健康评分语义文案。
- `/skills?view=skill&w=7d` 的摘要格不得直接渲染 `openspec-driven-development / tranfu-website-design / strategy-first-development` 这类长 skill 串。
- `/skills` 问题线索卡不出现 `openspec-driven-development`、`figma-implement-d`、`coolify-deploy` 等具体 skill 名;
  点击 icon 仍进入对应 evidence 明细。
- 375px 手机宽度下,问题线索的跳转 icon 与文字行垂直居中,页面根无横向滚动。
- `/skills?view=skill&w=7d` 的摘要格不得重复出现多个可见文字「证据」入口;证据入口应是 icon button,并有可访问名称。
- 点击 `/skills` 首屏 `总触发次数` 的证据入口 → 跳到 `/skills/evidence?kind=total&w=7d...`,证据表显示当前窗口 records。
- 点击 `/skills` 首屏 `新增发布 Skill` 的记录入口 → 跳到 `/skills/new?w=7d...`,页面展示同一窗口内按
  `published_at` 统计的新发布公司库 skill 列表;无 used 详情的行仍保留可读名单,不隐藏。
- 点击 `/skills` 首屏 `有使用但未收录` 的证据 icon 或 mobile 待处理线索行 → 跳到 `kind=untracked`,证据表只展示非公司库 used records。
- `/skills?view=skill&w=7d` 的 `待处理线索` 不得显示可见文案 `找人`;对应查看 action 的可访问名称为 `查看记录`、`查看名单` 或同义语义。
- `/skills?view=skill&w=7d` 的 `待处理线索` 三组摘要不得显示 `8/48`;必须显示明文总数和展示数量。
- `/skills?view=skill&w=7d` 的 `待处理线索` 忽略按钮必须显示文字 `忽略`,不得使用可见 `×`。
- `待处理线索` 点击忽略后当前页面隐藏,刷新或重新 mount 后恢复;前端不得调用 localStorage/sessionStorage 保存该状态。
- `/skills?view=skill&lens=untracked` 中 `lens` 为 no-op 兼容参数;未收录使用通过当前时间窗变化、问题线索和待处理线索 A 组呈现。
- 1440x900 打开 `/skills/evidence?kind=total&w=7d` → 第一屏露出 records 表头和前几行;摘要包含
  `其中 N 条来自未收录 skill` 上下文切片,且该切片可跳转到 `/skills/evidence?kind=untracked&w=7d...`。
- 1440x900 打开 `/skills/clues/untracked?w=7d&skill=coolify-deploy` → 第一屏先露 Top Operators,operator 行显示
  `5/7 · 71%` 这类占比,且不显示 Top Skills。
- 1440x900 打开 `/skills/clues/idle?w=7d&skill=write-spec` → 第一屏显示安装者名单,能看到安装该 skill 的 operator / agent / runtime,
  且不显示 Top Skills / Top Operators。
- 1440x900 打开 `/skills/clues/zero-install?w=7d` → 第一屏显示零装机名单,且不显示 Top Skills / Top Operators。
- 打开旧链接 `/skills/evidence?kind=idle&w=7d&skill=write-spec` → 前端跳转到 `/skills/clues/idle?w=7d&skill=write-spec`。
- 从 `/skills?src=own&w=7d` 点击未收录线索 → 进入 `/skills/clues/untracked?w=7d&src=non_catalog...`;页面 chip 显示
  `来源:未收录` 或等价文案,不显示 `non_catalog`。
- `/skills/evidence` 中 `Top skills / Top operators` 不得让主表列宽小到无法读清 `time / skill / operator / runtime / source`;不足时分组下置。
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
- 375x812 打开 `/skills?view=skill&w=7d` → 页面根无横向滚动,控制条默认显示一行摘要
  `7 天 · 按 Skill · 全部 runtime/source · 筛选` / `7 days · By skill · all runtime/source · Filter`
  或等价实际筛选摘要,第一屏能看到「问题线索」和「待处理线索」的实质内容,
  不先展示完整筛选表单;排行摘要行之后显示 7 天趋势图;趋势图填满自身面板可视宽度但柱体不过粗;
  Skill 明细行为移动摘要/单列样式,点 Skill 明细行打开全屏抽屉。
- 375x812 打开 `/skills?view=skill&w=30d` → 页面根无横向滚动,30 天趋势图只在 `.chart-box` 内横滚,
  待处理线索位于首屏判断流内,公司库漏斗位于页面底部。
- 375x812 打开 `/skills/evidence?kind=total&w=30d` → 页面根无横向滚动,记录表以摘要行展示。
- 375x812 打开 `/skills?view=operator&w=30d` → 页面根无横向滚动,按人榜为摘要行且整行点击进入 `/operator/:name`,
  公司库漏斗仍位于页面底部。
- 768x1024 打开 `/skills` → 主视图上下堆叠,Donut 上下堆叠,筛选条可换行但页面无横向滚动,
  搜索字段内部不拆行,KPI 为 4×2,表格/图表横滚限制在组件内部。
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

## Agents 运营看板（2026-07-13）

- `/api/state` 与 `/api/state/stream` 顶层可返回 `agent_overview`。对象包含 `today`、90 天 `days[]`、`summary`、`daily[]`、`runtime[]`、`operator[]`；日期为服务端 `Asia/Shanghai` 统计日，时长为秒。
- `agent_overview` 的聚合以最终身份卡片为单位，遵守 `operator + agent||runtime` 合并规则；`summary` 的 runs/success/errors/blocked 沿用 Agent card 的 quality 口径。现有 state 字段保持兼容，缺失 `agent_overview` 时前端由 sessions 降级构建。
- `/agents` 桌面/平板信息流为控制条 → 单一八卡时间窗变化/快照 → 问题线索 → 操作员/运行终端排行与活跃趋势 → Agent 明细；控制条支持 `q`、`status`、`signal`、`rank`、`w`、`wstart`、`wend`、`rt`、`op`、`sort` URL 参数，变化使用 replace，不得使用浏览器存储。
- 问题线索至少包含当前异常/阻塞、Shim outdated/unknown、最近 14 天无活跃、至少 3 runs 且成功率低于 80%；线索是事实提示，不作为评分或成本指标。
- Agent 明细为可扫描的响应式表格，保留身份、操作员、运行终端、当前状态、任务/步骤、当前选择窗口的活跃时长与活跃天数、累计质量、Skill、MCP、Shim 和最近活跃；整行键盘可达并进入 `/agent/:key`。桌面显示完整列，平板只允许表格容器内部横滚，手机以同一语义表格行压缩为摘要，不得造成页面根横向滚动。
- `/agents` 支持中英文、system/light/dark 主题和 `>1080px` 桌面、`601–1080px` 平板、`≤600px` 手机布局；新增 Agents 前端状态不得持久化。

### Agents 控制条与八卡事实区

- 顶部 frame 标题为“控制条”，右侧说明随 `rank=runtime|operator` 显示当前观察视角，不在该 frame 重复页面标题。控制条同时承载“操作员｜运行终端”视角切换、搜索、状态、时间窗、运行终端、操作员与排序筛选；操作员必须排在运行终端之前并作为默认选中项，手机默认只显示一行折叠摘要。
- 时间窗复用 Skills 的 `today`、`this_week`、`last_week`、`7d`、`14d`、`30d`、`90d`、`custom` 选项，缺省语义为 `today`，通过 `w/wstart/wend` 保持在 URL。
- `w=custom` 的 `wstart/wend` 可分别增量写入 URL；Unix instant 转 Agents 统计日时使用 `Asia/Shanghai`，不可按 UTC 日期截断造成跨日偏移。排行榜视角使用 `rank=runtime|operator`，缺省为 `operator`；默认操作员视角省略 `rank`，运行终端视角必须显式写 `rank=runtime`。
- 时间窗变化与稳定摘要合并为单一 Skills 同构八卡网格，不得保留第二个摘要 frame、事实带或次级行。八张卡固定为：窗口活跃 Agent、窗口活跃时长、Agent 总数、操作员数、当前在线/运行中、本周活跃、运行质量、待处理 Agent。frame 标题与 Skills 使用同一窗口派生规则，直接显示“今天变化 / 本周变化 / 近 N 天变化”等完整标题，不得只靠手机会隐藏的右侧 `cnt` 表达窗口。
- 前两卡展示当前窗口、上一同长度窗口与 delta；活跃序列以 `agent_overview.today` 为统计日右端，上一窗口不可用或两边均为 0 时显示 `—`，前期为 0 且本期大于 0 时显示 `+∞%`。其余六卡展示“快照”：Agent 总数 detail 为当前可见/全部身份；操作员数为当前可见去重值；当前在线 detail 为 live/可见 Agent；本周活跃 detail 保留今日活跃；运行质量 detail 为 success/runs；待处理 detail 为错误/阻塞。
- 八卡的核心数值与右上角真实入口同行，入口默认低权重、hover/focus-visible 高亮并提供真实 `aria-label`。入口动作固定为：前两卡聚焦趋势；Agent 总数聚焦明细；操作员数切 `rank=operator` 并聚焦排行；当前在线写 `status=live` 并清 `signal`；本周活跃写 `sort=window_time`；运行质量写 `sort=success`；待处理写 `status=attention` 并清 `signal`。动作保留无关的 `q/w/rt/op` 等观察范围。
- 八卡在桌面、平板、手机分别为 `8×1`、`4×2`、`2×4`。

### Agents 趋势图、排行与明细表

- 问题线索使用与 Skills health bar 同级的紧凑事实条，每项仍可点击并回填 `status=attention&signal=...`。
- 桌面 `>1080px` 主分析区左侧为操作员/运行终端排行，右侧为当前窗口活跃趋势，两列采用接近 `.95fr / 1.05fr` 的近等宽比例并底边对齐；两张面板使用同构 `//标题 + cnt` header。排行无数据时显示居中标题+说明 Empty。`≤1080px` 退化为单列。
- 排行榜名称、进度条、数量与窗口元信息必须使用跨行一致的列轨道；同一断点下所有进度条从同一水平位置开始。长名称可省略但不得推动单行轨道或造成页面根横向滚动。
- `AgentActivityChart` 消费与 Skills 相同的 `resolveSkillsChartLayout(dayCount, contentWidth)`：`1..14` 日填满面板且柱宽不超过同一上限；`>14` 日只在图表容器内部横向滚动。尾部有数据时定位最新日期；尾部全零但较早日期有数据时定位当前指标最后一个非零日期。Agents 页面根不得出现横向滚动。
- `rank=runtime|operator` 同时驱动排行和趋势分组。趋势逐日按当前视角堆叠，支持活跃 Agent 数/活跃时长指标切换；当前窗口按所选指标取 Top 8 分组，其余聚合为“其他”，缺失 Runtime/操作员归入“未分配”。各堆叠段之和必须等于当日总数，不能因 Top N 截断丢失事实。
- 多日图沿用同等级轴线、220px viewBox、日期抽样、今日斜纹与 hover 降权；逐日透明 hit rect 覆盖整日槽。tooltip 锚定日期槽并在视口边缘翻转，显示当前视角各分组的所选指标分布，并同时保留该日活跃 Agent 总数和活跃总时长；只有窗口右端等于服务端 `today` 时标记“今日进行中”。
- 日期槽支持 pointer hover/click 与键盘 focus，并使用 roving `tabIndex` 使整图只有一个顺序 Tab 停靠点；左右方向键切换日期，Escape/blur 关闭。移动端点击列显示浮层，点击空白或横向滚动关闭。窗口或指标变化时关闭旧 tooltip，并把唯一停靠点与滚动位置同步重置到当前指标最后一个非零日期。
- current/previous 时间窗只有每个统计日都存在于 overview 日序列时才可展示或参与环比；custom 部分落在可用序列之外时视为不可用，不得把缺失日期静默按 0 聚合。
- `today` 只有一个真实统计日：当前指标有正值时显示约 160px 紧凑单日 plot，并在图上方直显当日 Agent 数与时长；不得伪造小时数据。当前指标全窗为 0 时只显示 Empty，不绘制坐标轴、日期或零高度柱。
- Agent 明细表与趋势使用同一组经过 `q/status/signal/rt/op` 筛选的 Agent，并按 `w/wstart/wend` 从身份卡片 `active_days` 重算窗口活跃时长和活跃天数。排序支持最近活跃、窗口活跃时长、窗口活跃天数、累计成功率、累计错误数和名称；旧 URL 的 `sort=today|week` 分别兼容映射到窗口活跃时长/窗口活跃天数。质量必须明确标为累计口径，不得伪装成窗口统计。

### Agents 手机优先级

- `≤600px` 必须按真实 DOM/焦点顺序呈现：控制摘要 → 问题线索 → Agent 明细 → 八卡时间窗变化 → 排行 → 趋势。不得只用 CSS `order` 重排交互节点。
- 断点切换使用媒体查询选择带稳定 key 的 section 顺序，不复制交互节点、不丢失 URL 状态；页面根宽度不得超过视口，长图仍只在自身容器内横滚。

### Agents 可验证行为

- 固定数据库数据后，`/api/state.agent_overview.daily` 长度为 90，日期递增且最后一天等于服务端 `today`；身份跨多个 session 时只在 summary、Runtime、operator 和 daily 中计为一个 Agent。
- `/agents?rt=codex&status=attention&signal=quality` 只显示满足筛选条件的明细行；刷新/复制链接保持筛选，清空筛选回到全量列表。
- Agent 明细行点击或键盘 Enter/Space 进入对应 `/agent/:key`；无匹配 Agent 时显示空态，不渲染空表头。
- 无窗口参数打开 `/agents` 时显示“今天”，且初次渲染不强制写入无关参数；打开 `/agents?w=14d` 时使用当前 14 个服务端统计日与其前紧邻 14 日计算前两卡变化。
- 打开 `/agents?w=last_week` 时默认选中操作员且 URL 不补写 `rank`；选择运行终端后 URL 写 `rank=runtime`，刷新仍保持运行终端视角。中文界面所有面向用户的 Runtime 标签显示为“运行终端”。
- 排行包含不同长度名称时，各行进度条左边界一致；1440、768、375 三档宽度均不得产生页面根横向滚动。
- 1440×900 下八卡一行，排行在左、趋势在右且底边差值不超过 4px；768×1024 下八卡四列且分析区单列；375×812 下八卡两列，问题线索之后先出现 Agent 明细。
- 当前选择指标全窗为 0 时趋势无 SVG 坐标轴；有效单日正值显示 160px 紧凑 plot；7 日正值图无根横滚且柱宽不超过 30px；30 日正值图默认滚到容器末端且根 `scrollWidth <= clientWidth`。
- 图表顺序 Tab 只有一个日期停靠点；方向键切换后 tooltip 显示分组分布并同时保留总人数与总时长，Escape 关闭。KPI、问题线索、排行和 Agent 明细行均保留既定 URL 或下钻语义。

## Skill 双语显示名称（2026-07-14）

### Requirement: Skill slug 与本地化显示名称分离

所有 Skill 统计与治理 API MUST 继续使用 slug 作为稳定 identity。每个含 Skill 的响应对象 MUST 同时提供来自 catalog 或 profile `SKILL.md` 的 `display_name/display_name_zh`；包含多个 Skill 的 payload MUST 另提供以 slug 为键的 `skill_names` 双语映射。服务端不得只返回随 locale 变化的单一 label。中文界面 MUST 按 `display_name_zh → display_name → slug` 显示，英文界面 MUST 按 `display_name → display_name_zh → slug` 显示。显示名不得改变数据库聚合、source 归因、URL、query、颜色、选择器或删除目标。

- catalog 元数据优先于 profile；profile 只补 catalog 缺失字段。
- `/skills` 总览、图表、抽屉、线索、漏斗、CSV 及 `/skills/new`、`/skills/evidence`、`/skills/clues/:kind`、`/skill/:name`、`/operator/:name` MUST 使用同一显示规则。
- Agent profile Skill 与 Admin Skill 清理视图 MUST 使用同一显示规则。
- 名称搜索 MUST 同时匹配 slug、`display_name` 与 `display_name_zh`，包括服务端分页 evidence/clue 查询。
- 可访问名称与 tooltip MUST 不得残留已有可解析显示名对应的 slug。

### Skill 名称可验证行为

- catalog 为 `openspec-driven-development` 返回 `display_name=OpenSpec-Driven Development`、`display_name_zh=OpenSpec 驱动开发` 时，中文界面显示中文名、英文界面显示英文名，但 URL 和 API identity 仍使用 slug。
- 英文名缺失时英文界面回退中文名；两者均缺失时回退 slug，页面与操作仍可用。
- 以 slug、英文名或中文名搜索同一 Skill 均命中；显示名冲突时返回所有匹配 Skill，选择与操作仍按 slug 区分。
