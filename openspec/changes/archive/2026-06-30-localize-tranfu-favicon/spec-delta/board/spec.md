# specs/board delta:localize-tranfu-favicon

## 修改:前端 head 图标资源
- 网站 head 中用于浏览器标签页的 favicon 链路 MUST 本地化 `https://tranfu.com/` 当前实际使用的版本化
  favicon 文件名,并使用同源根绝对路径引用,例如 `/favicon-20260626.ico`。
- 浏览器 favicon 声明 MUST 避免直接引用 `https://tranfu.com/...` 远端资源。
- 浏览器 favicon 声明 MUST 不再同时声明 SVG favicon,以免浏览器优先选择 SVG 而偏离主站当前 ICO/PNG 效果。
- PWA `manifest.json` MUST 保留 TRANFU//AGENTS 自己的 name/description/theme 语义;icons 可引用同一组版本化本地资源。

## 可验证行为新增
- 构建后的 `index.html` head 含 `/favicon-20260626.ico`、`/favicon-32x32-20260530.png`、
  `/favicon-16x16-20260530.png` 和 `/apple-touch-icon-20260530.png`,且不含 `rel="icon"` 的 `favicon.svg`。
- `manifest.json` 的 `theme_color` 与 HTML `<meta name="theme-color">` 保持一致。
