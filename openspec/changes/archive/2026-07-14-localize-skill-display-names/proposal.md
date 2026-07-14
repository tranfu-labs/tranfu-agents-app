# 提案：localize-skill-display-names

## 背景

SKILLS 统计当前把用于身份、URL 与聚合的原始 slug 直接呈现给用户，例如 `openspec-driven-development`。公司库 catalog 实际已经从对应 `SKILL.md` 导出 `display_name` 与 `display_name_zh`，但服务端同步时丢弃了这两个字段；本机 profile 采集也只读取 `name/description`。因此总览、图表、线索页、详情页、Agent 详情和后台清理台都无法根据当前界面语言显示可读名称。

## 提案

- 保留公司库 catalog 的 `display_name/display_name_zh`，并让 shim 从本机 `SKILL.md` profile 中上报同名字段。
- 服务端以 slug 为稳定 identity；每个含 Skill 的 API 对象直接输出可选 `display_name/display_name_zh`，payload 顶层同时输出双语名称映射，供其它页面和集成批量复用。公司库元数据优先，本机 profile 只补缺失字段。
- 中文显示按 `display_name_zh → display_name → slug` 回退，英文按 `display_name → display_name_zh → slug` 回退。
- `/skills` 及其所有下钻页、Skill 图表/抽屉/线索/导出、Agent 详情与后台 Skill 清理视图统一使用本地化名称；URL、查询、删除目标、颜色和数据库继续使用 slug。
- 搜索同时匹配 slug、英文显示名和中文显示名，服务端分页证据查询也遵守同一规则。

## 影响

- 影响 `server/catalog.py`、`server/routes/board.py`、`server/routes/admin.py`、`shims/tf_profile.py` 与相关 API payload。
- 影响 `frontend/src/lib/types.ts`、新增的 Skill 名称展示纯函数、Skills 全部路由/组件、通用图表、Agent 详情与 Admin 清理台。
- 更新 board/ingest 行为事实源、Skill 页面与 Agent/Admin 线框说明、协议、模块地图和 AGENTS 约定。
- 不迁移 SQLite，不改 `skill_uses.skill`，不改变历史聚合口径或现有深链。
