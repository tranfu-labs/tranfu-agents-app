# 设计:nav-new-skills-used-source

## 方案
服务端新增 used-only helper:

- assets: `COUNT(DISTINCT skill)` over `skill_uses WHERE mode='used'`。
- new skill names:按 skill 聚合 `MIN(day)` over `mode='used'`,再判断首次 used day 是否落在当前窗口。
- `/api/state` 与 `/api/skills` 复用同一套 helper,避免 nav 与 SKILLS 页再次分叉。
- `/api/skills?scope=new` 把 table/daily/operator/period/attribution/governance 约束到这批 new skill names;funnel 保持公司库整体口径。

前端:

- 顶部 copy 明确为 `7天新发现` / `New in 7d`;资产 copy 明确为 `Skill 资产` / `Skill assets`。
- 顶部 `+N` 是链接,目标 `/skills?w=7d&scope=new`,可键盘聚焦。
- `/skills` 手机首屏在折叠筛选摘要下方展示 `新发现 N` 链接,同样指向 `scope=new`。
- `scope=new` 激活时控制条显示 chip,可点击清除回 `scope=all`。

## 权衡
- 不使用 `skills_seen` 做 nav 数字。它继续适合内部发现/安装痕迹,但不能代表真实使用资产。
- 不把新增入口默认跳 raw evidence。用户需要先看到可行动名单、贡献者和上期变化;raw records 仍通过现有 evidence 入口追证。
- 不引入 KPI/红绿箭头/同比话术。新增名单只呈现事实列表和窗口对比字段,不做好坏评价。

## 风险
- 历史库里只有 profile/equipped 但没有 used 的 skill 会从 nav 资产数字中消失。这是预期口径收敛。
- `scope=new` 依赖 `skill_uses.day`;老数据如果缺 day,不会参与首次 used 判断。现有写侧会写入 `Asia/Shanghai` 统计日,测试覆盖当前路径。
