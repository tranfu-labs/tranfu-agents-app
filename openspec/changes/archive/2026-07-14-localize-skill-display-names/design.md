# 设计：localize-skill-display-names

字符图见 `wireframes.md`，任务见 `tasks.md`，行为增量见 `spec-delta/{board,ingest}/spec.md`。

## 方案

### 1. 元数据采集与优先级

`server/catalog.py::_parse_catalog_payload` 对 `display_name/display_name_zh` 做非空字符串清洗后保留。`shims/tf_profile.py::_parse_skill_md` 从 frontmatter 读取 `name/description/display_name/display_name_zh`，profile 的每个 Skill 项携带可选双语字段；shim 仍须 best-effort 且绝不抛错。

服务端在 catalog 模块集中构建 `slug -> {display_name, display_name_zh}` 映射。catalog 是公司库的权威元数据；profiles 只为 catalog 缺字段或非公司库 Skill 补值。冲突时不按 operator/runtime 分裂显示名，保证团队看板同一 slug 只有一套名称。

### 2. API 契约与稳定 identity

所有含 Skill 的 API 对象都直接增加可选 `display_name/display_name_zh`：包括 state 排行/profile 项、overview 的 daily/table/governance/funnel/published、evidence 的 records/items/top、Skill detail 根对象、operator detail 的 daily/skills/records，以及 Admin inventory/preview 的 Skill 对象。Skills 聚合 payload 顶层另增 `skill_names: {slug: {display_name, display_name_zh}}` 映射，方便图表、批量记录和其它调用方一次取得双语元数据，而不用遍历猜来源。

接口不返回单一、随请求语言变化的 `label` 作为事实字段；中英文原值同时返回，由消费方依据自己的 locale 选择。这样服务端响应可被其它页面、导出器或第三方集成直接复用。

所有 `name/skill` 现有字段继续表示 slug。服务端统计、source 匹配、幂等键、ETag、颜色、URL、筛选参数和删除选择器都继续使用 slug；新增字段只影响 presentation。旧前端面对缺失新字段仍按 slug 正常工作。

### 3. 前端统一显示纯函数

新增无副作用的 `skillDisplayName(slug, labels, lang)`、`skillSearchText(...)` 等 helper，执行已确认的回退链。组件接受 resolver 或 labels+lang，不把显示名写回选中态：

- `key/onSelect/selected/evidencePath/encodePathParam/skillColor` 使用 slug；
- 文本节点、图例、tooltip、筛选 chip、`aria-label/title` 使用显示名；
- 名称搜索覆盖 slug 与两个 display 字段；名称排序按当前语言显示名；
- CSV 输出 `skill_name`（当前语言）与 `skill_slug`（稳定技术列）。

`StackedSkillChart` 增加 segment label resolver，使柱段 key/color 仍是 slug，图例和浮层才翻译；operator/runtime 分段不受影响。

### 4. 全局显示面

覆盖 `/skills` 的排行、趋势、明细、抽屉、治理线索、漏斗、KPI 辅助名称；覆盖 `/skills/new`、`/skills/evidence`、`/skills/clues/:kind`、`/skill/:name`、`/operator/:name`；同时覆盖 `/agent/:key` 的 profile Skill 和 `/admin` Skill inventory/preview。查询 chip 中的 `skill=<slug>` 转成当前语言名称，但实际返回/跳转参数仍是 slug。

### 5. 服务端显示名搜索

overview/new 列表由前端在完整 payload 上匹配三种名称。evidence/clue 使用服务端分页，服务端先用 `q` 匹配双语映射得到候选 slug，再把候选与原有 `lower(skill) LIKE`、operator 条件做 OR 组合。精确 `skill=` 参数仍只接受 slug，避免显示名碰撞。

## 可测性

- Python 单测：catalog 清洗/保留；SKILL frontmatter 解析与异常兜底；catalog/profile 优先级；overview/evidence/detail/operator/state/admin 每个 Skill 对象的双语字段与顶层映射；中文/英文显示名 q 搜索；缺字段回退。
- TypeScript 单测：双语回退链、三字段搜索、显示名排序、slug identity 不变、图表 segment label resolver、CSV 双列。
- AI 验证：中文/英文分别检查 Skills 总览及所有下钻页；Agent/Admin 抽查；1440×900 与 375×812 检查长显示名可读、无根级横滚；核对 `openspec-driven-development` 的中英文结果与 URL slug。

## 风险与权衡

- 顶层映射比在每个嵌套行复制双语字段更紧凑，也更容易统一；代价是组件必须显式拿 resolver。通过集中 helper 和类型约束降低遗漏风险。
- 非公司库显示名依赖新的 profile 心跳；未升级或仅有历史 usage 的 Skill 会按规则回退 slug，这是可观察且兼容的降级。
- display name 可能重复，因此绝不允许它替代 slug 作为路由或选择器。
- 长中文/英文名称可能比 slug 更宽；沿用现有换行/截断和 title 机制，并做手机横滚验证，不为此改变信息架构。
