# 规格:board(看板与计算域)

事实来源:`server/app.py`(`/api/state`、`metrics`、`leverage`、`reuse_map`、`_snapshot`)与 `dashboard/index.html`。

## 接口
- `GET /api/state` → `{ now, sessions[], feed[], leverage, skills[], totals }`。
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

## 前端规则(MUST)
- 轮询 `/api/state`(约 2s),取不到时退回内置演示数据并显示"未连接服务端"。
- 视图:Pods 看板(按 operator 分组,人=调度员,其 agent=编队)/ Agents 列表 / 治理详情。
- Pods 看板展示 Skills 排行区;`skills` 为空时显示空态,不报错。
- 详情数据优先取 session 的服务端字段(`cf/skills/mcp/integrations/about/...`);演示映射仅用于独立预览。
- 暗/亮双主题;手机窄屏(≤600px)头部分行、表格横向滚动、详情单栏。
- 不得使用浏览器本地存储;不得写死后端端口(同源相对路径)。

## 可验证行为
- 同一 agent 跑多次/多 session → 看板仅一张卡,随最新状态刷新。
- 某 agent 3 分钟无心跳 → 卡片转 `idle`(灰)。
- 造数据:skill A 的 `used` 在 31 天前 1 个会话、5 天前 2 个会话(2 个不同 operator)使用 →
  `mode=used` 条目 `sessions_7d=2`、`sessions_30d=2`、`sessions_total=3`、`users_30d=2`。
- 同一 skill A 同时有 `used` 与 `equipped` → `skills` 出现两条同名不同 mode 条目,计数互不相加。
- 空库 → `skills: []`,看板显示空态。
