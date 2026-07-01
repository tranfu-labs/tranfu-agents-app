# ADR-0023 Theme preference localStorage exception

- 状态:Proposed
- 关联:ADR-0019、specs/board、openspec/changes/archive/2026-07-01-standardize-theme-mode

## 背景
ADR-0019 要求 React 看板不得使用 `localStorage/sessionStorage` 等浏览器本地存储,避免把业务状态、筛选条件或敏感内容落到浏览器。

深浅主题优化需要采用常见三态模式:`system` / `light` / `dark`。其中显式选择 `light` 或 `dark` 后,用户期望刷新页面仍保留该偏好;当前项目没有账号体系、服务端用户 profile 或其它偏好存储模型,把主题偏好送到服务端会扩大数据边界。

## 决策
允许看板前端使用唯一 localStorage key 保存主题模式偏好:

- key 固定为 `tf-theme-mode`。
- value 只能是 `system` / `light` / `dark`。
- 读取或写入失败必须静默回退,不得阻塞看板渲染。
- 不得存储语言、筛选条件、业务数据、身份数据、上报内容、prompt、代码、输出或任何其它前端状态。
- `/admin` 管理钥匙继续只允许使用本会话 `sessionStorage`,本 ADR 不改变管理钥匙边界。

`manifest.json` 的 `theme_color` 继续表示静态默认安装色,并与静态默认 `<meta name="theme-color">` 保持一致。页面运行时可以根据当前主题更新当前文档的 `theme-color` meta,不要求动态改写 manifest。

## 后果
- ✅ 显式主题选择能跨刷新保留,符合常见产品体验。
- ✅ 不需要引入账号体系、服务端偏好 API 或 cookie。
- ✅ 本地存储例外被限制在单一无敏感含义的枚举值。
- ⚠️ 后续任何新增前端持久化都不能复用这个例外,必须另走 ADR 与 spec。
- ⚠️ 隐私/无痕环境可能禁用 localStorage;前端必须把它当 best-effort 能力。
