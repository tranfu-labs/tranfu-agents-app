# skills-clue-pages

## 背景

`/skills` 的「待处理线索」和详情页把三类不同治理任务塞进同一个 evidence 概念里，导致用户难以行动：

- 「有使用但未收录」需要看原始使用记录和使用者占比。
- 「装了没用」需要知道谁装了但没用，而不是 Top Skills / Top Operators。
- 「收录但零装机」需要名单页，不需要 usage records 分组。

同时，页面里直接露出 `evidence`、`src: non_catalog`、`window_start/window_end`、`8/48` 等内部表达，且卡片右侧操作全是图标，`×` 容易被理解为删除。

## 目标

- 新增用户可见 clue 详情路由：
  - `/skills/clues/untracked?w=7d&skill=coolify-deploy`
  - `/skills/clues/idle?w=7d&skill=write-spec`
  - `/skills/clues/zero-install?w=7d`
- 待处理线索三类 row 分模板展示，不再共用字段。
- `untracked` 详情页首屏先展示 Top Operators，并显示 `records/total · percent`。
- `idle` / `zero-install` 详情页不展示 Top Skills / Top Operators，改为名单页。
- `idle` API item 返回安装者明细，让页面能回答“谁装了”。
- 前端文案从“证据”收敛为“记录 / 名单 / 分组”，筛选 chip 不再露内部字段名和枚举值。
- 旧 `/skills/evidence?kind=untracked|idle|zero_install` 链接兼容跳转到新 clue 路由。

## 非目标

- 不改 `/api/skills/evidence` 的 API 路径和现有统计 kind 契约。
- 不实现后端永久忽略或跨窗口忽略持久化；本次仍保持页面内临时忽略。
- 不为零装机强行造 owner / contributor 字段；没有事实来源时只展示已有名单事实。

## 影响面

- 后端：`server/routes/board.py` 的 SKILLS governance/evidence payload。
- 前端：路由、待处理线索组件、clue 专页、i18n 文案和 helper。
- 测试：前端 URL/helper/copy 单测，后端 evidence/governance API 单测。
- 文档：`openspec/specs/board/spec.md`、`docs/wireframes/`、`AGENTS.md`、`docs/architecture/module-map.md`。
