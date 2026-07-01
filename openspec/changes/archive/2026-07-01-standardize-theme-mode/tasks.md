# 任务：standardize-theme-mode

- [x] 1. 新增主题状态模块、测试入口与单元测试。
      实现 `ThemeMode` / `ResolvedTheme`、存储读写容错、系统偏好解析、DOM/meta 应用函数；增加 `npm --prefix frontend run test:unit` 入口，并覆盖合法/非法/异常 storage 场景。
- [x] 2. 加入首屏主题初始化脚本。
      在 `frontend/public/theme-init.js` 读取主题偏好并设置 root data attributes / `color-scheme` / `theme-color`；在 `frontend/index.html` app module 前加载。
- [x] 3. 更新 App 与顶栏主题交互。
      `App.tsx` 改为三态主题状态和 `matchMedia` 监听；`TopBar.tsx` 把单按钮改为三态分段控件并补中英文文案。
- [x] 4. 标准化 CSS 主题来源。
      将浅色变量迁移到 `:root[data-theme="light"]`，添加 `color-scheme`，修正移动端顶栏分段控件不溢出。
- [x] 5. 放行生产根静态脚本。
      更新 `server/routes/onboarding.py` 根静态白名单，补 `/theme-init.js` 的 GET/HEAD 路由测试。
- [x] 6. 更新规格、线框与项目约定。
      新增 ADR-0023 并更新 ADR README；确认 board/onboarding spec delta 和 `/`、`/skills` 顶部导航线框覆盖本次变化；更新 AGENTS/module-map 中“前端本地存储”约束的主题偏好窄例外，并收窄 head/manifest `theme_color` 约定为“静态默认一致、运行时 meta 可按主题覆盖”。
- [x] 7. 自检与视口验证。
      运行前端单测、前端构建、服务端 py_compile、相关 pytest；用 1440x900/768x1024/375x812 检查 `/` 与 `/skills` 的 system/light/dark 行为、刷新持久化、theme-color 和横向滚动。
