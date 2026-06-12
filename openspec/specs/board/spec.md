# 规格:board(看板与计算域)

事实来源:`server/app.py`(`/api/state`、`metrics`、`leverage`、`reuse_map`、`_snapshot`)与 `dashboard/index.html`。

## 接口
- `GET /api/state` → `{ now, sessions[], feed[], leverage, skills[], shim, totals }`。
- `GET /api/skills?days={7|30|90}` → `{ today, daily[], table[], funnel, catalog }`(SKILLS 总览;`today` 为 UTC 当日,`days` 仅影响 daily,默认 30)。
- `GET /api/skill/{name}` → 单 skill 详情(含 `today`、指标、used/equipped 分列日级序列、runtime/operator 分布、最近记录、来源);查无此名 → 404。
- `GET /api/agent/{key}`(key = `operator::agentOrRuntime`)→ 单 agent 详情(可选)。
- `GET /` → 看板页;`GET /healthz` → `ok`。

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

## 前端规则(MUST)
- 轮询 `/api/state`(约 2s),取不到时退回内置演示数据并显示"未连接服务端"。
- 视图:Pods 看板(按 operator 分组,人=调度员,其 agent=编队)/ Agents 列表 / SKILLS 总览 / 治理详情 / Skill 详情。
- Pods 看板不再展示 Skills 排行区;`/api/state.skills` 字段保留用于协议兼容,前端看板不消费。
- SKILLS 总览进入时加载 `/api/skills`,之后低频刷新;加载失败显示错误态。柱状图横轴按所选 UTC 日窗口逐日铺满:
  右端取服务端 `today`,左端为 `today-(N-1)`,N ∈ {7,30,90};每一天占一个槽位,有 used 数据才长堆叠柱,
  无数据留空槽。前端取窗口内使用量前 8 的 skill 分色,其余合并为"其它"段;时间窗筛选只作用于柱状图,
  主表固定 7 天/30 天/累计三列,漏斗第 3 层固定 30 天;窗口选择器不含"全部"档。
- SKILLS 柱状图悬停某日列时,该列高亮、其余列降透明,并显示跟随光标的明细浮窗(日期、当天各 skill 降序明细、
  Top8 外并"其它"、合计);今日列作为最后一格,以进行中视觉区分并在浮窗标注。移动端点击列显示浮窗,
  点击别处关闭。整窗全空或筛选后全空时显示空态,不渲染一排空轴。
- Skill 详情趋势图固定最近 30 个 UTC 日逐日铺满(右端同服务端 `today`),used 柱与 equipped 折线分列展示,
  不相加;空天留白,今日列进行中,悬停浮窗显示 used/equipped。
- 详情数据优先取 session 的服务端字段(`cf/skills/mcp/integrations/about/...`);演示映射仅用于独立预览。
- 卡片/详情显示本机上报的 `shim_version` 短码;落后于服务端 `shim.version` 时标记过期。
- 暗/亮双主题;手机窄屏(≤600px)头部分行、表格横向滚动、详情单栏。
- 不得使用浏览器本地存储;不得写死后端端口(同源相对路径)。

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
- 进入任一 skill 详情 → 趋势图铺满最近 30 个 UTC 日,used/equipped 分列展示且不相加。
- 主表默认按 30 天会话数降序,平手按累计。
- 看板页面不再渲染 skills 区块,原有卡片与轮询行为不变。
