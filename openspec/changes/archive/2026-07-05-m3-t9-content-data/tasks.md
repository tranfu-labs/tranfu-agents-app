# 任务：m3-t9-content-data

- [x] 将 `/api/skills` overview 聚合统一过滤占位/测试 skill 名。
- [x] 从 zero-install 与当前窗口新增发布计数中排除当前窗口 used 且 installers=0 的公司库 skill。
- [x] 将 `/skills?w=7d` 未收录 KPI/线索展示统一为 `used_sessions` / `skill_count` 派生。
- [x] 清理 demo fallback 并让 fallback 继承当前请求窗口。
- [x] 统一「近 7 天」/ `Last 7 days` / `Top3` 文案。
- [x] 补后端固定造数测试覆盖 used-but-uninstalled company skill 与占位名 overview 过滤。
- [x] 补前端单测覆盖聚合字段、fallback 和窗口/Top3 文案。
- [x] 合并 `spec-delta` 到 `openspec/specs/board/spec.md` 并归档本 change。
- [x] 运行 Python 编译、后端 pytest、前端 unit/build、coverage 与 `git diff --check`。
