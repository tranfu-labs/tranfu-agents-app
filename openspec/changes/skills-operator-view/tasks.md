# tasks:skills-operator-view

- [x] 1. `server/app.py`:`GET /api/skills` 增 `operator_table` / `operator_daily`(只 used、排除空 operator)。
      TestClient 造数测试:会话×skill 去重计数、equipped 不计入、空 operator 排除、
      7/30/累计三列与各 runtime 计数、`days` 只影响 operator_daily 不影响 operator_table、
      默认按 30 天降序平手按累计、空库空态。
- [x] 2. `server/app.py`:`GET /api/operator/{name}` 单人详情。
      测试:指标(7/30/累计/用过 skill/会话/首见/最近)、按 skill 分段日序列、skill 排行(含来源映射)、
      runtime 分布、最近记录截断、equipped 任何字段不计入、查无此人 404。
- [x] 3. `frontend/`:总览页"视角切换"(按 skill / 按人)。
      柱状图分段维度参数化(skill ↔ operator)、人排行主表、漏斗常驻、搜索框提示语随视角变、
      时间窗统一默认 30 天且切视角不重置。`npm --prefix frontend run build`;暗/亮主题 + ≤600px 走查。
- [x] 4. `frontend/`:operator-detail 视图 + 路由 `/operator/:name`。
      页头两行;日趋势按 skill 分段;⑨ 左右两栏(skill 排行 + runtime 分布);
      skill 排行行点击跳 `/skill/:name`(双向下钻);返回回按人总览。
- [x] 5. 端到端手验:本地起服务,造多 operator + 跨 runtime 数据(含 OpenClaw equipped):
      视角切换整页换主语、按人柱状图分段与悬浮高亮、人榜排序、单人下钻与返回、
      skill↔人 双向下钻、空 operator 不出现、equipped 不进人视角任何位置、漏斗两视角都在。
- [x] 6. 文档:PROTOCOL/README/USAGE 等如记录读侧接口则补新端点与新增字段;
      spec delta 合入 `openspec/specs/board/spec.md`;归档本 change 留待上线后执行。
