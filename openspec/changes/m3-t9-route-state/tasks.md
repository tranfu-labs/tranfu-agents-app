# 任务：m3-t9-route-state

- [x] 在 `frontend/src/App.tsx` 增加 Not Found 视图，并把 wildcard route 与非法 `/skills/clues/:clueKind` 从 Board/redirect fallback 改为 404/Not Found。
- [x] 调整 `/skills` 抽屉状态读取，使合法 `sel` 刷新后恢复抽屉，非法或不可见 `sel` 不打开抽屉。
- [x] 在 SKILLS query/link helper 中 canonical 化窗口参数：输入兼容 `win`，输出只保留 `w`。
- [x] 审核并修正 `/skills` 顶部 KPI 与问题线索链接：`总触发次数` 到 `kind=total`，`新增发布 Skill` 到 `/skills/new`，显式记录入口保持 `a[href]` / Router `Link`。
- [x] 更新前端单元测试，覆盖 `w/win` 去冗余与 KPI 路径语义。
- [x] 运行 `npm --prefix frontend run test:unit` 与 `npm --prefix frontend run build`。
- [x] 验证三条已确认验收语句，并将证据放入 `artifacts/acceptance/`；本轮内置浏览器无可用实例，未生成截图。
