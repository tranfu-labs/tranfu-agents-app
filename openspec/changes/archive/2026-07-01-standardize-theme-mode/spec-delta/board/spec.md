# spec-delta：board

## 修改

### 前端主题模式
看板前端 MUST 提供三态主题模式：`system`、`light`、`dark`。

- `system` MUST 是默认模式，并按浏览器 `prefers-color-scheme` 解析为实际浅/深主题。
- 当处于 `system` 模式时，系统深浅偏好变化 MUST 在不刷新页面的情况下更新实际主题。
- `light` / `dark` MUST 作为显式模式，不受系统偏好变化影响。
- 顶部导航 MUST 提供可键盘操作的三态主题控件，当前模式必须有明确选中态。
- 前端 MUST 在 root 元素上反映当前模式与实际主题，例如 `data-theme-mode` 与 `data-theme`；CSS 主题变量 MUST 以 root 实际主题为准，不再依赖 React effect 后才写入 `body.light`。
- 前端 MUST 设置 `color-scheme`，使表单控件、滚动条等浏览器原生 UI 跟随实际主题。
- 前端 MUST 在主题变化时同步 `<meta name="theme-color">`，深色使用 `#0b0b0c`，浅色使用 `#f6f7f8`。
- `manifest.json` 的 `theme_color` MUST 与静态默认 `<meta name="theme-color">` 保持一致；页面运行时 MAY 按实际主题更新当前文档 meta，不要求动态改写 manifest。

### 前端本地存储例外
除 `/admin` 管理钥匙的 `sessionStorage` 例外外，前端 MAY 使用 `localStorage` 保存唯一主题偏好 key，且只能保存 `system | light | dark`。

该例外 MUST NOT 被扩展为保存语言、筛选条件、业务数据、身份数据、上报内容或任意其它前端状态。读取或写入失败时 MUST 静默回退，不得阻塞看板渲染。

## 新增可验证行为
- 首次打开看板且无主题偏好时，实际主题跟随浏览器 `prefers-color-scheme`。
- 选择 `light` 后刷新页面，页面在 React 应用启动前即呈现浅色主题，`data-theme="light"`、`color-scheme: light` 与 `theme-color=#f6f7f8` 一致。
- 选择 `dark` 后刷新页面，页面在 React 应用启动前即呈现深色主题，`data-theme="dark"`、`color-scheme: dark` 与 `theme-color=#0b0b0c` 一致。
- 选择 `system` 后，浏览器系统偏好从深色切到浅色时，看板无需刷新即可更新为浅色；从浅色切到深色亦然。
- localStorage 不可用或存储值非法时，看板仍能渲染，并回退为 `system`。
- `manifest.json.theme_color` 与静态默认 meta 均为 `#0b0b0c`；浅色运行时只更新当前文档 meta 为 `#f6f7f8`。
- 375x812 打开 `/` 与 `/skills`，顶部三态主题控件可见且不造成页面根横向滚动。
