# 设计:show-skill-usage

## 改动文件与职责
- `server/app.py` —— `_snapshot()` 增加 `skills` 数组:对 `skill_uses` 按 skill 名 GROUP BY,
  每项产出 `name`、`sessions_7d`、`sessions_30d`、`sessions_total`、`users_30d`(去重 operator)、
  `last_day`(最近使用日期)。排序:`sessions_30d` 降序,平手按 `sessions_total`。
  时间窗口按 UTC 日切,与既有活跃统计口径一致。
- `dashboard/index.html` —— 新增 SKILLS 排行区块:
  表格列 = skill 名 / 7 天 / 30 天 / 累计 / 30 天使用人数 / 最近使用。
  暗亮双主题(CSS 变量 + `body.light`)与手机窄屏(≤600px)遵循现有样式;
  `skills` 为空时显示占位文案,不留空洞、不报错。

## 运营判读约定(写进看板提示或文档,不做自动判定)
"该下架?"的信号 = 最近使用日期久远 + 30 天会话数低 + 使用人数 ≤1。
看板只给数字,判断留给人——会话成败归因脏,自动标记容易误导(需求方已确认效果评估不在本期)。

## 性能
读时 GROUP BY,表量级一年数万行;`skill_uses` 建 `skill` 索引即可。
若未来轮询变慢再考虑缓存,本期不做(避免过早复杂化,与单容器约束一致)。

## 依赖与顺序
track-skill-usage 上线先行,数据积累至少数天后本变更的排行才有意义;
但实现可并行,验收用造数完成,不阻塞。
