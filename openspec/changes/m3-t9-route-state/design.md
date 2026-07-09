# 设计：m3-t9-route-state

## 方案

### 1. 未知路由显示 Not Found
- 在 `frontend/src/App.tsx` 增加轻量 `NotFoundRoute`，展示明确 `404 / Not Found`、当前路径和返回入口。
- 将 `<Route path="*">` 从 `StateRoute -> Board` 改为 `NotFoundRoute`。
- 将 `/skills/clues/:clueKind` 中不属于 `untracked | idle | zero-install` 的已匹配非法参数改为 `NotFoundRoute`，避免它绕过 wildcard 后又重定向回 `/skills`。
- 保留 FastAPI 对 SPA 深链的服务方式：服务端仍返回 SPA HTML，未知客户端路由由 React 负责显示 404 状态。
- Not Found 不依赖 `/api/state` 首包，避免错误页被 state loading gate 阻塞。

### 2. `/skills?sel=` 恢复抽屉
- 将 `/skills` Skill 抽屉的打开状态从纯本地 `drawerSkill` 收敛到 URL `sel`：
  - `selected = selectedSkillOf(params)` 继续作为选中态事实源。
  - `drawerSkill` 由 `selected` 与当前 `data.table` 匹配得到，匹配到才渲染 `SkillDrawer`。
  - 明细表行点击继续调用 `setParams({ sel: name })`，刷新后同一个 `sel` 仍能恢复。
  - 关闭抽屉时清空 `sel`，非法值或当前筛选下不可见值不打开抽屉。
- 排行 Bar 仍可设置 `sel` 做图表联动；如果其目标在 table 中，也会保持一致地打开抽屉。若实现时发现这会改变现有排行只选中不抽屉的体验，则保留本地 `drawerOpen` 标记并只在初次 mount / URL 变更时恢复 table 命中的 `sel`，但验收必须保证明细行刷新恢复。

### 3. 出站链接语义与 canonical query
- 在 `frontend/src/lib/skillsEvidence.ts` 内集中处理 query canonical 化：
  - 读入时 `normalizeWindow()` 仍按 `w` 优先、无 `w` 才从合法旧 `win` 映射到 `w`，否则默认 `7d`。
  - 新生成的 evidence / clue / published / back search 均设置 canonical `w`，并删除 `win`。
  - `PRESERVE`、`CLUE_PRESERVE`、`PUBLISHED_PRESERVE` 不再把 `win` 透传到输出。
- 补齐直接手写 URL 的组件：
  - `/skills` mobile 新发现入口和抽屉详情入口使用 canonical search。
  - TopBar 已固定 `/skills?w=7d&scope=new`，保持不变。
- 保持 KPI 语义：
  - 顶部 KPI `总触发次数`：`/skills/evidence?kind=total...`
  - 顶部 KPI `新增发布 Skill`：`/skills/new...`
  - 问题线索 `新增发布 Skill`：`/skills/new...`
  - 记录入口使用 `Link` 或 `<a href>`，不以 `button + navigate()` 代替显式操作链接。

### 4. 测试与验证
- 单元测试：
  - `skillsEvidence.test.ts` 增加 `?w=14d&win=30` 只输出 `w=14d` 的断言。
  - `publishedSkillsSearch('?win=30&src=external')` 期望从旧输入生成 `?w=30d`，不再保留 `win=30`。
  - `evidencePath` 分别断言 `kind=total` 与 published path 是不同 pathname。
- AI / 浏览器验证：
  - 构建后打开 `/skills/bogus-route-test`，应看到 404/Not Found 文案，不出现 Pods 看板首页主体。
  - 打开 `/skills/clues/not-a-kind`，应看到 404/Not Found 文案，不跳回 `/skills`。
  - 打开 `/skills`，点明细行产生 `?sel=` 后刷新，抽屉仍打开并显示同一 skill。
  - 通过 Tab 聚焦 KPI/问题线索的 `查看记录` 图标，检查 DOM 为 `a[href]`；总触发次数与新增发布 Skill 的 href pathname 不同，且 href query 不同时包含 `w` 与 `win`。

## 权衡
- 不新增服务端 404，因为当前部署依赖 SPA fallback 支持深链；服务端仍交给前端路由判定客户端未知路径。
- 不把 `sel` 存入 localStorage/sessionStorage，遵守前端状态不得持久化的既有约束；URL 是唯一恢复来源。
- 不改变后端 `days/w/win` 兼容逻辑，本变更只收敛前端生成的新 URL。
- 不重排 `/skills` 首屏，不改统计口径，不新增 API。

## 风险
- 如果当前筛选导致 `sel` 对应 skill 不在 `data.table` 中，抽屉会关闭。这符合“非法值降级关闭”，但实现时需避免在后台刷新短暂空数据时误清 URL。
- `win` 去冗余可能影响复制旧链接后的显示。方案保留旧输入兼容：进入页面时仍能从 `win` 映射出 `w`，只是之后生成的新链接只携带 `w`。
- Not Found 改动会改变所有未知客户端路径的表现。回滚方式是恢复 wildcard route 到原实现，但不建议回滚该行为。
