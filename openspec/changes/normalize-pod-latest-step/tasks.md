# 任务：normalize-pod-latest-step

## 实现

- [x] 1. `server/routes/board.py` 为 `/api/state.sessions[]` 增加 Pods 专用
      `pod_step?: string | null`：仅对
      `source IN (heartbeat, heartbeat_resume) + status=done + current_step="skill: ..."`
      的扫描补采行，在同 identity、同 session 内回退最近非扫描步骤；无回退时为 `null`。
      原始 `current_step` 不变；不改事件写入、schema、feed、Skill 统计、身份合并、状态或时间字段。
- [x] 2. `frontend/src/lib/podStepPresentation.ts` 新增 Pods 步骤展示纯函数：
      双语归一 `tool:` / `tool done:`，抑制 `turn end` / `skill:`，空值回退状态，
      未识别自由文本原样返回；`frontend/src/lib/types.ts` 增加可选 `pod_step?: string | null`。
- [x] 3. `frontend/src/views/Board.tsx` 仅让 `AgentCard` 的步骤行消费该纯函数；
      `pod_step !== undefined` 时使用该值（包括显式 `null`），字段缺失才兼容回退 `current_step`；
      `task` 行、Feed、AgentDetail / Agents 的原始 `current_step`、组件、文案规则、时长和样式保持现状。

## 测试

- [x] 4. 服务端测试：连续 `tool → tool done → turn end → skill: alpha → skill: beta`
      后卡片仍为 done、原始 `current_step` 仍为最新 scan、`pod_step` 回退且不跨并发 session；
      Skill 记录不丢，feed、AgentDetail / Agents 原始值不变；分别覆盖 `heartbeat` 与同 Skill
      跨 180 秒恢复产生的 `heartbeat_resume`；无前序事件时 `pod_step=null`；
      `接入自检` task 原样。feed 测试须同时断言普通 scan 保留、`heartbeat_resume` 仍被排除。
- [x] 5. 前端纯函数测试：中英文工具开始/完成、生命周期与 Skill 抑制、空值/未知状态兜底、
      未知自由文本（含空白和标点）原样；把测试注册到现有 unit runner。

## 文档与验证

- [x] 6. 把 `spec-delta/board/spec.md` 合入 `openspec/specs/board/spec.md`，同步
      `docs/wireframes/pages/board.md` 三个断点和注释；运行显示列宽校验。
- [x] 7. 运行 `python -m py_compile server/*.py server/routes/*.py`；
      `python -m coverage run -m pytest && python -m coverage report --include='server/**/*.py'`
      且整体行覆盖率 ≥ 95%；运行 `npm --prefix frontend run test:unit`、
      `npm --prefix frontend run build` 和 `npm --prefix frontend run lint`。
- [x] 8. 按 `design.md`“真实运行验收”在 `/` 逐条验证工具开始、工具完成、终态、
      连续 Skill 扫描、真实 task、未知自由文本、英文和 feed 范围守门，并把入口、操作、
      可断言信号、DOM 范围与实际观察值交给 @qa 复核。
- [x] 9. 对照 proposal / design / spec delta 做符合度反思：确认没有命令详情、TATP 写协议/schema/shim、
      task、活动流、原始 `current_step`、AgentDetail/Agents 可见行为、时长或无关重构的范围外改动；
      `pod_step` 仅由 Pods AgentCard 消费；事实源已合并。依 `openspec/README.md`，change 在实现上线后归档，
      本次未获部署授权，保留为 active change。

## 逐条验收清单

- [x] `tool: Bash` → `正在运行命令 Bash` / `Running command Bash`。
- [x] `tool done: Bash` → `已完成命令 Bash` / `Finished command Bash`。
- [x] `turn end` 不作为 Pods 卡片步骤显示，由本地化状态兜底。
- [x] 一个或多个 `skill: <name>` 扫描事件不覆盖 `pod_step`；`heartbeat` / `heartbeat_resume`
      均覆盖，原始 `current_step` 与 Skill 统计保持。
- [x] `task="接入自检"` 保持原样，步骤规则不处理 task。
- [x] 未识别自由文本逐字保留；缺失步骤安全退化为状态。
- [x] `/` 真实运行页面的七组验收语句均限定 DOM 范围并有实际观察记录。
- [x] 活动流明确保持原始事件摘要，不同步采用 Pods 卡片归一规则。
- [x] board spec、board wireframe、服务端测试、前端测试与构建同步完成。
- [x] 未引入 TATP 写协议字段、数据库变更、命令详情或无关重构；只增加 board 只读 `pod_step`。

## 验证记录（2026-07-30）

- 后端：`python -m py_compile server/*.py server/routes/*.py` 通过；全量 `pytest` 412 passed；
  `coverage report --include='server/**/*.py'` 整体 96%。
- 前端：`test:unit` 92 passed；生产构建通过；本变更 5 个改动文件定向 ESLint 通过。
  全仓 `npm run lint` 仍有 10 个既有错误和 1 个 warning，均位于未改的 `App.tsx`、
  `RankBars.tsx`、`api.ts`、`Agents.tsx`、`TokenUsage.tsx`。
- 线框：桌面 / 平板 / 手机分别按 120 / 64 / 31 显示列校验，0 mismatch。
- `/` 中文 Pod 卡片 `.card[task="Pods 最新步骤验收"] .step` 依次观察到
  `▸ 正在运行命令 Bash`、`▸ 已完成命令 Bash`、`完成`；步骤行未出现原始工具前缀或 `turn end`。
- 连续上报 `skill: alpha` / `skill: beta` 后，同卡片步骤仍为 `完成`；
  `.feed-item .sub` 分别观察到 `Codex — skill: alpha` / `Codex — skill: beta`，
  导航显示 `2 Skill 资产`。运行时 API 同时返回
  `current_step="skill: beta", pod_step="turn end"`，alpha / beta 各有 1 条 used 会话事实。
- `.card[task="接入自检"]` 的 `.task` 为 `接入自检`，`.step` 先为 `▸ tf-doctor`，
  再逐字变为 `▸ 同步发布说明 · 等待复核`。
- 切换 EN 后，`.card[task="English step acceptance"] .step` 依次为
  `▸ Running command Bash` / `▸ Finished command Bash`，未出现原始 `tool:` 前缀。
- Activity `.feed-item .sub` 实际保留 `tool done: Bash`、`turn end`、`skill: alpha`、
  `skill: beta`；同一主 Pod 卡片步骤仍为英文终态 `done`，范围隔离成立。
