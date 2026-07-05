# 任务：optimize-skills-overview-query

- [x] 在 `server/db.py` 为 `skill_uses` 增加 `/api/skills` 读路径组合索引，并保持幂等迁移。
- [x] 改写 `server/routes/board.py` 中 `skills_overview` 的 operator 聚合，减少 raw 行扫描，保持响应字段不变。
- [x] 扩展 SKILLS overview 测试，覆盖 operator used-only、空 operator 排除、equipped 排除、`rt/src`、`scope=new`、窗口和排序语义。
- [x] 增加合成样本性能验证脚本或测试辅助，记录 before/after 与 `EXPLAIN QUERY PLAN`。
- [x] 运行服务端编译、pytest、coverage、前端 unit/build，并在最终回复列出命令和结果。
