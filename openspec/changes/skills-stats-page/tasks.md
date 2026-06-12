# tasks:skills-stats-page

- [x] 0. 前置验证:抽样比对 profiles 表 skills 字段与 catalog `name` 的写法一致性;
      确认 index.json 可达、字段(`name`/`type`)符合预期。不一致 → 先回 design 定归一化规则。
      备注:当前默认 `tf.db` 无 profile skill 样本;已确认 catalog 可达且造数/测试按 catalog `name` 精确匹配。
- [x] 1. `server/app.py`:catalog 定时同步 + 缓存降级。
      测试:拉取成功更新缓存;失败沿用旧缓存并带过期标记;从未成功 → 漏斗数据为"不可达"态。
- [x] 2. `server/app.py`:`GET /api/skills` 总览聚合(daily / table / funnel)。
      TestClient 造数测试:7/30 天 UTC 窗口切分、用户数去重、来源映射(own/meta/external/非公司库)、
      漏斗三层与闲置差集、equipped 不出现在 table 与 daily、days 参数只影响 daily、空库各块空态。
- [x] 3. `server/app.py`:`GET /api/skill/{name}` 详情。
      测试:同名 used+equipped 并列且任何字段不相加;runtime/operator 分布;最近记录截断;查无此名 404。
- [x] 4. `frontend/`:顶部导航 + skills 总览视图
      (筛选条 / SVG 堆叠柱状图 Top8+其它 / 可排序主表 / 漏斗展开名单 / 空态与错误态)。
      `npm --prefix frontend run build`;暗/亮主题与 ≤600px 窄屏各走查一遍。
- [x] 5. `frontend/`:skill-detail 视图 + 行点击进入/返回导航。
- [x] 6. `frontend/`:移除看板侧栏 skills 区块(`/api/state.skills` 字段保留);
      看板回归走查:布局不破、原有 2 秒轮询不受影响。
- [x] 7. 端到端手验:本地起服务,造四 runtime 数据(含 OpenClaw equipped),浏览器走查:
      三视图切换、搜索/runtime/来源筛选、时间窗只动柱状图、列头排序、下钻与返回、
      图例悬浮高亮、catalog 断网降级显示。
- [ ] 8. 文档:PROTOCOL.md(如记录读侧接口)补两个新端点;
      PROTOCOL/README/QUICKSTART/USAGE/DEPLOY/UPDATE/SKILL/AGENTS/.env.example/module-map/llms 已同步;
      spec delta 已合入 `openspec/specs/board/spec.md`;归档本 change 留待上线后执行。
