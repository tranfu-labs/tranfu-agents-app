# spec-delta:board / SKILLS 管理者筛选 Lens

## 接口变更
- `GET /api/skills?days={7|30|90}` 新增 `governance.untracked_usage`:
  - `ratio`:当前 `days` 窗口内非公司库 used 会话占全部 used 会话比例;空分母为 0。
  - `used_sessions`:当前窗口内 `source=非公司库` 且 `mode=used` 的会话×skill 记录数。
  - `total_sessions`:当前窗口内全部 `mode=used` 的会话×skill 记录数。
  - `skill_count`:当前窗口内出现过的非公司库 Skill 数。
  - `top[]`:未收录 Skill 排行,每项含 `name/source/sessions/share/users_30d/runtime_counts/trend_14d/trend_days/last_day`。

## 规则(MUST)
1. 管理者 Lens 的未收录定义必须使用服务端来源字段 `非公司库`;catalog 中 `external` 不算未收录。
2. 管理者 Lens 只统计 `mode=used`;`equipped` 不得进入分母、分子或 Top 列表。
3. `ratio = used_sessions / total_sessions`;`top[].share = top[].sessions / total_sessions`;空分母时比例为 0。
4. `days` 参数影响 `governance.untracked_usage` 的分母、分子和 Top 列表窗口;`users_30d` 仍保持近 30 天用户数语义。
5. 前端 `/skills` 仅在按 Skill 视角的"使用排行"卡片内部展示管理者筛选 Lens:
   `[ 全部 Skill ] [ 未收录使用占比 X% · used/total ]`。
6. 默认 Lens 为 `all`,保持现有完整 Skill 主榜;选择 `untracked` 后只切换使用排行表格,不得影响每日趋势图、全局过滤条或公司库漏斗。
7. 按人视角不得展示该 Lens。

## 可验证行为
- 造数据:7 天内 own used 6、external used 2、非公司库 used 4、非公司库 equipped 3 →
  `total_sessions=12`,`used_sessions=4`,`ratio≈0.333`,Top 不含 external/equipped。
- `days=30` 包含更多历史非公司库 used 时,`governance.untracked_usage` 随窗口扩大更新。
- `/skills?view=skill&lens=all` 显示现有完整 Skill 主榜;`lens=untracked` 显示未收录占比列表。
- `/skills?view=operator&lens=untracked` 不显示管理者 Lens,操作员排行行为不变。
