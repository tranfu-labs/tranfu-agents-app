# 验证：align-agents-with-skills-dashboard 实现复核修复

验证日期：2026-07-13（Asia/Shanghai）

## 自动验证

- `npm --prefix frontend run test:unit`：通过，61/61。
- `npm --prefix frontend run build`：通过，Vite 生产构建成功。
- `python -m pytest tests/ -q`：通过，345/345。
- `git diff --check`：通过。
- Agents 源码静态检查：`frontend/src/components/agents/` 与 `frontend/src/views/Agents.tsx` 不再出现 `skills-*` className。
- ESLint 复核：本轮修改文件没有新增错误；仓库仍有 5 个既有错误，位于 `App.tsx`、`RankBars.tsx` 和 `lib/api.ts`，未扩展本 change 范围修复。

新增测试覆盖：

- `today`、预设窗口和自定义窗口标题从 Skills 同源窗口 label 派生。
- 当前/上一窗口必须被 `agent_overview.days` 完整覆盖；缺日时变化值、排行和趋势不展示不完整聚合。
- 长窗口按当前指标寻找最后一个非零日期，并计算容器内居中的初始滚动位置；全零回退窗口末日。
- 既有 roving focus、八卡入口模型和手机真实 DOM 顺序继续通过。

## 浏览器验证

本地 Vite + FastAPI，Codex 内置浏览器默认桌面视口 `1280×720`：

- `/agents?w=today` 标题显示 `//今天变化 · 今天`，不再是固定“时间窗变化”。
- `/agents?w=90d` 标题显示 `//近 90 天变化 · 近 90 天`。
- 90 天数据最后一个非零日为 `2026-06-12`；初始焦点 aria-label 为 `2026-06-12 · 活跃 Agent 1 · 活跃时长 16s`。
- 趋势容器 `scrollLeft=1377`、`max=1975`，焦点命中区位于可视范围内，没有被滚到尾部空白区。
- 切到“活跃时长”后该按钮 `aria-pressed=true`，焦点仍定位 `2026-06-12` 且可见。
- Agents 页面根横向溢出为 `0`，Agents 页面内包含 `skills-*` class 的元素数为 `0`。
- `/skills?w=7d` 保持 8 张 `.skills-kpi-card`，核心标题仍为“近 7 天变化 / 使用排行 / 每日使用 / 明细”，页面根横向溢出为 `0`，控制台 error 为 `0`。

## 验证限制

内置浏览器的 viewport override 在切换到 `768×900` 时未能重新挂载 webview，因此本轮没有把平板/手机截图或浏览器尺寸实测写成已完成事实。`>1080px / 601–1080px / ≤600px` 的 8/4/2 KPI 列数、分析区单列和手机真实 DOM 顺序由 CSS 媒体查询审查与已通过的纯函数单测覆盖；后续人工视觉回归仍可按 `docs/wireframes/pages/agents.md` 补做。

## 结论

本轮确认并修复了复核中发现的动态标题、样式域隔离、长窗口空白尾部、指标/窗口状态重置、窗口完整性和 CI 缺失。未修改 SKILLS 页面组件或业务行为；仅增加了窗口标题共享函数的回归断言。
