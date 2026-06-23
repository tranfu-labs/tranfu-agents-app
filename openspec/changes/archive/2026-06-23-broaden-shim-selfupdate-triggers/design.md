# 设计:broaden-shim-selfupdate-triggers

## 触发面扩展的边界与节流

**问题**:扩了事件 → 自更新调用次数会暴涨吗?

**不会**。`shims/tf_selfupdate.py:28` 的 `CHECK_INTERVAL = 3600` 已经在 `update_once()` 入口做了节流:
读 `~/.tranfu/.selfupdate.json` 的 `last_check`,在 1 小时窗口内直接 return,根本不发 HTTP 请求,也不进入
锁竞争。新加的 `UserPromptSubmit / Stop / SessionEnd` 共享同一份 state 文件,所以**真实拉 manifest 的频率**
仍然是 ≤ 1 次/小时/客户端,只是命中节流的 spawn 数变多——而 spawn 一个 `python3 tf_selfupdate.py` 本身在
节流命中时大概只跑几毫秒就退出,代价可忽略。

**为什么不加 `PreToolUse`**:这是 hook 系统里频率最高的事件(一轮可能几十上百次)。加上后绝大多数 spawn
都会被节流挡掉,**没有任何收益,只增加系统调用**。把触发点收敛在"用户级动作"或"会话级边界"才符合"每个触发都有意义"的设计。

## OpenClaw 接入自更新的选择

**问题**:OpenClaw 是独立 JS 插件,没有 `tf_hook.py` 这条链路。怎么接最小侵入?

**方案**:在 `reporter.mjs` 的 `sessionStart` 里直接 `child_process.spawn('python3', [selfupdatePath], {detached, stdio:'ignore'})` + `.unref()`。

理由:
- **跟 Python shim 同款语义**(`shims/tf_hook.py:_spawn_selfupdate`):detached + 忽略 stdio + 不阻塞当前进程。
- **触发频次匹配**:OpenClaw 长进程已经把 `sessionStart` 当"用户级边界",自更新放这里跟 Python 路径的 `SessionStart` 等价。
- **不需要 PreToolUse 等价物**:OpenClaw 没有"频繁触发的小事件",`sessionStart` 一次足够。
- **依赖注入**:`spawnImpl` 与 `selfupdatePath` 通过 `deps` 传入,方便单测替换。

## 为什么不让 selfupdate 把消息推给当前进程

**问题**:即便触发了自更新,当前进程还是跑旧代码——直到下次新会话才用上新版。要不要 SIGUSR1 / `reloadShimVersion()` 一把热刷?

**仍然不做**(沿用 `self-update-shims` 非目标):
- Python shim 是 short-lived(每次 hook 都新启进程),根本没有"热重载"的需求,下一次 hook 自动用新代码。
- OpenClaw 是 long-lived,但 JS 模块加载语义不支持安全的代码热替换。已有的 `SIGUSR1` 让 `reloadShimVersion()`
  只更新**版本显示**,不会让 reporter 的逻辑变化生效——这本身是设计如此,保持现状。

## 失败模式

| 失败点 | 影响 | 处理 |
|---|---|---|
| `python3` 不在 PATH | spawn 抛错 | catch + 静默 |
| `tf_selfupdate.py` 不存在 | child 立即退出非 0 | 监听 `error` 事件兜底,不打印 |
| 节流窗口内被反复触发 | 进程立即退出 | 接受;1h 内多花几毫秒 spawn 是可接受成本 |
| `TF_AUTO_UPDATE=0` | 函数入口直接 return | 不进入 spawn |
| OpenClaw 运行在 Windows / 无 `child_process` | 整个 spawn 块在 try/catch | 静默 fallback |

## 与 `fix-shim-version-reporting` 的衔接

那个 change 让客户端**每次心跳都带顶层 `shim_version`**;本 change 让客户端**在更多事件上触发更新检查**。
两者合起来形成完整闭环:
- 旧客户端心跳带的版本号被 sticky 表保存;
- 新触发面让那个版本号有机会从 24116eef 自然过渡到 8e0b47a0;
- 看板三态把 outdated 真实呈现给用户,直到它升完为止。

## 测试策略

- **保留现有测试**:`tests/test_hook.py` / `tests/test_openclaw_skill_reporter.mjs` 已跑通 — 证明改动没回归。
- **新增回归测试**(本 change tasks 节列出):
  - Python:`tests/test_hook.py` 加 case,喂 `UserPromptSubmit` / `Stop` / `SessionEnd` 事件,断言 selfupdate 被 spawn。
  - JS:`tests/test_openclaw_skill_reporter.mjs` 注入假 `spawn`,断言 `sessionStart` 触发它,`TF_AUTO_UPDATE=0` 时不触发。
- **AI 验证**:线上 Coolify 部署后,让线上一个长会话 agent 各发一次 prompt,等 1h 节流过期(或现场删 `.selfupdate.json`),
  看 `/api/state` 该 agent 的 `shim_version` 从 24116eef 翻到新 manifest hash。
