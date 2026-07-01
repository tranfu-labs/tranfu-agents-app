# 设计：standardize-theme-mode

## 方案

### 主题状态模型
- 新增 `frontend/src/lib/theme.ts`：
  - `ThemeMode = 'system' | 'light' | 'dark'`
  - `ResolvedTheme = 'light' | 'dark'`
  - `resolveTheme(mode, prefersDark)`：`system` 取系统偏好，显式模式直接返回。
  - `readStoredThemeMode(storage)` / `writeStoredThemeMode(storage, mode)`：只接受合法枚举；storage 异常时吞掉并回退。
  - `applyTheme(mode, resolved)`：写 `document.documentElement.dataset.themeMode`、`dataset.theme`、`style.colorScheme`，同步 `meta[name=theme-color]`。
- `App.tsx` 不再维护 `light` boolean，改为维护 `themeMode` 和 `resolvedTheme`。
- `matchMedia('(prefers-color-scheme: dark)')` 只在 `system` 模式下决定实际主题；系统偏好变化时更新 `resolvedTheme`。

### 首屏初始化
- 新增 `frontend/public/theme-init.js`，在 `frontend/index.html` 的 app module 之前加载：
  - 从 `localStorage` 固定 key 读取主题模式。
  - 非法值或读取失败时使用 `system`。
  - 根据 `matchMedia` 得出实际主题。
  - 立即设置 `document.documentElement.dataset.theme` / `dataset.themeMode` / `colorScheme` / `theme-color`。
- 使用外部同源脚本而非 inline script，避免放宽 CSP。
- `server/routes/onboarding.py` 需要把 `/theme-init.js` 加入根静态白名单，确保生产容器能直接服务该文件。

### CSS 与视觉
- 主题变量改为：
  - `:root` 默认深色变量。
  - `:root[data-theme="dark"]` 明确深色。
  - `:root[data-theme="light"]` 浅色变量。
- `body.light` 可短期保留为兼容兜底，但新代码不再写它。
- `:root` 设置 `color-scheme: dark`，浅色主题设置 `color-scheme: light`。
- 使用现有色板，避免把本次扩大成全新视觉系统；只修正深浅模式状态来源和浏览器原生主题。

### 顶栏控件
- `TopBar` 接收：
  - `themeMode`
  - `resolvedTheme`
  - `setThemeMode`
- 当前单个图标按钮替换为三态分段控件：
  - 中文：`系统` / `浅色` / `深色`
  - 英文：`System` / `Light` / `Dark`
- 每个按钮带 `aria-pressed` 和明确 `aria-label`；选中态沿用现有 `.seg .on` 风格。
- 移动端控件可以换行，不能造成 `document.documentElement.scrollWidth > window.innerWidth + 1`。

### HTML head 与 manifest
- `frontend/index.html` 保留默认深色 `<meta name="theme-color" content="#0b0b0c">`。
- 初始化脚本和 React 状态变化负责运行时更新 `theme-color`：
  - 深色：`#0b0b0c`
  - 浅色：`#f6f7f8`
- `manifest.json` 暂不动态化，继续作为默认安装色，与静态默认 meta 深色值 `#0b0b0c` 保持一致。
- 根 `AGENTS.md` 现有约定“manifest `theme_color` 必须与 `<meta name="theme-color">` 一致”需要收窄为：manifest 与静态默认 meta 一致；页面运行时可按实际主题更新 meta，manifest 仍是安装/默认色。

### ADR 与项目约定
- ADR-0019 已 accepted，且写明前端不得使用 `localStorage/sessionStorage` 等浏览器本地存储；本次主题偏好例外会修订该约束，不能只改 spec 或 AGENTS。
- 实现时 MUST 新增 `docs/adr/0023-theme-preference-localstorage-exception.md`，记录：
  - 背景：三态主题需要刷新后保留显式选择，且当前无用户账号/服务端偏好模型。
  - 决策：允许唯一 localStorage key 保存 `system | light | dark` 主题模式；其它前端状态仍禁止持久化；`/admin` sessionStorage 例外不变。
  - 后果：主题体验符合常见产品做法，但未来新增任何前端持久化都必须重新走独立 ADR/spec。
- 同步更新 `docs/adr/README.md` 列表、根 `AGENTS.md` 与 `docs/architecture/module-map.md` 的本地存储约束表述。

### 测试门槛判断
- 本变更包含可测逻辑：主题枚举解析、持久化读写容错、系统偏好解析。因此必须新增单元测试。
- 当前前端已有 `node:test` 风格的 TS 测试文件，但没有统一 npm 测试入口；实现时 MUST 增加轻量、无运行期依赖的前端单测命令，优先用 `tsc` 编译到临时目录后 `node --test` 执行，覆盖新增 theme 测试并保留既有 timeFormat 测试可运行。
- CSS/布局为展示变更，不额外强制单元测试；必须做浏览器视口验证。
- 若实现中 `styles.css` diff 超过 200 行，仍属于纯展示/CSS 变更，记录豁免，靠 AI 视口验证覆盖。

## AI 验证流程
- 单元测试：
  - `npm --prefix frontend run test:unit`。
  - `theme.ts` 非法/缺失存储值回退 `system`。
  - storage 读取/写入抛错不影响应用。
  - `system` 随 `prefersDark` 解析，`light/dark` 不受系统偏好影响。
- 构建：
  - `npm --prefix frontend run build`
  - `python -m py_compile server/*.py server/routes/*.py`
- 服务端路由：
  - 若新增根静态白名单，TestClient 验证 `GET` / `HEAD` `/theme-init.js` 返回 200 且 content-type 为 JavaScript。
- 浏览器验证：
  - 启动本地服务，打开 `/` 与 `/skills`。
  - 视口：1440x900、768x1024、375x812。
  - 切换 `system/light/dark`，刷新后显式模式保留；切回 `system` 后跟随系统偏好。
  - 检查 `document.documentElement.dataset.theme`、`document.documentElement.style.colorScheme`、`meta[name=theme-color]` 与 UI 状态一致。
  - 检查 `manifest.json` 的 `theme_color` 与静态默认 meta 仍为 `#0b0b0c`，浅色运行时只更新当前文档 meta。
  - 手机检查页面根无横向滚动。

## 权衡
- **使用 localStorage 而非 cookie/server profile**：当前看板无用户登录态，主题偏好是纯浏览器偏好；localStorage 是最小实现。代价是需要给项目“禁止本地存储”规则增加明确窄例外。
- **外部同源初始化脚本而非 inline script**：能避免首屏闪烁，同时不放宽 CSP。代价是服务端根静态白名单要增加一个文件。
- **三态分段控件而非单按钮循环**：状态更清楚，符合系统/显式主题的常见产品模式。代价是顶栏占用更多宽度，需要移动端换行处理。
- **不重做色板**：本次目标是主题机制标准化，不扩大到品牌视觉重设。

## 风险
- 用户已有浅色习惯但之前不可持久化，首次上线默认会跟随系统；显式选择后才持久化。
- 某些隐私模式会禁用 localStorage；读取/写入容错后仍可使用 `system` 默认，不阻塞应用。
- 根静态文件白名单漏配会导致生产环境初始化脚本 404；用 TestClient 覆盖。
- 如果漏写 ADR，后续协作者会看到 ADR-0019 与实现冲突；用新增 ADR-0023 和 README 列表更新收口。
- 如果不更新 head/manifest 约定，后续会误以为运行时浅色 meta 必须同步改 manifest；通过 AGENTS 与设计说明明确“静态默认一致、运行时 meta 覆盖”的边界。
- 回滚方式：revert 本 change；默认深色 CSS 变量仍可工作。
