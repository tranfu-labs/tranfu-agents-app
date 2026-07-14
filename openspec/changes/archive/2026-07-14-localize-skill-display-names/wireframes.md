# 线框增量：Skill 本地化显示名称

基线：`docs/wireframes/pages/skills.md`、`skills-new.md`、`skills-evidence.md`、`skills-clues.md`、`skill-detail.md`、`operator-detail.md`、`agent-detail.md`、`admin.md`。页面结构与流转不变，本变更只统一可见名称与搜索语义。

## pages/skills.md

```text
┌─ 排行 / 趋势 / 明细 / 待处理 / 漏斗 ──────────────────────┐
│ 中文：OpenSpec 驱动开发        █████████ 128  [↗]       │
│ EN:   OpenSpec-Driven Development ███████ 128 [↗]       │
│ 搜索 [OpenSpec 驱动开发____] → 命中同一 slug              │
└───────────────────────────────────────────────────────────┘
```

## pages/skills-new.md · skills-evidence.md · skills-clues.md

```text
┌─ 列表 / 原始记录 / Top Skills / 筛选 chip ────────────────┐
│ Skill: OpenSpec 驱动开发                                  │
│ [Skill：OpenSpec 驱动开发]  ← chip 不暴露原始 slug         │
└───────────────────────────────────────────────────────────┘
```

## pages/skill-detail.md · operator-detail.md

```text
┌─ Skill 详情 / 按人 Skill 排行与趋势图例 ──────────────────┐
│ OpenSpec 驱动开发  [公司自研]                              │
│ 图例 ● OpenSpec 驱动开发                                  │
└───────────────────────────────────────────────────────────┘
```

## pages/agent-detail.md · admin.md

```text
┌─ Agent 已安装 Skill / Admin Skill 清理预览 ───────────────┐
│ OpenSpec 驱动开发                                         │
│ 操作 identity（隐藏）：openspec-driven-development        │
└───────────────────────────────────────────────────────────┘
```

## 注释

| 编号 | 元素 | 状态/交互 | 数据来源 | 引用控件 |
|---|---|---|---|---|
| ① | 本地化 Skill 名称 | 随中/英文即时切换；点击、筛选、颜色与 URL 仍按 slug | catalog/profile 双语元数据 | 文字、表格、图例、tooltip |
| ② | 名称搜索 | slug/英文/中文任一命中；结果仍以 slug 区分 | 前端 helper + evidence 服务端扩展 | 搜索框 |
