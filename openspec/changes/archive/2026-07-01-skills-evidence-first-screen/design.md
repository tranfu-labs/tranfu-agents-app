# 设计：skills-evidence-first-screen

## 1. 现状约束

已读边界：

- `docs/architecture/module-map.md`：前端只能走同源相对 API，不能新增运行期前端服务；服务端仍是 FastAPI + SQLite。
- `openspec/specs/board/spec.md`：`/api/skills` 只统计 `mode=used`，`equipped` 只在 skill 详情里分列；SKILLS URL 参数已有 `w/wstart/wend/rt/src/q/topn/view/sel`。
- ADR-0015 / ADR-0018：Skill 使用口径是会话 x skill x mode；`used` 与 `equipped` 不得相加。
- ADR-0019 / ADR-0023：React SPA 深链可扩展；除主题外不写 localStorage。

现有实现锚点：

- 后端：`server/routes/board.py` 的 `_skills_window`、`skills_overview`、`_skills_governance_untracked`、`_governance_buckets`。
- 前端：`frontend/src/views/Skills.tsx`、`components/skills/KpiStrip.tsx`、`HealthBar.tsx`、`GovernanceTodo.tsx`、`RankBars.tsx`、`SkillsDetailTable.tsx`。

## 2. 后端证据 API

新增：

```text
GET /api/skills/evidence
  ?kind=total
  &w=7d|14d|30d|90d|today|this_week|last_week|custom
  &wstart=<unix>&wend=<unix>
  &q=<skill-or-operator-substring>
  &rt=<runtime>
  &src=own|meta|external|non_catalog
  &skill=<skill-name>
  &operator=<operator-name>
  &limit=100&offset=0
```

返回形状：

```json
{
  "kind": "total",
  "today": "2026-07-01",
  "window": {"key": "7d", "start": "...", "end": "..."},
  "summary": {
    "records": 337,
    "skills": 42,
    "operators": 12,
    "sessions": 280,
    "untracked_records": 113,
    "company_records": 180
  },
  "actions": [
    {"id": "inspect-records", "label": "看原始记录"},
    {"id": "group-by-operator", "label": "找使用者"}
  ],
  "applied_filters": {"w": "7d", "rt": "", "src": "", "q": ""},
  "ignored_filters": [],
  "top_skills": [{"name": "figma", "source": "non_catalog", "records": 42, "operators": 5}],
  "top_operators": [{"operator": "alice", "records": 30, "skills": 6}],
  "daily": [{"day": "2026-07-01", "records": 50}],
  "records": [
    {
      "day": "2026-07-01",
      "first_seen": "2026-07-01T02:00:00+00:00",
      "skill": "figma",
      "operator": "alice",
      "runtime": "codex",
      "source": "non_catalog",
      "session_id": "..."
    }
  ],
  "items": []
}
```

`records` 只来自 `skill_uses WHERE mode='used'`。`items` 用于没有窗口内触发记录的 evidence kind，例如 `idle` / `unused_ratio` / `zero_install`：

```json
{
  "kind": "idle",
  "summary": {"items": 16, "installed": 34, "records": 0},
  "items": [
    {"name": "idle-own", "source": "own", "installers": 3, "last_day": "2026-06-01"}
  ],
  "records": []
}
```

### kind 规则

| kind | 证据口径 | 主要用途 |
|---|---|---|
| `total` | 当前窗口全部 `mode=used` records | 总触发次数 |
| `untracked` | `source == non_catalog` 的 used records；`external` 不算 | 未收录占比 / 有使用但未收录 |
| `coverage` | `source in own/meta` 的 used records + catalog/company 名单摘要 | 公司库覆盖 |
| `operators` | 非空 operator 的 used records，按 operator 分组 | 活跃操作员数 |
| `avg_per_session` | used records 按 session 分组，显示每会话 skill 数分布 | 平均 skill/会 |
| `idle` | company installed names - current window used company names | 闲置 Skill 数 |
| `unused_ratio` | 与 `idle` 同名单，summary 增加 installed/idle ratio | 装了没用比例 |
| `zero_install` | company catalog own/meta names - installed names | 收录但零装机名单 |
| `top3` | 当前窗口 used Top3 skill records + share | Top3 集中度 |
| `runtime` | 当前窗口 used records，按 runtime 分组 | runtime 分布证据 |
| `source` | 当前窗口 used records，按 source 分组 | 来源分布证据 |

### 查询实现

- 复用 `_skills_window`，保持 `Asia/Shanghai` 日期口径。
- 复用 `_catalog_context` 和 `_skill_source_key`，让 source 命名与前端筛选一致。
- 可测逻辑拆成 `skills_evidence_payload(conn, days, w, wstart, wend, kind, filters)`，并通过 `server.app` re-export 保持测试入口可见。
- 路由函数放在 `server/routes/board.py`；实现完成时同步 `server/app.py` 顶部 Read docstring 与 board re-export，
  保持测试和既有 monkeypatch 入口的一致性。
- `kind` 是强制证据口径，用户筛选是附加约束。`q/rt/skill/operator` 总是与 `kind` 取交集；`src` 只有在不与 `kind`
  的强制 source 口径冲突时才生效。
- Source 冲突处理必须可见：后端返回 `applied_filters` 与 `ignored_filters`。例如从
  `/skills?src=own` 点击 `有使用但未收录` 时，前端进入 `kind=untracked`，后端忽略冲突的 `src=own`，
  `applied_filters.src` 为 `non_catalog`，`ignored_filters` 含 `{name:"src", value:"own", reason:"kind_untracked_forces_non_catalog"}`。
- `limit` 默认 100，上限 500；`offset` 默认 0。
- `q` 只匹配 skill/operator 的小写 substring，不匹配 session 内容。
- 不读取 `events.input/output` 或任何 prompt/code/output 字段。

## 3. 前端路由与 API

新增：

- `frontend/src/views/SkillsEvidence.tsx`
- `useSkillsEvidence(enabled, query)` hook
- `SkillsEvidencePayload` / `SkillsEvidenceRecord` / `SkillsEvidenceItem` 类型
- `Route path="/skills/evidence"`，由 `SkillsEvidenceRoute` 读取当前 search params。
- 服务端现有 SPA fallback 已允许 `/skills/evidence` 这类无扩展名深链；实现时只需加 React route，不需要改
  `server/routes/onboarding.py` 的 blocked prefixes。

Evidence 页布局：

1. 顶部 `← SKILLS`，返回时保留除 `kind` 外的原 query。
2. 标题区显示 evidence kind 名称、窗口范围、筛选 chips。
3. 摘要条：records / skills / operators / sessions 等，不用 KPI 词。
4. 下一步动作区：非破坏 action chips，只做导航、筛选或复制名单；不写持久状态。
5. 分组区：Top skills、Top operators、daily。
6. 证据表：时间、skill、operator、runtime、source、session_id。最近记录时间复用已有本地时区格式化规则。

## 4. `/skills` 首屏改造

### `KpiStrip` -> 证据入口

保留组件文件名以降低 diff，但 UI 文案改：

- 标题：`过去 W 变化`
- 每格增加 `看证据` 链接，目标为 `/skills/evidence?kind=<kind>&...currentSearch`。链接构造必须保留时间窗和
  `q/rt/view/topn`；对于 `untracked/coverage/idle/unused_ratio/zero_install` 这类 source 语义明确的入口，若当前 `src` 冲突，
  链接可直接改写或删除 `src`，避免用户点进空证据页。
- 格内露 Top names：
  - 总触发次数：Top 2 skill names
  - 未收录占比：Top 2 untracked names
  - 闲置 / 装未用：Top 2 idle names
  - Top3 集中度：Top3 skill names
- Delta 仍可显示，但不使用红绿考核语义；只作为变化辅助。

### `HealthBar` -> 问题线索

- 标题改为 `问题线索`
- 不再显示 `良好/偏高/需关注`
- 每项展示当前值 + 证据链接 + 一句可行动提示，例如：
  - `未收录 33.5% · figma / coolify-deploy · 看证据`
  - `装了没用 47% · 16 个 · 看名单`

### `GovernanceTodo` -> 待处理线索

- 标题改为 `待处理线索`
- Skill 视角顺序固定：
  1. 有使用但未收录
  2. 装了 W 内没用
  3. 收录但零装机
- 行动作：
  - `看证据`：进入 evidence 页，保留窗口和筛选。
  - `找使用者`：进入 evidence 页并聚焦 operator/top operator 分组。
  - `忽略`：只在当前 React state 中隐藏，已有实现保留。
- Operator 视角保留人维度待办，但同样增加证据链接。

## 5. 线框

字符图单独落 `wireframes.md`，基线引用 `docs/wireframes/pages/skills.md`。归档时回流：

- `docs/wireframes/pages/skills.md`
- 新增 `docs/wireframes/pages/skills-evidence.md`
- 更新 `docs/wireframes/flow.md` 的 SKILLS 下钻。

## 6. 测试策略

### 后端单测

新增或扩展 `tests/test_skills_stats_page.py`：

- `kind=total` 返回窗口内全部 used records，summary.records 等于同一窗口 `/api/skills` 的
  `period_comparison.current_sessions`。
- `kind=untracked` 不含 catalog external，也不含 equipped。
- 从 `src=own` 页面点击 `kind=untracked` 时，source 冲突被忽略或改写，证据页仍展示 non_catalog records，并在
  `ignored_filters` 中说明。
- `kind=idle` 返回 installed - window used company names，并带 installers/last_day。
- `q/rt/src/skill/operator` 筛选影响 records 和分组。
- invalid `kind`、invalid `limit` 返回 400。

### 前端单元测试

若现有 Vitest 结构可直接复用：

- evidence link builder 保留 `w/wstart/wend/rt/src/q/view/topn`。
- 首屏不再出现 `KPI 环带`、`治理健康`、`良好/偏高/需关注` 文案。
- 待处理线索的 `忽略` 只影响当前组件 state，不触发 localStorage。

### AI 验证

- `npm --prefix frontend run build`
- `npm --prefix frontend run test:unit`
- `python -m py_compile server/*.py server/routes/*.py`
- `python -m pytest tests/test_skills_stats_page.py`
- 启动本地服务后用 Browser/Playwright：
  - 1440x900 打开 `/skills`，核首屏文案与未收录线索前移。
  - 点 `总触发次数 -> 看证据`，核 URL 和证据表。
  - 点 `有使用但未收录 -> 看证据`，核 `kind=untracked` 和记录 source。
  - 375x812 打开 `/skills` 与 `/skills/evidence`，核页面根无横向滚动。

## 7. 风险与取舍

- 新 evidence kind 较多，但都基于同一 used records 查询；idle/unused 是唯一 list evidence 分支。
- 不做公司库写入会让 `收录` 不能一键完成；本轮先提供证据和名单，避免伪造不可用动作。
- 保留 `KpiStrip` 文件名会让代码名与产品语义不完全一致；若后续 diff 可控，再单独重命名为 `EvidenceStrip`。
