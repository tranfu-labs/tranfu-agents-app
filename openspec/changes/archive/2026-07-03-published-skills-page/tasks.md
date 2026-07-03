# 任务：published-skills-page

- [x] 服务端 catalog 解析保留 `version/author/updated_at/published_at/path/sha`，旧 catalog 缺字段时保持兼容。
- [x] 服务端 board 域实现新发布聚合：`own|meta`、`published_at` 转 `Asia/Shanghai` 日、当前窗口列表、上一窗口数量、安装数与窗口 used 数。
- [x] 扩展 `/api/skills` 响应类型与测试，覆盖已发布未使用、external 排除、上一窗口、无效 `published_at`。
- [x] 前端 types/i18n/link helper 支持 `新增发布 Skill` 与 `/skills/new`。
- [x] `/skills` 当前时间窗变化与问题线索替换 `平均 skill/会`，入口跳独立 `/skills/new`。
- [x] 新增 `/skills/new` 页面与路由，继承时间窗，展示新发布列表、空态、catalog stale/unavailable 状态和响应式布局。
- [x] 更新 change 线框：`/skills` 首屏替换项和 `/skills/new` 页面结构。
- [x] 验证：`python -m py_compile server/*.py server/routes/*.py`、相关 pytest、`npm --prefix frontend run test:unit`、`npm --prefix frontend run build`，并用浏览器检查 `/skills` 与 `/skills/new` 桌面/手机布局。
