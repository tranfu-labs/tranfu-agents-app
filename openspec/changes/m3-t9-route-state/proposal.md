# 提案：m3-t9-route-state

## 背景
本变更覆盖 issue T9 的路由与 SKILLS 状态缺陷：

- React wildcard route 目前把未知路径落到 Pods 看板，导致 `/skills/bogus-route-test` 看起来像首页而不是错误状态。
- `/skills` 明细行点击会写入 `?sel=` 并打开抽屉，但刷新后本地抽屉状态丢失，URL 不能恢复同一个 skill。
- SKILLS 的记录入口与 KPI 下钻依赖 helper 生成链接，需要保证显式操作是可聚焦 anchor，且不同业务语义不能混到同一个 URL。
- `win` 是旧链接输入兼容参数；新生成 URL 不应再同时暴露 `w` 与 `win`，避免窗口语义冲突。

最新需求消歧以 product-manager 的后续说明为准：顶部 KPI 主验收对象是 `/skills` Skill 视角的 `总触发次数` 与 `新增发布 Skill`。前者跳记录证据页 `kind=total`，后者跳 `/skills/new`；问题线索里的 `新增发布 Skill` 也保持同一语义。`win` 只做旧输入兼容，若 `w` 和 `win` 同时存在，以 `w` 为准并在新生成 URL 中去掉 `win`。

## 提案
1. 为 React SPA 添加明确 Not Found 视图，用 wildcard route 渲染 404/Not Found 状态，并让已匹配但非法的 SKILLS 子路由（如非法 clue kind）也进入 Not Found，不再 fallback 到 Board 或静默跳回 `/skills`。
2. 让 `/skills` 的抽屉选中态以 URL `sel` 为事实源：刷新或复制链接后，如果 `sel` 对应当前 table 中的 skill，自动打开抽屉；非法或不可见 skill 降级为关闭。
3. 收敛 SKILLS 出站链接生成：记录入口继续使用 React Router `Link` / `a[href]`；总触发次数进入 `/skills/evidence?kind=total...`，新增发布 Skill 进入 `/skills/new...`；所有生成链接只输出 canonical `w`。
4. 补充前端单元测试覆盖 URL canonical 化与 KPI 路径语义，并通过构建和浏览器验收验证 404、`sel` 恢复和键盘可达链接。

## 影响
- 受影响模块：M2 前端 `frontend/`，主要是 `App.tsx`、`Skills.tsx`、`skillsEvidence.ts` 及相关组件/测试。
- 事实源影响：`openspec/specs/board/spec.md` 的前端路由、SKILLS query 与下钻规则需要在归档时合并本变更 delta；`docs/wireframes/` 需要在归档时新增 Not Found 页面并更新 flow 中 wildcard 行为。
- 不影响模块：不新增或修改后端 API，不改变 SKILLS 统计口径，不改 SQLite schema，不改 shim。
