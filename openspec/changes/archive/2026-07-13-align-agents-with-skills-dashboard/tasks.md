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
- [x] 在 1440×900、768×1024、375×812 验证 `/agents`，覆盖 today/7d/30d、中/英、浅/深主题，并逐项对照 Skills chart 的宽度、柱宽、轴、今日标记、tooltip 与内部滚动。
- [x] 验证 Agents 根 `scrollWidth <= innerWidth`，长图只在图表容器内滚动。
- [x] 验证键盘焦点顺序、问题筛选、排行筛选与 Agent 整卡下钻。
- [x] 打开 `/skills?w=7d` 做只读回归截图，确认本 change 没有修改 Skills 结构、样式或行为。
- [x] 对照本 change 逐条复核实现与视觉结果。
