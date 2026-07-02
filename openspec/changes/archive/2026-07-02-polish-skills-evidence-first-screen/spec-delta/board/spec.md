# spec-delta：board（polish-skills-evidence-first-screen）

> 本 delta 描述 `/skills` 与 `/skills/evidence` 从「证据入口已具备」继续收紧为「首屏先看到下一步，证据页先看到事实」。归档时把下面的 MODIFIED / ADDED 合并回 `openspec/specs/board/spec.md`。

## MODIFIED

### SKILLS 总览首屏

- `/skills` 手机窄屏 `<=600px` 下，控制条默认折叠为一行摘要。摘要至少包含当前窗口、视角、runtime/source 筛选摘要和筛选入口，例如 `7d · 按 Skill · 全部 runtime/source · 筛选`。完整筛选控件只能在用户展开后显示。
- `375x812` 打开 `/skills?view=skill&w=7d` 时，第一屏必须先露出「问题线索」和「待处理线索」的实质内容；不得让完整筛选表单占据第一屏主体。
- 按 Skill 视角「过去 W 变化」摘要格只展示短结论，不得直接铺长 skill name 列表。长名单只能出现在「待处理线索」、`/skills/evidence` 或展开详情中。
- 摘要格若必须露对象，只能露 1 个短名；超长名必须截断，不能用 `/` 拼接多个长名。
- 摘要格不得在每格重复显示可见文字「证据」作为入口。证据入口应使用 icon button，并通过 tooltip / `aria-label` 表达 `查看证据`、`查看名单`、`查看集中度证据` 等语义。

### 问题线索与待处理线索

- 「未收录 / Top3 / 覆盖率 / 平均 skill/会」等线索的主语应优先对象驱动或事实驱动；百分比可作为次级说明，不得作为唯一主句。例如主句可为 `figma / coolify-deploy 正在被自发使用，但还没进入公司库`，次级说明为 `4 records · 2 operators · 100% non_catalog`。
- `待处理线索` 行正文只展示事实，不展示一排文字动作。事实行示例：`figma · 3 次 · alice/bob · 未收录`。
- `待处理线索` 桌面动作收为 icon group，至少包含：
  - 原始记录：打开 evidence records；
  - 使用者：按 operator 分组看这条线索的证据；
  - 忽略：当前页面隐藏。
- 界面不得使用可见文案 `找人`。对应语义应为 `按使用者看证据`，并通过 tooltip / `aria-label` 暴露。
- `待处理线索` mobile 行点击进入 evidence；次级动作进入 `...` 菜单，不得在窄屏行内铺一排文字按钮。
- `忽略` 只允许当前页面内临时隐藏，刷新、重新进入页面或重新 mount 后恢复；不得写入 localStorage、sessionStorage 或后端。

### SKILLS 证据页

- `/skills/evidence` 不是另一个 dashboard。它的第一职责是回答「这批事实到底是什么」。
- evidence 页头必须紧凑，避免标题区和摘要区在 1440x900 下吃掉第一屏主体空间。
- evidence 摘要区不得固定渲染 `RECORDS / SKILLS / OPERATORS / SESSIONS / UNTRACKED / COMPANY` 这类 KPI cards。摘要必须按 kind 收敛成上下文句：
  - `total`：`284 records · 64 skills · 8 operators · 188 sessions，其中 92 条来自未收录 skill`
  - `untracked`：`92 条未收录使用 · 46 skills · 7 operators`
  - `idle`：`19 个装了但 7d 没用 · 33 installs`
  - `zero_install`：`5 个收录但零装机`
- `kind=total` 里的未收录数量不得单独以 `UNTRACKED N` 指标卡形式站着。它必须作为总证据摘要里的上下文切片展示，例如 `其中 N 条来自未收录 skill`，并能跳转到保留当前窗口和筛选语义的 `kind=untracked`。
- evidence 顶部动作不得铺成一排文字链接。`看原始记录 / 按 skill 分组 / 按使用者分组 / 复制` 等语义应收敛为 icon toolbar 或紧凑 tabs。
- 有 raw records 的 evidence kind（`total / untracked / runtime / source / top3 / coverage / operators / avg_per_session`）默认视图必须停在「原始记录」，且 1440x900 第一屏必须露出 records 表头和前几行。
- 无 raw records 的 evidence kind（`idle / unused_ratio / zero_install`）默认视图必须停在「名单」，且 1440x900 第一屏必须露出名单表表头和前几行。
- `Top skills / Top operators` 在 evidence 页是辅助分组，不得排在主表之前把 raw records 或名单表挤出第一屏。
- `Top skills / Top operators` 可放右侧辅助区，但不得压窄主表。主表至少要能读清 `time / skill / operator / runtime / source`；若并排导致主表变挤，分组必须放到主表下方。

## ADDED

### 可验证行为

- 375x812 打开 `/skills?view=skill&w=7d`：
  - 页面根无横向滚动；
  - 控制条默认显示一行摘要 `7d · 按 Skill · 全部 runtime/source · 筛选` 或等价实际筛选摘要；
  - 第一屏能看到「问题线索」和「待处理线索」的实质内容；
  - 不先展示完整筛选表单。
- `/skills?view=skill&w=7d` 的摘要格不得直接渲染 `openspec-driven-development / tranfu-website-design / strategy-first-development` 这类长 skill 串。
- `/skills?view=skill&w=7d` 的摘要格不得重复出现多个可见文字「证据」入口；证据入口应是 icon button，并有可访问名称。
- `/skills?view=skill&w=7d` 的 `待处理线索` 不得显示可见文案 `找人`；对应 icon action 的可访问名称为 `按使用者看证据` 或同义语义。
- `待处理线索` 点击忽略后当前页面隐藏，刷新或重新 mount 后恢复；前端不得调用 localStorage/sessionStorage 保存该状态。
- 1440x900 打开 `/skills/evidence?kind=total&w=7d`：
  - 第一屏露出 records 表头和前几行；
  - 摘要包含 `其中 N 条来自未收录 skill` 上下文切片；
  - 该切片可跳转到 `/skills/evidence?kind=untracked&w=7d...`。
- 1440x900 打开 `/skills/evidence?kind=untracked&w=7d`：
  - 默认停在原始记录；
  - 第一屏露出 records 表头和前几行。
- 1440x900 打开 `/skills/evidence?kind=idle&w=7d` 或 `/skills/evidence?kind=zero_install&w=7d`：
  - 默认停在名单；
  - 第一屏露出名单表表头和前几行。
- `/skills/evidence` 中 `Top skills / Top operators` 不得让主表列宽小到无法读清 `time / skill / operator / runtime / source`；不足时分组下置。
