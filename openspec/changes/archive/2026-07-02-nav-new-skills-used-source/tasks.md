# 任务:nav-new-skills-used-source

- [x] 1. 服务端:提取 used-only distinct/new skill helper,让 `/api/state.leverage.assets` 与 `skills_week` 不再读取 `skills_seen`。
- [x] 2. 服务端:`/api/skills` 支持 `scope=new`,返回当前窗口内历史首次 used 的 skill 名单,并继承窗口、runtime/source、operator 证据口径。
- [x] 3. 前端:顶部 `+N 新增 Skill` 改为跳 `/skills?w=7d&scope=new`;copy 明确 `7天新发现` 与 `Skill 资产`。
- [x] 4. 前端:`/skills` 支持 `scope` query、清除 chip、手机首屏新增名单入口;入口可点击且可键盘聚焦。
- [x] 5. 测试:补 used-only、重复 session 去重、installed-only/profile-only/equipped-only 不计入 nav;补 `scope=new` 名单态、非法 scope 和前端 query/mobile summary 测试。
- [x] 6. 验证:`python -m py_compile server/*.py server/routes/*.py`;`pytest tests/test_skill_usage.py tests/test_skills_stats_page.py -q`;`npm --prefix frontend run test:unit`;`python -m coverage run -m pytest && python -m coverage report --include='server/**/*.py'`;`npm --prefix frontend run build`。
- [x] 7. 归档:spec delta 合入 `openspec/specs/board/spec.md`,wireframes 回流 `docs/wireframes/pages/skills.md`,AGENTS 同步 nav used-only 口径。
