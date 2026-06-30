# 设计:localize-tranfu-favicon

## 方案

### 1. 对齐 tranfu.com 当前 favicon 链路
`https://tranfu.com/` 当前 head 中与 favicon 相关的声明为:

```html
<link rel="shortcut icon" href="https://tranfu.com/favicon-20260626.ico" type="image/x-icon" />
<link rel="icon" href="https://tranfu.com/favicon-20260626.ico" sizes="any" />
<link rel="icon" href="https://tranfu.com/favicon-32x32-20260530.png" sizes="32x32" type="image/png" />
<link rel="icon" href="https://tranfu.com/favicon-16x16-20260530.png" sizes="16x16" type="image/png" />
<link rel="apple-touch-icon" href="https://tranfu.com/apple-touch-icon-20260530.png" sizes="180x180" />
<link rel="manifest" href="https://tranfu.com/manifest.json" />
```

本项目不直接引用主站域名,而是保留同样的文件名并换成同源根绝对路径:

```html
<link rel="shortcut icon" href="/favicon-20260626.ico" type="image/x-icon" />
<link rel="icon" href="/favicon-20260626.ico" sizes="any" />
<link rel="icon" href="/favicon-32x32-20260530.png" sizes="32x32" type="image/png" />
<link rel="icon" href="/favicon-16x16-20260530.png" sizes="16x16" type="image/png" />
<link rel="apple-touch-icon" href="/apple-touch-icon-20260530.png" sizes="180x180" />
<link rel="manifest" href="/manifest.json" />
```

移除当前的 `favicon.svg` 声明,避免现代浏览器优先选 SVG 而不是主站同款 ICO/PNG 链路。

### 2. public 资源
`frontend/public/` 新增版本化文件名。当前仓库内 unversioned 文件内容已经与主站版本化资源 hash 一致,
实现时可以从主站下载覆盖,也可以从现有本地文件复制成版本化别名;验收以 MD5/尺寸为准。

需要存在:
- `favicon-20260626.ico`(32x32 ICO,MD5 `feb9453864b47ec44b340e0264cfe111`)
- `favicon-32x32-20260530.png`(32x32 PNG,MD5 `78ec95d63a884d41f2e7e5620a0dc98c`)
- `favicon-16x16-20260530.png`(16x16 PNG,MD5 `20a7c35ad99d06a89cff81155cd154ad`)
- `apple-touch-icon-20260530.png`(180x180 PNG,MD5 `982092952146574e3554ddc97fd4b017`)
- `android-chrome-192x192-20260530.png`(192x192 PNG,MD5 `14b728cc6c8fdcceeffb39856e42f669`)
- `android-chrome-512x512-20260530.png`(512x512 PNG,MD5 `f8c640a9385b0b8755596dd0573d5ad2`)

保留现有 unversioned 文件,避免旧缓存或外部引用突然 404。

### 3. manifest
`frontend/public/manifest.json` 继续保留 TRANFU//AGENTS 自己的:
- `name` / `short_name`
- description
- theme/background color(`theme_color` 必须与 `frontend/index.html` 的 `theme-color` 一致)
- start/scope 语义

只将 `icons[].src` 改为版本化本地路径:
- `/apple-touch-icon-20260530.png`
- `/android-chrome-192x192-20260530.png`
- `/android-chrome-512x512-20260530.png`

### 4. FastAPI 根静态路由
生产环境不是 Vite dev server,`server/routes/onboarding.py` 只显式直出白名单根静态文件。
新增版本化文件后必须:
- 加入 `_ROOT_STATIC_FILES`
- 提供 GET/HEAD 路由
- 复用 `_frontend_root_static()` 与 `_MEDIA` MIME 映射

### 5. 测试与验证
- 扩展 `tests/test_onboarding.py::test_frontend_root_static_assets_support_get_and_head`,覆盖版本化
  ICO/PNG 的 GET/HEAD 与 MIME。
- 跑 `python -m py_compile server/*.py server/routes/*.py`。
- 跑目标 pytest:`python -m pytest tests/test_onboarding.py`。
- 跑 `npm --prefix frontend run build`,检查构建后的 HTML head 引用为本地根绝对路径。

## 权衡
- **采用版本化文件名,保留 unversioned 旧文件**:版本化路径能绕开 favicon 的强缓存,同时 unversioned 文件继续兼容旧路径。
- **不复制 tranfu.com manifest 文案**:主站 manifest 的 name/description 属于主站,本项目仍应展示 TRANFU//AGENTS。
- **不继续声明 SVG favicon**:SVG 可缩放但会改变浏览器选择结果,与"和 tranfu.com 一样的 ico 效果"冲突。

## 风险
- 新版本化根静态文件若忘记加 FastAPI 路由,生产环境会 404;用 onboarding 测试兜住。
- 浏览器 favicon 缓存顽固;版本化文件名降低缓存风险,但用户本地旧标签页可能仍需刷新或清缓存。
- 回滚:恢复 head/manifest/路由,删除版本化文件即可;不影响数据和 API。
