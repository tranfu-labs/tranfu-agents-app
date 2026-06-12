# 变更提案:skills-stats-page(SKILLS 独立统计页)

- 状态:Proposed
- 关联:specs/board、show-skill-usage(前身:看板侧栏排行)、openclaw-equipped-skill-usage(装备态语义)、
  ADR-0015~0018(四 runtime 采集链路)

## 背景 / 问题
show-skill-usage 把排行塞进看板右侧栏,只能回答"哪些 skill 最常用"。
运营实际想看的更多:使用趋势怎么变、谁在哪个 runtime 用、公司库(tranfu-skills catalog)的
skill 采纳到了哪一步、哪些装了没人用。侧栏空间放不下这些,公司库采纳漏斗还需要外部数据源
(catalog index.json),不适合继续往看板里堆。

## 目标(经需求访谈逐项拍板,口径细节见 design.md)
- SKILLS 升级为第三个顶级视图(看板 / Agents / SKILLS);看板侧栏排行区**整个移除**。
- 总览页结构:筛选条 → 每日堆叠柱状图 → 排行主表(只含 used)→ 公司库采纳漏斗。
- 行级下钻:单 skill 独立详情视图(日级趋势、runtime/operator 分布、最近使用记录、装备态)。
- 漏斗三层:catalog 收录(own+meta)→ 已安装(≥1 个 agent)→ 30 天有人使用;
  第 2 层减第 3 层的差集即闲置名单。

## 非目标
- 不动采集链路(四 runtime 上报照旧,`skill_uses` 表结构不变)。
- 不做 skill 效果/成功率评估。
- `/api/state.skills` 字段保留不删(协议兼容),仅前端不再消费。
- catalog 中 external 类型不进漏斗(在主表中照常出现,来源标 external)。

## 方案概述(详见 design.md)
新增两个只读聚合接口(总览 + 单 skill 详情),不进 2s 轮询;服务端定时拉取 catalog 并缓存,
失败降级用旧缓存。前端沿用单文件 HTML 零依赖风格,柱状图用内联 SVG 手绘,不引入图表库。

## 影响
- specs/board:新增两个接口与 SKILLS 视图规则;修改看板前端规则(移除侧栏排行区)。
- 不触碰 ingest 侧任何行为。
