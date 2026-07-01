# specs/board delta：skills-evidence-first-screen

## MODIFIED

### 接口

`GET /api/skills` 的现有字段保持兼容。SKILLS 总览首屏使用这些字段时，不再把 8 格摘要命名为 KPI，也不再用综合健康评分语义解释问题。

`GET /`、`/agents`、`/agent/{key}`、`/skills`、`/skill/{name}`、`/operator/{name}` 的 SPA 深链列表新增：

- `GET /skills/evidence` → SKILLS 证据页。

## ADDED

### `/api/skills/evidence`

- `GET /api/skills/evidence?kind={total|untracked|coverage|operators|avg_per_session|idle|unused_ratio|zero_install|top3|runtime|source}[&days=7|30|90][&w=today|this_week|last_week|7d|14d|30d|90d|custom][&wstart=&wend=&q=&rt=&src=&skill=&operator=&limit=&offset=]`
  返回当前时间窗下的 SKILLS 证据 payload：
  - `today`：服务端统计时区 `Asia/Shanghai` 当日。
  - `window`：与 `/api/skills` 相同的窗口对象。
  - `summary`：当前证据集合的 records / skills / operators / sessions / source/runtime 等摘要。
  - `actions`：前端可展示的非破坏下一步动作文案；不得表示已经完成公司库写入或永久忽略。
  - `applied_filters`：实际生效的时间窗和筛选条件。
  - `ignored_filters`：因 evidence kind 强制口径而被忽略的冲突筛选。
  - `top_skills`：当前证据集合按 used records 降序的 skill 分组。
  - `top_operators`：当前证据集合按 used records 降序的 operator 分组，空 operator 不进入 operator Top。
  - `daily`：当前证据集合按 `Asia/Shanghai` day 聚合的日级 used records。
  - `records`：窗口内原始会话 x skill used 记录，字段至少含 `day/first_seen/skill/operator/runtime/source/session_id`。
  - `items`：名单型证据；`idle` / `unused_ratio` 用于展示 installed-but-unused skill 名单，`zero_install` 用于展示 cataloged-but-not-installed skill 名单。
- 该端点只统计 `mode='used'` records。`equipped` 不得进入 `summary.records`、`top_*`、`daily` 或 `records`。
- `src=non_catalog` 等价于服务端来源 `非公司库`；catalog 中 `external` 不算未收录。
- `kind=untracked` 必须只包含 `source=非公司库` 的 used records。
- `kind=total` 的 `summary.records` 必须等于同一窗口 `/api/skills` 响应里的 `period_comparison.current_sessions`。
- `kind=idle` / `kind=unused_ratio` 的名单口径必须使用 company catalog `own|meta` 中的 installed names 减去当前窗口 used company names；它们可返回空 `records`，但必须返回 `items`。
- `kind=zero_install` 的名单口径必须使用 company catalog `own|meta` names 减去 installed names；可返回空 `records`，但必须返回 `items`。
- Evidence `kind` 是强制证据口径，用户筛选是附加约束。`q/rt/skill/operator` 与 `kind` 取交集；`src` 只有在不与
  `kind` 的强制 source 口径冲突时才生效。若冲突，后端必须忽略冲突 `src` 并在 `ignored_filters` 说明。
- `limit` 默认 100，上限 500；`offset` 默认 0。非法 kind、limit、offset 返回 400。

### SKILLS 首屏证据入口

- `/skills` 首屏所有可见聚合数字必须能进入证据页或同页名单证据；不得只显示数字而没有下钻。
- 按 Skill 视角的 8 格摘要改称「过去 W 变化」或同义文案，不得使用 `KPI 环带`。
- 按 Skill 视角的健康/状态条改称「问题线索」或同义文案，不得使用综合健康分语义，也不得显示 `良好`、`偏高`、`需关注` 作为考核标签。
- 每个摘要格至少包含：
  - 主数值；
  - 证据入口；
  - 若该聚合背后有名单，展示 Top 1-3 个 skill/operator 名称。
- `总触发次数` 的证据入口必须进入 `/skills/evidence?kind=total`，并继承当前 `w/wstart/wend/q/rt/src/view/topn`。
- `未收录占比` 和 `有使用但未收录` 的证据入口必须进入 `/skills/evidence?kind=untracked`，并继承当前窗口和
  `q/rt/view/topn`；若当前 `src` 与 non_catalog 冲突，不得让冲突 `src` 导致空证据。
- `闲置 Skill 数`、`装了没用比例` 与 `收录但零装机` 的证据入口必须进入名单型证据页，展示具体 skill 名单与装机人数。

### 待处理线索

- 按 Skill 视角的待处理线索顺序固定为：
  1. 有使用但未收录；
  2. 装了 W 内没用；
  3. 收录但零装机。
- `有使用但未收录` 是首屏第一优先线索，必须展示 Top items、触发次数和至少一个证据动作。
- 待处理线索行的动作必须是非破坏操作，例如 `看证据`、`找使用者`、`打开详情`、`忽略本页`。
- `忽略本页` 仅能写 React 组件内存状态，不得写 localStorage/sessionStorage 或后端。

### 证据页

- `/skills/evidence` 必须保留当前 SKILLS 时间窗和筛选语义；刷新、复制链接和前进后退必须保持证据 kind 与筛选。
- 证据页必须展示：
  - 返回 SKILLS 的入口；
  - 当前窗口；
  - 下一步动作；
  - 分组证据；
  - 原始记录表或名单证据。
- 原始记录的具体时间 `first_seen` 按浏览器本地时区展示；缺失 `first_seen` 时按服务端 `day` date-only 语义展示，规则与 `/skill/:name`、`/operator/:name` 最近记录一致。
- 最近记录/证据记录无下钻目标时不得呈现可点态。
- SKILLS 统计域响应式规则同样适用于 `/skills/evidence`：桌面 `>1080px`、平板 `601px-1080px`、手机 `<=600px`；页面根不得横向滚动。

## 可验证行为

- 造数据：7 天内 `alpha own used=2`、`beta external used=1`、`ghost non_catalog used=3`、`ghost equipped=2`。
  - `/api/skills/evidence?kind=total&w=7d` 的 `summary.records=6`，records 不含 equipped。
  - `/api/skills/evidence?kind=untracked&w=7d` 的 `summary.records=3`，records 只含 `ghost`，不含 `beta` 或 equipped。
- `/api/skills/evidence?kind=total&w=7d` 的 `summary.records` 与同一窗口 `/api/skills?w=7d` 响应里的 `period_comparison.current_sessions` 相同。
- 造安装态：`idle-own` 在 profile installed，窗口内未 used，且 catalog type 为 `own`。
  - `/api/skills/evidence?kind=idle&w=7d` 的 `items` 含 `idle-own`，并带 `installers`。
- 造公司库收录但未安装态：`meta-tool` 在 company catalog `meta` 中，未出现在 profile installed。
  - `/api/skills/evidence?kind=zero_install&w=7d` 的 `items` 含 `meta-tool`，`installers=0`。
- `/skills?view=skill&w=7d` 首屏不显示 `KPI 环带`、`治理健康`、`良好`、`偏高`、`需关注`。
- 点击 `/skills` 首屏 `总触发次数` 的证据入口 → 跳到 `/skills/evidence?kind=total&w=7d...`，证据表显示当前窗口 records。
- 点击 `/skills` 首屏 `有使用但未收录` 的 `看证据` → 跳到 `kind=untracked`，证据表只展示非公司库 used records。
- 从 `/skills?src=own&w=7d` 点击 `有使用但未收录` 的 `看证据` → 证据页仍展示 non_catalog used records，
  payload 的 `ignored_filters` 标明 `src=own` 被 `kind=untracked` 覆盖。
- 375x812 打开 `/skills/evidence?kind=total&w=30d` → 页面根无横向滚动；记录表以摘要行展示。
