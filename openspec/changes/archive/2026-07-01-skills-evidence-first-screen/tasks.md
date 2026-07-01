# 任务：skills-evidence-first-screen

> 归档动作（移动 change / 合并 spec-delta / 回流 wireframes）不写在这里，参见 `openspec/changes/AGENTS.md`。

## 后端

- [x] 新增 `skills_evidence_payload`，复用 `_skills_window`、catalog source 映射和 used-only 口径。
- [x] 新增 `GET /api/skills/evidence` 路由，支持 `kind/w/wstart/wend/q/rt/src/skill/operator/limit/offset`。
- [x] 同步 `server/app.py` Read docstring 与 board re-export，保持路由入口和测试 monkeypatch 路径可见。
- [x] 实现 records evidence：`total/untracked/coverage/operators/avg_per_session/top3/runtime/source`。
- [x] 实现 list evidence：`idle/unused_ratio/zero_install`，返回 installed-but-unused 与 cataloged-but-not-installed 名单、installers、last_day。
- [x] 参数校验：未知 kind、非法 limit/offset 返回 400；limit 上限 500。
- [x] 保证不读取 prompt/code/output，不接触 `events.input/output`。

## 前端

- [x] 新增 `SkillsEvidencePayload` 类型与 `useSkillsEvidence` API hook。
- [x] 新增 `/skills/evidence` route 和 `SkillsEvidenceView`。
- [x] `KpiStrip` 改为「过去 W 变化」证据入口，每格带 `看证据` 并露 Top names。
- [x] `HealthBar` 改为「问题线索」，移除 `良好/偏高/需关注` 评分文案。
- [x] `GovernanceTodo` 改为「待处理线索」，未收录组前移；行内加 `看证据`、`找使用者`、`忽略`。
- [x] Evidence 页记录表支持桌面表格与手机摘要行，最近记录无下钻目标时不呈现可点态。
- [x] 证据页返回 SKILLS 时保留时间窗和筛选 query。

## 事实源

- [x] `spec-delta/board/spec.md` 覆盖新 API、首屏语义、证据页、可验证行为。
- [x] `wireframes.md` 覆盖 `/skills` 首屏和 `/skills/evidence` 桌面/移动版。
- [x] 实现完成归档时回流 `docs/wireframes/pages/skills.md`、新增 `skills-evidence.md`、更新 `flow.md`。
- [x] 同步 `docs/architecture/module-map.md` 与根 `AGENTS.md` 的 SKILLS API/路由清单。

## 验证

- [x] 后端单测：`kind=total` records 数与 `/api/skills` current_sessions 一致。
- [x] 后端单测：`kind=untracked` 不含 `external` 和 `equipped`。
- [x] 后端单测：`kind=untracked&src=own` 忽略冲突 source，返回 non_catalog records，并填充 `ignored_filters`。
- [x] 后端单测：`kind=idle` 使用 installed - window used company names，返回 installers/last_day。
- [x] 后端单测：`q/rt/src/skill/operator` 筛选影响 records 与 Top 分组。
- [x] 后端单测：invalid kind / invalid limit 返回 400。
- [x] 前端单测：证据链接保留窗口和筛选 query。
- [x] 前端单测：source 语义明确的证据入口不会把冲突 `src` 带成空证据页。
- [x] 前端单测：首屏不再出现 `KPI 环带`、`治理健康`、`良好/偏高/需关注`。
- [x] 前端单测：忽略待办不写 localStorage。
- [x] `python -m py_compile server/*.py server/routes/*.py`
- [x] `python -m pytest tests/test_skills_stats_page.py`
- [x] `npm --prefix frontend run test:unit`
- [x] `npm --prefix frontend run build`
- [x] Browser/Playwright 1440x900 验证 `/skills` 首屏和 `/skills/evidence?kind=total&w=7d`。
- [x] Browser/Playwright 375x812 验证 `/skills` 与 `/skills/evidence` 页面根无横向滚动。

## 反思代码符合度（步骤 6）

- [x] 对照 proposal/design 核每个首屏聚合数是否有证据入口。
- [x] 对照 spec-delta 核 `used`/`equipped` 隔离和 source 口径。
- [x] 对照 wireframes 核 14 寸首屏未收录线索是否前移。
- [x] 对照测试结果核所有新增 API kind 与前端入口均被覆盖。
