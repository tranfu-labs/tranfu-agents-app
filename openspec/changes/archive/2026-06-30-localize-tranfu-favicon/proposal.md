# 变更提案:localize-tranfu-favicon(本地化 tranfu.com favicon 链路)

- 状态:Proposed
- 关联:网站 head 图标 / frontend public assets / onboarding root static

## 背景 / 问题
当前 TRANFU//AGENTS 的 head 使用部署域名下的 favicon 资源,并同时声明了 `favicon.svg`、
`favicon-32x32.png`、`favicon-16x16.png` 等多个 `rel="icon"`。浏览器可能优先选择 SVG 或缓存旧的
unversioned 文件,导致浏览器标签页图标与 `https://tranfu.com/` 主站实际显示效果不一致。

用户明确要求不要取页面展示区里的素材,而是参考 `https://tranfu.com/` 自己显示自己的 favicon 效果:
本地化主站当前 head 中使用的版本化 favicon 链路,并用本地域名根绝对路径引用。

## 提案
- 将 `tranfu.com` 当前 favicon 链路使用的版本化文件名落到 `frontend/public/`:
  `favicon-20260626.ico`、`favicon-32x32-20260530.png`、`favicon-16x16-20260530.png`、
  `apple-touch-icon-20260530.png`、`android-chrome-192x192-20260530.png`、
  `android-chrome-512x512-20260530.png`。
- 更新 `frontend/index.html` 的 favicon / apple-touch / manifest 链接,使用同源根绝对路径:
  `/favicon-20260626.ico` 等,并移除 SVG favicon 声明避免抢优先级。
- 更新 `frontend/public/manifest.json`,保留 TRANFU//AGENTS 自己的应用文案与主题色,只把 icons 改为版本化本地路径。
- 更新 `server/routes/onboarding.py`,让这些版本化根静态文件在生产 FastAPI 中可 GET/HEAD。
- 增加 onboarding 静态资源测试,覆盖版本化 favicon 文件的 MIME 与 HEAD 行为。

## 非目标
- 不改页面内容、导航、React 组件布局或业务数据接口。
- 不直接引用 `https://tranfu.com/...` 远端资源;远端只作为素材来源与效果基准。
- 不改 OG/Twitter 分享大图内容,仍使用 TRANFU//AGENTS 自己的 `og-image-1200x630.png`。

## 影响
- 影响 M2 看板前端 head 与 public 静态资源。
- 影响 M1 onboarding 根静态文件白名单与路由。
- 影响 specs/board 与 specs/onboarding 的事实源描述。
