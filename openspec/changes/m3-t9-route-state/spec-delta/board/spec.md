# spec-delta：board（m3-t9-route-state）

> 合入后并入 `openspec/specs/board/spec.md`。本 delta 只修改前端路由与 SKILLS URL 状态规则，不改接口契约、统计口径或后端聚合。

## 前端规则（MODIFIED）

- React SPA 的 wildcard route 必须渲染明确的 404 / Not Found 状态，不得把未知客户端路径渲染为 Pods 看板首页。已匹配但非法的 SKILLS 子路由参数（例如非法 `/skills/clues/:kind`）也必须进入 Not Found，不得静默重定向到 `/skills`。FastAPI 仍可对非 API 深链返回 SPA HTML，最终未知路由由 React 路由层显示 Not Found。
- `/skills` 的 Skill 选中态继续绑定 URL search param `sel`。当 `sel` 对应当前 SKILLS table 中存在的 skill 时，刷新、前进后退或复制链接进入页面必须恢复右侧 Skill 抽屉并选中同一个 skill；当 `sel` 为空、非法或当前 table 不包含该 skill 时，抽屉关闭。
- SKILLS 新生成的出站链接必须使用 canonical 时间窗参数 `w`，不得同时输出 `w` 与旧参数 `win`。旧链接输入兼容规则保留：如果 URL 只有合法 `win` 而没有 `w`，前端可把它映射成等价 `w`；如果两者同时存在，以 `w` 为准。
- `/skills` 顶部 KPI 与问题线索的显式记录入口必须是可键盘聚焦的 `a[href]` 或 React Router `Link`，不得只用行点击、button 或 JS navigate 代替。
- `/skills` Skill 视角的顶部 KPI 语义必须区分：
  - `总触发次数` 跳 `/skills/evidence?kind=total...`。
  - `新增发布 Skill` 跳 `/skills/new...`。
  问题线索中的 `新增发布 Skill` 入口也必须跳 `/skills/new...`。

## 可验证行为（新增/修改）

- 打开 `/skills/bogus-route-test` → 页面显示明确 404 或 Not Found 状态，且不渲染 Pods 看板首页主体。
- 打开 `/skills/clues/not-a-kind` → 页面显示明确 404 或 Not Found 状态，且不重定向到 `/skills`。
- 在 `/skills` 点击 Skill 明细行产生 `?sel=<skill>` 后刷新 → 右侧 Skill 抽屉仍打开，并显示同一个 skill；把 `sel` 改成不存在的值后刷新 → 抽屉关闭。
- 在 `/skills?win=30` 进入页面后点击任意 SKILLS 记录/KPI/新增发布链接 → 新 href 使用 `w=30d`，且不再包含 `win=30`。
- 在 `/skills?w=14d&win=30` 进入页面后点击任意 SKILLS 记录/KPI/新增发布链接 → 新 href 保留 `w=14d`，且删除 `win`。
- 使用键盘 Tab 检查 `/skills` 的 `查看记录` 图标 → 焦点落在带 `href` 的链接元素上。
- `/skills` Skill 视角顶部 `总触发次数` 的 href pathname 为 `/skills/evidence` 且 query 含 `kind=total`；顶部 `新增发布 Skill` 的 href pathname 为 `/skills/new`。
