# 提案：m3-t9-evidence-completeness

## 背景

`/skills/evidence` 记录页当前只渲染 `/api/skills/evidence` 首批返回的 `records` 或 `items`。服务端接口已有 `limit`/`offset`，且 `limit` 默认 100、上限 500；当同一筛选下实际存在 367 条记录时，前端只展示前 100 条，没有分页、加载更多或等价入口，剩余 267 条在 UI 上不可达。

这会破坏 evidence 页作为审计证据链入口的完整性：用户能看到摘要总量，却无法继续访问全部原始记录，也无法用键盘进入后续记录。

## 提案

1. `/skills/evidence` 对 raw records 和名单型 `items` 都增加显式“加载更多记录”入口。入口使用标准可聚焦控件，并展示已加载/总量，例如 `100 / 367`。
2. 加载下一批时复用当前 evidence URL 的筛选语义，只追加或覆盖 `limit` 与 `offset`，按当前已加载条数继续请求后续批次；不得改变 `kind/w/wstart/wend/q/rt/src/skill/operator` 等筛选。
3. 刷新带筛选参数的 evidence URL 后可以回到首批 100 条，但必须显示同一筛选口径下的可访问总量，并能继续加载直到全部记录可达；不把“已展开到第 N 批”的临时 UI 状态写入 URL、localStorage 或 sessionStorage。
4. 到底后明确进入完成态：加载入口消失或 disabled，并通过文案让用户能判断已加载完，例如 `已加载全部 367 条记录`。
5. 加载失败时保留已加载记录，显示可重试入口，避免用户卡死在前 100 条。
6. 加载更多请求必须有有界恢复路径：请求超时、用户切换筛选、组件卸载或慢响应返回时，不能把旧口径数据追加到新列表，也不能让按钮永久停在 disabled loading 状态。
7. 每批追加后以唯一记录数和最新 summary 重新计算已加载/总量；服务端总量在加载期间变化时，UI 必须保持可继续加载、可重试或明确完成，不得出现“已加载数小于总量但没有入口”的状态。

## 影响

- **前端**：主要影响 `frontend/src/views/SkillsEvidence.tsx`、`frontend/src/lib/skillsEvidence.ts`、`frontend/src/lib/skillsEvidence.test.ts` 与必要 CSS。`App.tsx` 的 evidence 路由可保持首批请求逻辑。
- **后端**：不改 `/api/skills/evidence` 统计口径、used-only 规则、筛选语义或数据模型，只消费现有 `limit/offset` 能力。
- **事实源**：更新 board spec-delta 与 `wireframes.md`；归档时回流 `openspec/specs/board/spec.md` 与 `docs/wireframes/pages/skills-evidence.md`。
- **测试/验证**：补前端单测覆盖下一批 query、列表追加、367 条唯一记录完整可达、筛选变化重置、慢响应丢弃、超时恢复、错误重试与总量漂移；实现后跑前端单测和构建，并用浏览器检查按钮键盘可达与到底态。
