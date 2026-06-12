# spec delta:board(本变更新增/修改的规则)

> 合入后并入 `openspec/specs/board/spec.md`。

## 接口(新增)
- `GET /api/skills?days={7|30|90|0}` → `{ daily[], table[], funnel, catalog }`(SKILLS 总览;days 仅影响 daily,默认 30)。
- `GET /api/skill/{name}` → 单 skill 详情(指标、used/equipped 分列日级序列、runtime/operator 分布、最近记录、来源);查无此名 → 404。

## 新增规则(MUST)
- SKILLS 为第三个顶级视图(看板 / Agents / SKILLS),含总览与单 skill 详情(独立视图 + 返回)两级。
- 总览页所有聚合(daily、table)**只统计 `mode=used`**;equipped 仅在详情页展示并明确标注,
  与 used 在任何位置不得相加(沿袭既有"分条呈现"约束并收紧:总览不出现 equipped)。
- table 每行含来源字段,取值 own / meta / external / 非公司库;来源由服务端用 catalog 缓存按名字映射。
- funnel 只统计 catalog 中 `type ∈ {own, meta}` 的 skill,三层为:catalog 收录名单、
  已安装名单(出现在 ≥1 个 agent 的 profiles 安装态快照)、30 天有人使用名单(UTC 日切);
  并返回闲置名单 = 已安装 − 30 天使用。三层均返回名单而非仅数字。
- catalog 由服务端定时拉取并缓存;拉取失败时 `/api/skills` 仍须 200,funnel 携带旧缓存与过期标记;
  从未成功拉取时 funnel 为"目录不可达"态,其余字段正常。
- 柱状图按 UTC 日;前端取窗口内使用量前 8 的 skill 分色,其余合并为"其它"段;
  时间窗筛选只作用于柱状图,主表固定 7 天/30 天/累计三列,漏斗第 3 层固定 30 天。
- 新端点不进 2 秒主轮询;SKILLS 视图进入时加载、低频刷新;加载失败显示错误态。

## 修改规则
- 前端规则"Pods 看板展示 Skills 排行区"**删除**:看板不再展示 skills 区块;
  `/api/state` 的 `skills` 字段保留(协议兼容),看板前端不再消费。

## 可验证行为(新增)
- 同名 skill 同时有 used 与 equipped → `/api/skills` 的 table 与 daily 只含 used;
  `/api/skill/{name}` 两种模式并列展示且任何字段不相加。
- 造安装态:某 own skill 装于 ≥1 个 agent 且 30 天零使用 → funnel 闲置名单含之。
- catalog 拉取失败 → `/api/skills` 返回 200,funnel 带过期标记与旧名单。
- `days=7` → daily 仅含最近 7 个 UTC 日;`days` 变化不影响 table 与 funnel。
- 主表默认按 30 天会话数降序,平手按累计。
- 看板页面不再渲染 skills 区块,原有卡片与轮询行为不变。
