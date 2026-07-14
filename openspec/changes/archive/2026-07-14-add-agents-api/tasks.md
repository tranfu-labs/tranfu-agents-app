# 任务：add-agents-api

## 方案与事实源

- [x] 诊断 `/agents` 当前全局 state + 浏览器重算链路并确认独立接口目标。
- [x] 定义 `/api/agents` 查询参数、响应契约、90 天边界和 skeleton 线框。
- [x] 反思方案与既有 board/身份/时间规范的一致性。

## 服务端

- [x] 实现 Agents 时间窗、过滤、signal、排序和 payload 纯函数。
- [x] 新增 `GET /api/agents` 路由并保持 `/api/state.agent_overview` 兼容。
- [x] 补齐预设/custom/非法窗口/身份/排行/过滤/响应契约测试。

## 前端

- [x] 新增 Agents payload 类型与独立 API hook。
- [x] 将 `/agents` 从 `StateRoute` 解耦并消费服务端统计字段，底部明细表新增操作员列。
- [x] 增加 loading skeleton、错误态和响应式样式。
- [x] 补齐 query、payload 与独立加载回归测试。

## 验证

- [x] 运行服务端 py_compile、pytest 和覆盖率门槛。
- [x] 运行前端 unit 和 build。
- [x] 验证 `/api/agents?w=7d`、custom 示例及 `/agents` skeleton/筛选行为。
- [x] 对照 proposal、design、spec delta 和 wireframe 反思代码符合度。
