# 任务：operator-detail-windowed-analysis

## 方案与事实源

- [x] 采访确认操作员详情继承 `w/rt/src`，单日使用构成环形图，多日保留趋势，完整 Skill 清单下沉到同页。
- [x] 写入 proposal、design、board spec delta、操作员详情三断点字符线框和 SKILLS 页面流转增量。
- [x] 自审统计口径、返回上下文、空范围、可访问性、响应式和测试边界。

## 实现

- [x] 新增操作员详情 query 纯模块：统计参数白名单、API query、来源 query 编码/校验、最小返回地址。
- [x] 扩展 `operator_detail_payload` 与 `/api/operator/{name}`，复用 Skills 窗口和 runtime/source 规则；现有顶层兼容字段保持原语义，新增 `window/applied_filters/analysis` 承载统一窗口范围。
- [x] 补齐服务端 API 测试：无参数旧契约逐项兼容、today、custom、rt+src 交集、上期、used-only、空范围 200、未知操作员 404、非法窗口。
- [x] 新增单日构成与紧凑排行纯模型，并补 Top 5/8、其他、占比守恒、单日/多日/空态单测。
- [x] 重构 `/skills` → `/operator/:name` 下钻和显式返回，只让统计参数影响详情，并恢复来源页完整视角/筛选。
- [x] 重构 OperatorDetail：只消费 `analysis` 渲染窗口标题/筛选 chip/窗口 KPI/自适应图表/带来源的紧凑排行/runtime/完整 Skill 明细/最近记录。
- [x] 补齐中英文文案、system/light/dark 样式和桌面/平板/手机响应式；保证根级无横滚。

## 验证命令

- [x] `python -m py_compile server/*.py server/routes/*.py`
- [x] `pytest tests/test_board.py tests/test_skills_stats_page.py`
- [x] `python -m coverage run -m pytest && python -m coverage report --include='server/**/*.py'`，整体行覆盖率 ≥95%。
- [x] `npm --prefix frontend run test:unit`
- [x] `npm --prefix frontend run build`
- [x] 浏览器走查 today/7d/30d/custom、rt/src、空态、返回恢复、Skill 下钻、中英文、三态主题和 1440/768/375 视口。

## 可核查验收清单

- [x] A1. 从按人总览的 `w=today` 行进入后，详情标题明确显示“今天/Today”，API 请求带 `w=today`。
- [x] A2. `rt/src` 同时存在时，摘要、图、排行、runtime、完整清单和最近记录均取交集。
- [x] A3. `q/topn/hz/sel/sort/dir/scope` 不进入详情 API；显式返回仍恢复来源 `/skills?view=operator...` 状态。
- [x] A4. `w=custom` 保留完整 `wstart/wend`；刷新、复制链接和前进后退后统计范围不变。
- [x] A5. 单统计日有数据时显示 Top 5 + 其他环形图和紧凑 Top 5；紧凑排行每条真实 Skill 行显示来源，不显示单根趋势柱。
- [x] A6. 多统计日显示 Top 8 + 其他日趋势和紧凑 Top 8；紧凑排行每条真实 Skill 行显示来源，30/90 天只在图表盒内滚动。
- [x] A7. 完整 Skill 明细列出当前范围全部 Skill，不受 Top 5/8 限制，并支持鼠标、Enter、Space 下钻。
- [x] A8. 页面所有数字只统计 `mode=used`，可见口径明确为会话×Skill 使用记录而非真实调用次数。
- [x] A9. 当前范围为空返回 200 零值空态；全局无 used 记录的未知操作员才返回 404。
- [x] A10. 直接访问无 `from` 的详情时，返回入口至少保留 `view=operator` 与当前 `w/wstart/wend/rt/src`。
- [x] A11. 最近记录仍最多 50 条、不可点，具体时刻与 date-only fallback 沿用既有本地时区规则。
- [x] A12. 1440/768/375 三档、中文/英文和 system/light/dark 下无根级横滚、文字/数值重叠或不可达交互。
- [x] A13. 服务端编译、相关 pytest、≥95% coverage、前端单测和生产构建全部通过后，才可声明 `验证通过(code-verified)`。

## A1–A13 实施阶段证据映射

下列是实施后必须产出的证据位置与断言，不代表方案阶段已经通过。

| 验收项 | 自动化测试证据 | 浏览器/人工证据 |
|---|---|---|
| A1 | `frontend/src/lib/operatorDetailQuery.test.ts`：`today` 下钻/API query；`tests/test_skills_stats_page.py::test_operator_detail_today_window_and_runtime_source_intersection_apply_to_all_blocks`：`window.key=today` 且 `analysis` 只有今天 | 1440px 从 `/skills?view=operator&w=today` 下钻，截图标题“今天/Today”及 Network query |
| A2 | `tests/test_skills_stats_page.py::test_operator_detail_today_window_and_runtime_source_intersection_apply_to_all_blocks`：逐项断言 `analysis.metrics/daily/skills/runtime/records` 只有 `codex + own`；顶层兼容字段不参与页面 | 以 `[Codex] [own]` 打开详情，核对摘要、图、排行、Runtime、完整明细、最近记录；线框示例所有可见数据也只使用该交集 |
| A3 | query 纯模块单测断言 `q/topn/hz/sel/sort/dir/scope` 不进统计/API query，但能在受限 `from` 中往返；拒绝任意 path/origin | 下钻后查看地址与 Network；点返回恢复原 `/skills?view=operator...` 全部合法 query |
| A4 | query 纯模块单测覆盖完整 custom、半填写拒绝请求和逆序拒绝；`test_operator_detail_custom_window_empty_scope_and_invalid_window` 锁定 Unix 秒按上海日转换 | custom 选择后刷新、复制新标签、前进/后退，标题和数据范围保持一致 |
| A5 | `frontend/src/lib/operatorDetailAnalysis.test.ts`：一天窗口 Top 5 + 其他、占比/数量守恒、每条真实排行行保留 `source`、模式为 donut | today 与一天 custom 各截图：环形 + 带来源紧凑 Top 5，无单柱趋势 |
| A6 | 同一纯模型测试：多日 Top 8 + 其他、来源保留、两天 custom 判为 trend；图表布局单测覆盖长窗 `scroll` | 7d/14d/30d/90d/custom 截图；30/90d 检查只有 `.chart-box` 横滚且默认最新日 |
| A7 | `operatorDetailAnalysis.test.ts` 以 14 个 Skill 断言紧凑榜 8 行而 `all` 保留 14 行；`operatorDetailQuery.test.ts` 锁定 Enter/Space 激活规则 | 实际 DOM 核对紧凑 8 行/完整 14 行，并从完整明细键盘下钻；返回后范围不丢 |
| A8 | rt/src 交集测试混入 equipped，断言 `analysis` 全部 used-only；既有 ingest 幂等测试继续守住会话×Skill×mode 唯一性 | 中英文页面核对“会话×Skill 去重使用记录，不是真实调用次数”口径 |
| A9 | `test_operator_detail_custom_window_empty_scope_and_invalid_window` 断言范围空为 200 零值；`test_operator_detail_unknown_or_equipped_only_404` 断言全局无 used 为 404 | 逐一截图范围空态、404，并核对二者文案不同 |
| A10 | query 纯模块单测：无 `from` 时返回 `/skills?view=operator&w/.../rt/src` 最小地址 | 直接粘贴详情深链并点击返回，落回同一按人观察范围 |
| A11 | `test_operator_detail_recent_records_are_limited_to_50` 断言兼容记录和 `analysis.records` 最多 50；既有 `timeFormat.test.ts` 覆盖 instant/date-only | 浏览器本地时区核对相对时间与 title，DOM 确认记录行无 link/tabIndex |
| A12 | 既有 `theme.test.ts` 覆盖 system/light/dark，生产构建守住类型/CSS；服务端与浏览器分别覆盖 empty/404，浏览器 accessibility tree/键盘走查记录在验证日志 | system/light/dark 与 1440/768/375 组合抽查；检查 `document.documentElement.scrollWidth === clientWidth`、无重叠、焦点可达 |
| A13 | 保存 `py_compile`、定向 pytest、全量 coverage ≥95%、`test:unit`、生产 build 的退出码与摘要 | 汇总 A1–A12 截图/Network/DOM 证据；全部通过后才标记 `code-verified` |

### 无参数兼容测试（必须落地）

`tests/test_skills_stats_page.py::test_operator_detail_no_query_preserves_legacy_contract` 使用固定统计日，造 31 天前、5 天前和今天的多 runtime/source used 记录，然后：

1. 无参数请求逐项断言顶层 `metrics` 的 7d/30d/累计与全局首末日、顶层 `daily` 含 31 天前记录、顶层 `skills` 仍按 30d/累计排序、顶层 `runtime` 为全历史、顶层 `records` 仍取全历史最近 50 条。
2. 同一响应断言新增 `window.key=7d`，且 `analysis` 排除 31 天前记录。
3. 再请求 `w=today&rt=codex&src=own`，断言顶层五组兼容字段与无参数响应逐项相等，只有 `window/applied_filters/analysis` 收窄。

## 实施验证记录（2026-07-23）

- A1：从 `/skills?view=operator&w=today&rt=codex&src=own&q=alice&topn=20&hz=1` 实际下钻后，地址仅以 `w=today&rt=codex&src=own` 作为统计范围，标题为 `alice · 今天`。
- A2：浏览器和 `test_operator_detail_today_window_and_runtime_source_intersection_apply_to_all_blocks` 均核对 `codex + own` 交集；样例摘要为 28 条记录、7 个 Skill、1 个 runtime，图、排行、完整清单和记录均无交集外数据。
- A3：`operatorDetailQuery.test.ts` 锁定统计白名单与安全 `from`；实际下钻地址中的 `q/topn/hz` 仅存在于编码后的 `from`，显式返回恢复原按人总览 query。
- A4：浏览器以 `w=custom&wstart=1784736000&wend=1784822399&rt=codex&src=own` 刷新，URL 与 `alice · 自定义周期` 标题保持不变；纯模块覆盖半填写与逆序拒绝。
- A5：375/1440 视口实际核对 today 为 Top 5 + 其他环形图、紧凑 Top 5、完整清单 7 行；纯模型断言数量与占比守恒。返工补充单 Skill 边界：共享路径测试断言完整环带外缘与内缘各由两段 arc 构成，`OperatorSkillDonut` 静态组件测试断言单 Skill 环、`100%` 图例和可访问标题均实际输出。二次返工补充历史单日 custom：组件测试锁定中文 `Skill 使用构成 · 自定义周期`、英文 `Skill usage composition · Custom range`，并排除旧的“今日/Today”固定文案；真实浏览器以 `2026-06-12` 单日窗口核对可见标题与 SVG 可访问名称一致，中文/英文均通过且页面根无横滚。
- A6：30d 实际核对趋势、紧凑 Top 8、完整清单 14 行；图盒 `clientWidth=771`、`scrollWidth=926`、默认 `scrollLeft=155`，页面根无横滚。纯模型覆盖 7/14/30/90d 与两日 custom，既有图表布局单测覆盖长窗滚动。
- A7：完整行实际用 Enter 下钻并返回；行本身有 click handler，`isOperatorDetailActivationKey` 单测锁定 Enter/Space，其他按键不激活。
- A8：API fixture 混入 equipped 后仍只返回 used；中英文页面均显示“会话 × Skill 去重使用记录，不是真实调用次数”的口径。
- A9：`alice?w=today&rt=hermes` 返回 200 零值空态；`ghost?w=today` 呈现独立 404 文案，服务端测试同时覆盖 equipped-only 404。
- A10：无 `from` 的 30d 深链返回地址为 `/skills?w=30d&rt=codex&view=operator`；query 单测覆盖 custom/rt/src 的最小返回地址。
- A11：API 测试断言兼容记录与 `analysis.records` 均最多 50；浏览器 DOM 中最近记录无 link/tabIndex，时间文案继续消费既有 `formatRecentRecordTime`。
- A12：实测根宽分别为 `1440=1440`、`768=768`、`375=375`；桌面双列、平板/手机单列，中文/英文与系统解析浅色/显式深色均已截图核对。主题纯模块单测覆盖 system/light/dark 三态。
- A13：`py_compile` 通过；定向 54 tests passed；全量 406 tests passed；服务端总覆盖率 96%；前端二次返工后 87 tests passed；生产构建通过。全量 ESLint 仍有仓库既有 10 errors/1 warning，本次新增及返工文件定向 ESLint 为 0。

说明：本机 pytest 自动加载的第三方插件会使标准命令被系统以 137 终止；验证使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 隔离本机插件，测试集合未变。
