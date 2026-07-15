# 任务：sync-token-usage-filters-url

## 方案与事实源

- [x] 采访确认参考 `/skills`，全部可见筛选与排序写 URL，临时抽屉/忽略状态不写 URL。
- [x] 输出 URL 状态、请求派生、字符线框、单元测试与浏览器验证方案。
- [x] 写入 board spec delta，并反思默认值、自定义半填写、请求抖动与特殊字符风险。

## 实现

- [x] 新增 token usage query-state/纯函数模块及单元测试。
- [x] 路由从 URL 派生时间范围和图表粒度 API query。
- [x] 顶部筛选、明细快捷筛选、隐藏零消耗和排序统一改为 URL 状态。
- [x] 补齐 Token Usage URL 行为相关文档事实。
- [x] 用 nuqs 共享 parsers 补真实序列化/解析往返测试，移除源码字符串伪集成测试。
- [x] 失效模型在当前范围 payload 到达后回退全部模型并清理 URL。
- [x] custom 无效范围显示提示、禁用刷新，离开 custom 时移除起止参数。
- [x] 澄清 ADR-0002 与既有只读外部 Token Usage 模块的边界。

## 验证

- [x] 运行 `npm --prefix frontend run test:unit`。
- [x] 运行 `npm --prefix frontend run build`。
- [x] 在 1440、768、375 三档验证筛选、刷新/复制/历史导航与 custom URL；主题变量和既有布局未改变。
- [x] 对照 proposal、design、spec delta 和 wireframe 逐条反思代码符合度。
- [x] 重新运行单测、构建和定向浏览器验证，并更新实现后反思。
