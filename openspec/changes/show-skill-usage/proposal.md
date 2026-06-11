# 变更提案:show-skill-usage(skill 使用排行——聚合与看板)

- 状态:Proposed(依赖 track-skill-usage 落库并积累数据后实施)
- 关联:specs/board、track-skill-usage(数据来源)、ADR-0004(profile 可选、服务端计算)

## 背景 / 问题
track-skill-usage 让 `skill_uses` 表持续积累"会话×skill"记录,但只有数据没有视图。
本变更把它变成可决策的画面:团队看"哪些 skill 真被用起来",运营看"哪些该维护、哪些该下架"。

## 目标
- `GET /api/state` 增加 `skills` 聚合块:每个 skill 的 7 天/30 天/累计使用会话数、
  30 天使用人数(去重 operator)、最近使用日期。
- 看板新增 Skills 排行区,按 30 天使用会话数降序;无数据时优雅空态。

## 非目标
- 不做 skill 效果/成功率(未来单独立项,数据钩子已由 track-skill-usage 保留)。
- 不做 skill 详情下钻、不做按人查询(需求方未选"个人维度"目标)。
- 不改 leverage 现口径("从装了多少升级为用了多少"另议)。

## 方案概述(详见 design.md)
聚合读时现算(与 `reuse`/`leverage` 同风格,量级小不需缓存);看板沿用单文件 HTML +
`/api/state` 轮询,新增一个排行区块,不引入新接口、不破坏现有卡片模型。

## 影响
- specs/board:`/api/state` 返回结构 + skills 块,看板 + 排行区(见本 change 的 spec delta)。
- 不触碰 ingest 侧任何行为。
