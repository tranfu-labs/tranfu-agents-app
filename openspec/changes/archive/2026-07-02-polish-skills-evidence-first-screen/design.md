# 设计：polish-skills-evidence-first-screen

## 事实源与约束

已读事实源：

- `docs/architecture/module-map.md`：前端只能走同源相对 API；除主题和 admin key 例外，不得使用浏览器持久存储。
- `openspec/specs/board/spec.md`：`/skills`、`/skills/evidence` 是 SKILLS 统计域；`/api/skills/evidence` 只统计 `mode=used`；evidence kind 强制口径优先于冲突筛选。
- `docs/adr/0015-skill-usage-per-session.md`：Skill 使用口径是会话 x skill x mode，不能引入调用次数或内容追踪。
- `docs/adr/0019-react-dashboard-build.md`：React SPA 可扩展路由，但最终仍是单容器、同源 API、无运行期 node。
- `docs/adr/0023-theme-preference-localstorage-exception.md`：除 `tf-theme-mode` 外不得把前端状态写入 localStorage。
- 上一轮归档：`openspec/changes/archive/2026-07-01-skills-evidence-first-screen/`。

## 方案

### 1. `/skills` mobile 控制条折叠

- 在 mobile `<=600px` 下把完整控制条改为默认折叠。
- 折叠态显示一行摘要：`{window} · {view} · {runtime/source summary} · 筛选`。
  - 默认示例：`7d · 按 Skill · 全部 runtime/source · 筛选`。
  - 有筛选时摘要必须反映实际状态，例如 `7d · 按 Skill · codex · non_catalog · 筛选`。
- 点 `筛选` 展开完整控件；展开后仍沿用 URL search params，不写本地持久化。
- 375x812 首屏验收以「问题线索」和「待处理线索」进入第一屏为准，不以控制条控件完整露出为准。

### 2. 摘要格去长名单、去重复文字入口

- `过去 W 变化` 摘要格只显示短结论：
  - `未收录：2 个 skill · 4 records`
  - `装了没用：16 个 skill`
  - `覆盖率：23/60 公司库 skill 有使用证据`
  - `Top3：使用集中在 3 个 skill`
  - `平均 skill/会：1.51`
- 具体 skill 名单只允许出现在：
  - `待处理线索` 的事实行；
  - `/skills/evidence`；
  - 摘要格展开详情或抽屉。
- 如果某个摘要格必须露对象，只露 1 个短名；超长名必须截断，不能用 `/` 拼接长名单。
- 每格的证据入口改成 icon button，使用可访问名称表达语义，例如 `aria-label="查看未收录使用证据"`；视觉上不重复显示「证据」文字。

### 3. 待处理线索事实行 + icon actions

- `待处理线索` 行正文只展示事实，示例：
  - `figma · 3 次 · alice/bob · 未收录`
  - `write-spec · 装机 4 人 · 7d 0 次`
  - `meta-tool · 公司库 · 零装机`
- 桌面右侧动作收成 icon group：
  - 原始记录：进入 evidence records。
  - 使用者：进入或聚焦按 operator 分组的 evidence，不露 `找人` 文案。
  - 忽略：当前页面隐藏该条。
- hover tooltip / `aria-label` 写清动作，例如 `按使用者看证据`。
- mobile：
  - 行点击进入主 evidence。
  - 次级动作进入 `...` 菜单。
  - 不在行内铺一排文字按钮。
- `忽略` 只存在 React 组件内存状态；刷新、重新进入页面、切换筛选后可恢复。不得 localStorage，不加后端 API。

### 4. evidence 页压缩页头和摘要

- 页头合并为紧凑两行以内：
  - 返回入口 + evidence 标题 + 窗口范围。
  - 生效筛选/ignored filters 用小 chip 行，不能形成大标题区。
- 摘要不再渲染固定六七个 KPI cards，改为 `kind` 专属上下文句。
- `kind=total` 句内的 `其中 N 条来自未收录 skill` 必须是可点击切片，跳转到相同筛选下的 `kind=untracked`。
- `看原始记录 / 按 skill 分组 / 找使用者 / 复制...` 这组动作改为 icon toolbar 或紧凑 tabs。若使用 tab，默认 tab 规则如下：
  - 有 raw records 的 `total / untracked / runtime / source / top3 / coverage / operators / avg_per_session` 默认停在「原始记录」。
  - 无 raw records 的 `idle / unused_ratio / zero_install` 默认停在「名单」。
  - 默认不得停在 `Top skills`。

### 5. evidence 主表优先

- 1440x900 验收：
  - 有 raw records 的 kind 第一屏必须露出 records 表头和前几行。
  - `idle / unused_ratio / zero_install` 第一屏必须露出名单表表头和前几行。
- `Top skills / Top operators` 作为辅助：
  - 可放右侧辅助区，但不得压窄主表；主表至少能读清 `time / skill / operator / runtime / source`。
  - 如果右侧辅助区导致主表过窄，分组放到 records 下方。
  - 分组不能排在主表之前把 raw records 挤出首屏。

## 线框

字符图单独落 `wireframes.md`，基线引用：

- `docs/wireframes/pages/skills.md`
- `docs/wireframes/pages/skills-evidence.md`
- `docs/wireframes/flow.md`

## 可测性评估

- 这轮主要是前端信息架构、响应式布局和交互语义，不改后端统计逻辑。
- 仍包含可测逻辑：
  - mobile 控制条摘要字符串；
  - evidence URL builder 对 `kind=untracked` 的 query 保留/改写；
  - 待处理线索临时忽略不持久化；
  - action icon 的 accessible name；
  - evidence kind 默认 tab / 主表优先规则。
- 因此需要前端单测；响应式首屏可见性用 Playwright/Browser 截图和 DOM 断言验证。

## 测试策略

### 前端单测

- mobile filter summary：
  - 默认 URL 渲染 `7d · 按 Skill · 全部 runtime/source · 筛选`。
  - 有 `rt/src/view/w` 时摘要反映实际状态。
- summary card formatter：
  - `openspec-driven-development / tranfu-website-design / strategy-first-development` 不直接出现在摘要格主文案。
  - 超长 skill name 只在允许区域展示，或被截断。
- evidence link builder：
  - 摘要格 icon 和待处理线索 icon 继承 `w/wstart/wend/q/rt/view/topn`。
  - `kind=untracked` 不被冲突 `src=own` 导致空证据。
- temporary ignore：
  - 忽略后当前页面隐藏；
  - 重新 mount 后恢复；
  - 不调用 `localStorage.setItem` / `sessionStorage.setItem`。
- accessibility：
  - icon actions 有 `aria-label` 或 tooltip 文本；
  - 不渲染可见 `找人` 文案。

### AI / 浏览器验证

- `npm --prefix frontend run test:unit`
- `npm --prefix frontend run build`
- 375x812 打开 `/skills?view=skill&w=7d`：
  - 页面根无横向滚动；
  - 控制条默认一行摘要；
  - 第一屏先露「问题线索」和「待处理线索」，不先露完整筛选表单；
  - 待处理线索 mobile 行点击进 evidence，次级动作在 `...` 菜单。
- 1440x900 打开 `/skills/evidence?kind=total&w=7d`：
  - 第一屏露 records 表头和前几行；
  - 摘要为一句上下文，未收录切片可点到 `kind=untracked`；
  - `Top skills / Top operators` 不抢主表。
- 1440x900 打开 `/skills/evidence?kind=idle&w=7d` 与 `kind=zero_install`：
  - 第一屏露名单表；
  - 默认 tab 停在「名单」。

## 权衡

- 不新增图表：把注意力放在语言、布局和首屏优先级，避免再次变成 dashboard。
- 不持久化忽略：遵守 ADR-0023，避免为轻量 UI 隐藏引入后端模型或浏览器业务状态。
- 不改后端 summary shape：优先在前端做展示收敛，只有发现 payload 缺字段时再最小补齐。
- 摘要格牺牲名单露出量：长名单转移到待处理线索和 evidence 页，换取首屏扫描效率。

## 风险

- 375 首屏空间紧，若顶部导航高度过高，仍可能挤压线索区。实现时要用截图验收真实 375x812，而不是只看 CSS 断点。
- icon-only actions 可能降低可发现性。必须用 tooltip、`aria-label` 和一致的图标顺序弥补。
- evidence 右侧辅助区在部分窗口宽度可能压窄主表。实现应允许通过 CSS grid/container query 降级为分组下置。
