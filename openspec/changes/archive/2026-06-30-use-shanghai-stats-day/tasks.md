# 任务：use-shanghai-stats-day

- [x] 1. `server/db.py`:新增统一统计时区 helper,保持 `now_iso()` UTC 不变。
- [x] 2. `server/routes/ingest.py`:写入 `events.day`、`skill_uses.day`、`skills_seen.first_day` 时使用上海统计日。
- [x] 3. `server/routes/board.py`:把日级窗口、`today`、活跃时长日边界、SKILLS 聚合窗口切到上海统计日。
- [x] 4. 测试:补充 ingest 上海日写入、SKILLS `today`、活跃时长跨上海午夜分桶用例。
- [x] 5. 文档/spec:更新 board / ingest / admin specs、AGENTS.md、docs/architecture/module-map.md 中的 UTC 日口径描述。
- [x] 6. 验证:运行 `python -m py_compile server/*.py server/routes/*.py`、相关 pytest,必要时运行全量测试/覆盖率。
