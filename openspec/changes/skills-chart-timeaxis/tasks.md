# tasks:skills-chart-timeaxis

- [x] 0. 前置验证:抽样确认 `skill_uses.day` 为 UTC 日且与服务端 `today`
      (`datetime.now(timezone.utc).date()`)同一套写法;确认 `chart-box` 在 90 天柱宽下横滚可用、
      不破 ≤600px 窄屏。不一致 → 先定归一化规则再继续。

- [x] 1. `server/app.py`:`skills_overview()` 与 `skill_detail_payload()` 响应各加 `today`(UTC ISO 日);
      `/api/skills` 的 `days` 校验集合改为 `{7,30,90}`。
      测试(TestClient):两接口响应含 `today` = UTC 当日;`daily`/`table`/`funnel` 数值与改动前一致(回归);
      `days=0` 不再是合法入参(按现有 400 口径或前端不再传——以 spec 为准)。

- [x] 2. `dashboard/index.html`:窗口选择器去掉「全部」(options `[7,30,90]`,默认 30)。

- [x] 3. `dashboard/index.html`:`stackedChart()` 横轴按 `[today-(N-1) .. today]` 逐日铺满,
      空天留白;今日柱"进行中"样式。
      自测:只有今天有量时,7d 出 7 槽、今天 1 柱(进行中)、其余 6 空;切 30d 出 30 槽。

- [x] 4. `dashboard/index.html`:明细浮窗组件(日期 / 当天各 skill 降序 / 合计 / 今日标注),
      整列悬停高亮并与图例 hover 解耦,替换原生 `<title>`;移动端点击触发;边界翻转。

- [x] 5. `dashboard/index.html`:`detailTrend()` 固定最近 30 天逐日铺满 + 同款浮窗(used/equipped)+
      今日进行中。

- [x] 6. 抽出 `<script>` 跑 `node --check`;暗 / 亮主题与 ≤600px 窄屏各走查一遍。

- [x] 7. 端到端手验(本地起服务 `TF_KEY=devkey python -m uvicorn server.app:app --port 8788`,
      浏览器开 127.0.0.1:8788 → SKILLS):
      A. 造数仅今天 1 个 used → 7d/30d 档分别铺 7/30 槽,仅今天 1 柱且进行中样式,其余留白。
      B. 造数今天 / 前 2 天 / 前 5 天各有量、中间留空 → 柱落在对应槽,空档如实留白(不前移、不压缩)。
      C. 造数 >8 个 skill 当天都有量 → 堆叠与浮窗均把 Top8 外并入"其它";浮窗合计 = 当天全部 sessions 之和。
      D. 悬停某柱 → 浮窗逐项数值 = 主表 / SQL `COUNT`;移出消失;切 7/30/90 即时重铺。
      E. 进某 skill 详情 → 趋势图铺满最近 30 天,首见日之前留白;今日柱进行中;悬停浮窗给 used/equipped。
      F. 跨 UTC 午夜(系统/容器时间拨到 UTC 次日凌晨,或 mock `today`)→ 今日柱落在最后一格,不错位。
      G. 看板与 Agents 视图回归:不受影响。
      H. 整窗全空(或筛选后无数据)→ 显示空态文案,而非一排空槽。
      I. 加 runtime / 来源 / 搜索筛选 → 图与主表同步,某天归零变空槽、其余照常。

- [x] 8. 文档:spec delta 合入 `openspec/specs/board/spec.md`;PROTOCOL.md 若记录读侧响应字段则补 `today`;
      归档本 change 留待上线后执行。
