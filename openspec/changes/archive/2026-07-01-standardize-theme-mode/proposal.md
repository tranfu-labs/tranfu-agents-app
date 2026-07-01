# 提案：standardize-theme-mode

## 背景
当前前端只在 React 内部用一个 `light` boolean 切换 `body.light`：

- 默认不跟随系统深浅偏好。
- 刷新后不记住用户显式选择。
- 浏览器原生控件和 UA 主题没有通过 `color-scheme` 明确声明。
- `theme-color` 固定为深色，浅色模式下浏览器地址栏/安装体验不一致。
- 首屏主题只能等 React effect 后应用，存在闪烁风险。

GitHub Issue 要求“优化深浅模式，采用业界通用标准做法”。采访确认的目标是三态主题：跟随系统 / 浅色 / 深色；本次允许对主题偏好使用持久化例外；同时处理 `color-scheme`、`theme-color` 与首屏应用。

## 提案
1. 将主题状态从 boolean 改为三态 `system | light | dark`。
2. 默认使用 `system`，通过 `prefers-color-scheme` 解析为实际浅/深主题，并在系统偏好变化时同步。
3. 允许唯一的前端持久化例外：使用 `localStorage` 固定 key 保存主题模式。只能存储 `system | light | dark`，不得存业务数据、身份数据、筛选状态或语言偏好。
4. 新增同源 `theme-init.js`，在应用启动前设置 `document.documentElement` 主题属性并更新 `theme-color`，避免首屏闪烁；不使用 inline script，继续满足 CSP `script-src 'self'`。
5. CSS 主题来源迁移到 `:root[data-theme="light|dark"]`，并设置 `color-scheme`，保留现有 CSS 变量体系。
6. 顶部导航把单按钮改为紧凑三态分段控件，保持中英文、键盘、窄屏可用。
7. 保持 manifest 默认 `theme_color` 与静态默认 `<meta name="theme-color">` 一致；运行时由主题脚本按实际主题覆盖 meta。
8. 同步规格、ADR 与线框：`board` 前端规则新增主题三态约束；`onboarding` 规格新增根静态 `theme-init.js` 分发约束；新增 ADR 记录对 ADR-0019“禁止本地存储”的窄修订；归档时回流顶部导航线框。

## 影响
- 影响模块：`frontend/` 主题状态、全局 CSS、顶部导航、HTML head、public 静态文件；`server/routes/onboarding.py` 根静态白名单；相关测试与文档。
- 不影响：事件协议、SQLite schema、collector 聚合、shim、安装协议、Skill 统计口径。
- 约束变化：原“前端不得使用浏览器本地存储”增加极窄例外，仅用于主题模式偏好；`/admin` 管理钥匙仍只使用 sessionStorage。该修订必须通过新增 ADR 显式记录，避免和 ADR-0019 冲突。
