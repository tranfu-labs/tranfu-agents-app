# 任务：polish-skills-evidence-first-screen

> 归档动作（移动 change / 合并 spec-delta / 回流 wireframes）不写在这里，参见 `openspec/changes/AGENTS.md`。

## 前端 · `/skills`

- [x] mobile 控制条默认折叠为一行摘要：`7d · 按 Skill · 全部 runtime/source · 筛选`，展开后显示完整筛选控件。
- [x] 确保 375x812 第一屏先露「问题线索」和「待处理线索」，而不是完整筛选表单。
- [x] 摘要格主文案改为短结论，不直接铺长 skill name，不用 `/` 串长名单。
- [x] 摘要格重复的「证据」文字入口改成 icon entry，并补齐 tooltip / `aria-label`。
- [x] `待处理线索` 行正文改为事实行：skill、次数/装机、operator、来源/状态。
- [x] `待处理线索` 桌面动作改为 icon group：原始记录、按使用者看证据、忽略。
- [x] 移除可见 `找人` 文案；保留语义到 tooltip / `aria-label`。
- [x] `待处理线索` mobile 行点击进入 evidence，次级动作收进 `...` 菜单。
- [x] `忽略` 只做当前页面临时隐藏；刷新或重新 mount 后恢复，不写 localStorage/sessionStorage/后端。

## 前端 · `/skills/evidence`

- [x] 页头压缩到返回入口、标题、窗口和筛选 chip，避免 1440x900 第一屏被标题区吃掉。
- [x] 摘要区从固定 KPI cards 改为 kind 专属上下文句。
- [x] `kind=total` 的未收录显示为 `其中 N 条来自未收录 skill`，并可点到相同筛选下的 `kind=untracked`。
- [x] 顶部动作从文字按钮改为 icon toolbar 或紧凑 tabs，不使用 `找使用者` 这类铺开的文字链接。
- [x] 有 raw records 的 kind 默认停在「原始记录」，1440x900 第一屏露出 records 表头和前几行。
- [x] `idle / unused_ratio / zero_install` 默认停在「名单」，1440x900 第一屏露出名单表表头和前几行。
- [x] `Top skills / Top operators` 改为辅助区；若并排会压窄主表，则自动下置到 records/list table 后方。
- [x] 主表至少能读清 `time / skill / operator / runtime / source`。

## 测试

- [x] 前端单测覆盖 mobile 控制条摘要格式。
- [x] 前端单测覆盖摘要格不展示长 skill name 串。
- [x] 前端单测覆盖 evidence link builder 保留窗口/筛选，并处理 `kind=untracked` 的 source 冲突。
- [x] 前端单测覆盖临时忽略不写 localStorage/sessionStorage，重新 mount 后恢复。
- [x] 前端单测或 accessibility 断言覆盖 icon actions 的 `aria-label`，并确认没有可见 `找人` 文案。
- [x] `npm --prefix frontend run test:unit`。
- [x] `npm --prefix frontend run build`。

## AI 验证

- [x] 375x812 打开 `/skills?view=skill&w=7d`，截图确认首屏先露线索、页面根无横向滚动、控制条默认折叠。
- [x] 375x812 验证待处理线索：行点击进 evidence，次级动作在 `...` 菜单。
- [x] 1440x900 打开 `/skills/evidence?kind=total&w=7d`，截图确认第一屏露 records 表头和前几行。
- [x] 1440x900 打开 `/skills/evidence?kind=untracked&w=7d`，截图确认第一屏露 records 表头和前几行。
- [x] 1440x900 打开 `/skills/evidence?kind=idle&w=7d` 与 `kind=zero_install`，截图确认第一屏露名单表。
- [x] 验证 `Top skills / Top operators` 不压窄主表，必要时下置。
