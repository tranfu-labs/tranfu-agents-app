# 变更提案:skills-operator-view(SKILLS 按人视角 / 视角切换)

- 状态:Proposed
- 关联:skills-stats-page(前身:SKILLS 总览页只有 skill 视角)、openclaw-equipped-skill-usage(装备态语义)

## 背景 / 问题
skills-stats-page 把 SKILLS 页做成了一条"以 skill 为准"的主线(柱状图/主表/漏斗都以 skill 为主语),
只能回答"哪个 skill 最热"。运营同样关心对等的另一个维度——"谁用得最多"。但"人"和"skill"是
同级问题,不该把"人"塞进页尾一个小区块当 skill 的附属:既局促,地位也不对等。

## 目标(经访谈逐项拍板,口径见 design.md)
- SKILLS 总览页顶部加 `[ 按 skill ] / [ 按人 ]` 视角切换,**整页切主语**:柱状图、主表、下钻
  整页同一主语,不混搭。
- 按人视角:每日柱状图按 operator 分段、人排行主表、单操作员下钻详情(独立视图 + 返回)。
- 人维度计量 = 会话×skill 去重使用次数(沿用 `skill_uses` 主键),语义为"此人在多少个会话里
  用过 skill",非真实调用次数。
- 双向下钻闭环:skill 下钻看"谁用了它"、人下钻看"他用了啥",人详情 skill 行可点回 skill 下钻。

## 非目标
- 不动采集链路与 `skill_uses` 表结构(operator 字段已在采集,数据已就绪)。
- 人视角彻底不碰 equipped(装备态只在单 skill 下钻出现);不为人视角引入装备态概念。
- 不改 skill 视角既有口径与既有两个端点的行为。
- 不做 operator 之间的对比/协作分析、不做"未识别"兜底聚合。

## 方案概述(详见 design.md)
新增两段只读聚合:`/api/skills` 增 `operator_table` / `operator_daily`(只 used、排除空 operator),
新增 `GET /api/operator/{name}` 单人详情。前端把柱状图分段维度参数化(skill ↔ operator)、
总览加视角切换状态、新增 operator-detail 视图与 `/operator/:name` 路由。漏斗作为公司库健康面板
常驻、不随视角变。

## 影响
- specs/board:新增 `operator_table`/`operator_daily` 字段与 `/api/operator/{name}` 端点;
  新增"视角切换"与按人聚合规则。
- 不触碰 ingest 侧任何行为,不改 skill 视角既有契约(向后兼容,仅在 `/api/skills` 增字段)。
