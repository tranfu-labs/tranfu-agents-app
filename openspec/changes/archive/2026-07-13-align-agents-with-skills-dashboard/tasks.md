# 任务：align-agents-with-skills-dashboard

## 方案与事实源

- [x] 实际检查 `/agents` 的 1440px/375px 渲染，并以现有 `/skills` 作为只读参照。
- [x] 采访确认只优化 Agents；Skills 统计必须保持不变；停在 `plan-written` 审阅线框。
- [x] 输出 Agents 桌面、平板、手机字符线框与测试方案。
- [x] 写入 Agents-only proposal、design、board spec delta 和任务清单。

## 实现

- [x] 将 Agents 控制区标题改成 Skills 同层级的“控制条 + 当前视角说明”，手机保留折叠摘要。
- [x] 删除独立 Agents 摘要 frame，将窗口变化与稳定事实合并为 Skills 同款八卡网格，桌面 8×1、平板 4×2、手机 2×4。
- [x] 为八卡补齐真实入口：趋势/排行/Agent 明细锚点与现有 URL 筛选；入口可键盘访问且不清掉无关筛选。
- [x] 让 Agents chart 消费 `resolveSkillsChartLayout`，实现同等级的短窗铺满、长窗内滚、今日斜纹、整日命中区、自定义 tooltip、pointer/键盘交互和全零 Empty。
- [x] 为 `today` 实现紧凑单日 plot，不伪造小时序列，并保持桌面排行/趋势外框底边对齐。
- [x] 将 Agents 排行/趋势改成近等宽 split、同构 `//标题 + cnt` header，并补排行居中 Empty；同步优化排行行与 Agent 卡片的层级和密度。
- [x] 调整 Agents 平板/手机内容顺序和组件内滚动边界；手机按媒体查询重排真实 DOM，使问题线索后先展示 Agent 明细，再下沉八卡与分析区，不只依赖 CSS `order`。
- [x] 补齐 Agents 新增中英文展示文案；不改 Skills 专用文案。
- [x] 若任一 TypeScript 单文件实际 diff 超过 200 行，先拆分纯函数或展示组件再继续。

## 测试与 AI 验证

- [x] 扩展 Agents 单测：八卡值/detail/delta/入口动作模型、today/全零/短窗/长窗布局、tooltip/roving-focus 模型、响应式 section 顺序、窗口变化、问题信号。
- [x] 运行 `npm --prefix frontend run test:unit`。
- [x] 运行 `npm --prefix frontend run build`。
- [x] 在可用桌面视口验证 `/agents` 的 today/90d 标题、趋势定位、指标切换和内部滚动；平板/手机断点由响应式单测与媒体查询审查覆盖，浏览器视口覆盖限制记录在 `verification.md`。
- [x] 验证 Agents 根 `scrollWidth <= innerWidth`，长图只在图表容器内滚动。
- [x] 用纯函数单测验证 roving focus、问题/排行入口 URL 与手机真实 DOM 顺序，并在浏览器验证趋势指标切换后的唯一焦点日期。
- [x] 打开 `/skills?w=7d` 做只读 DOM 回归，确认 8 张变化卡、核心区块、根宽度和运行日志未受影响。
- [x] 对照本 change 逐条复核实现与视觉结果。

## 实现复核修复

- [x] 将 KPI frame 标题改为与 Skills 同源的动态窗口变化标题，并隔离所有 Agents 对 `.skills-*` 展示 class 的依赖。
- [x] 长窗口初始定位最后一个非零日期；窗口/指标变化时同步重置 roving focus、tooltip 与滚动位置。
- [x] custom/current/previous 窗口仅在日序列完整覆盖时标记可用。
- [x] 补窗口标题、完整覆盖、初始焦点和滚动位置纯函数测试；把前端单测加入 CI。
- [x] 重新运行前端单测、build、后端测试和浏览器验证，并把可复核结果写入 `verification.md`。

## CI 返修

- [x] 固定 browser-local 时间格式测试的夹具时区，消除 GitHub Runner UTC 与开发机 Asia/Shanghai 的环境差异。
- [ ] 在 UTC 外部环境重跑前端单测，并确认 PR #113 远端 CI 通过。
