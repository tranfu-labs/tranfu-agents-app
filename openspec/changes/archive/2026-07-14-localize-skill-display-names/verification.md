# 验证：localize-skill-display-names

- 后端：`349 passed`；coverage `96%`，满足项目整体 `>=95%` 门槛。
- 前端：`65 passed`；TypeScript + Vite 生产构建通过。
- 静态检查：Python compile、shim profile JSON、shell syntax、`git diff --check` 通过。
- API：state、overview、evidence、Skill 详情、operator 详情、Admin inventory 均返回双语 `skill_names`，含 Skill 的对象直接返回双语字段。
- 浏览器：中文/英文总览、显示名搜索、Skill 详情、evidence 筛选摘要、operator 详情、Agent profile、Admin Skills 清单均通过；已有显示名时可见 slug 为 0。
- 响应式：375x812 下显示中文名称且页面根无横向滚动。
