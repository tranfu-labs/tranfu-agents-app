# tasks:show-skill-usage

- [x] 1. `server/app.py`:`_snapshot()` 聚合 `skills` 块 + `skill_uses(skill)` 索引。
      TestClient 测试:造跨 7/30 天边界的数据,校验窗口切分(UTC 日)、去重人数、排序、字段齐全;
      空库 → `skills: []`。
- [x] 2. `dashboard/index.html`:SKILLS 排行区块渲染 + 空态。
      抽出 `<script>` 跑 `node --check`;暗/亮主题与 ≤600px 窄屏各看一眼。
- [x] 3. 端到端手验:本地起服务,向 `/v1/events` 投递带 `skill` 字段的事件造数,
      打开看板确认排行顺序与数字;清库后确认空态。
- [ ] 4. 上线后:spec delta 合入 `openspec/specs/board/spec.md`,归档本 change。
      spec delta 已合入;归档留到上线后执行。
