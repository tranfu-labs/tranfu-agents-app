# Board Spec Delta

## MODIFIED Requirements

### SKILLS 路由

- React SPA 必须支持 `/skills/clues/untracked`、`/skills/clues/idle`、`/skills/clues/zero-install` 三类治理线索详情页。
- 旧 `/skills/evidence?kind=untracked|idle|zero_install` 必须兼容，并重定向到对应 `/skills/clues/...` 路由；其它 `/skills/evidence` kind 保持通用记录页。
- `/skills/clues/*` 与 `/skills/evidence` 一样，不得被全局 `/api/state` 首包阻塞，必须先挂载自身 loading/skeleton 并并行请求 SKILLS API。

### SKILLS 待处理线索

- `/skills` 的待处理线索必须按 kind 使用独立 row 模板：
  - `untracked`: `N 条记录 · M 人 · 上次使用 MM-DD`，不得重复展示 `非公司库` 来源。
  - `idle`: `N 人安装 · 当前窗口 0 次 · 上次使用 MM-DD|从未使用`。
  - `zero_install`: `0 人安装 · 收录 MM-DD`。
- 待处理线索每行主操作必须收敛为查看图标和可见文字 `忽略`；不得再用 `×` 作为忽略按钮。
- 待处理线索分组摘要不得使用 `8/48` 这类裸分数，必须显示为 `48 个未收录，展示前 8` 或 `5 个零装机，已全量展示` 这类明文。

### SKILLS clue 详情页

- `/skills/clues/untracked` 必须第一屏先展示 Top Operators，并显示 `records/total · percent`，百分比分母是当前 clue 记录总数。
- `/skills/clues/untracked` 在 URL 带 `skill=` 时必须隐藏 Top Skills。
- `/skills/clues/idle` 必须第一屏展示安装者名单，字段至少包含 skill、安装人数、安装者、上次使用；不得展示 Top Skills / Top Operators。
- `/skills/clues/zero-install` 必须第一屏展示零装机名单；不得展示 Top Skills / Top Operators。
- clue 详情页筛选 chip 必须展示用户语义，不得暴露 `window_start`、`window_end`、`src: non_catalog` 等内部字段名或枚举值。
- clue 详情页和待处理线索相关用户可见文案必须使用 `记录 / 名单 / 分组`，不得使用 `证据` 描述这些线索。

### SKILLS evidence API

- `/api/skills/evidence?kind=idle|unused_ratio` 的 `items[]` 必须包含 `installers_detail[]`，每项至少包含 `operator`、`agent_key`、`runtime`、`profile_updated_at`。
- `/api/skills/evidence?kind=zero_install` 的 `items[]` 必须返回 `installers=0` 与空 `installers_detail=[]`。
- `/api/skills` 的 `governance.idle_installed.top[]` 必须包含 `last_day`，用于展示已安装但当前窗口未使用 skill 的历史最后使用日。

## ADDED Scenarios

- 打开 `/skills/clues/untracked?w=7d&skill=coolify-deploy`，第一屏显示 Top Operators；operator 行显示 `5/7 · 71%` 这类占比，且不显示 Top Skills。
- 打开 `/skills/clues/idle?w=7d&skill=write-spec`，第一屏显示安装者名单，能看到安装该 skill 的 operator / agent / runtime。
- 打开 `/skills/clues/zero-install?w=7d`，页面显示零装机 skill 名单，不显示 Top Skills / Top Operators。
- 打开旧链接 `/skills/evidence?kind=idle&w=7d&skill=write-spec`，前端跳转到 `/skills/clues/idle?w=7d&skill=write-spec`。
- 从 `/skills?src=own&w=7d` 点击未收录线索，进入 `/skills/clues/untracked?w=7d&src=non_catalog...`；页面 chip 显示 `来源：未收录`，不显示 `non_catalog`。
