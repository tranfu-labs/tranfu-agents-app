# 设计：normalize-pod-latest-step

## 锁定范围

本变更只处理 `/` Pods 卡片的步骤行，不借机实现结构化活动协议或单次运行耗时。

| 输入 / 场景 | Pods 卡片步骤行（中文） | Pods 卡片步骤行（英文） |
|---|---|---|
| `tool: Bash` | `▸ 正在运行命令 Bash` | `▸ Running command Bash` |
| `tool done: Bash` | `▸ 已完成命令 Bash` | `▸ Finished command Bash` |
| `turn end` | 不直出；显示本地化状态 `完成` | 不直出；显示本地化状态 `done` |
| `skill: ai-opportunity-evaluation` | 不直出；Pods 专用 `pod_step` 先回退非扫描步骤，仍无可见步骤时显示状态 | 同左 |
| `tf-doctor` / 其它未知自由文本 | 原样显示 | 原样显示 |
| 缺失 / 空步骤 | 显示本地化状态 | 显示本地化状态 |

`task` 行完全不经过该规则，`接入自检` 等真实任务名保持字面值。

## 方案

### 1. 服务端：状态事件与卡片步骤来源分离

`_snapshot()` 仍以当前逻辑从 `source IN ('heartbeat', 'heartbeat_resume')` 选每个身份最新事件，
保持以下字段及口径：

- `status`、`ts/recv/last_seen`、`session_id`；
- `task`、原始 `current_step`、profile、shim、质量与活跃时长；
- 按 `(operator, agent || runtime)` 合并卡片。

为 `/api/state.sessions[]` 增加仅供 Pods 展示的可选派生字段：

```text
pod_step: string | null
```

普通事件的 `pod_step` 等于原始 `current_step`。若最新事件命中本项目扫描器生成的窄模式：

```text
source IN ("heartbeat", "heartbeat_resume")
status = done
current_step starts with "skill: "
```

则在同一 `operator + runtime + (agent || runtime) + session_id` 内按 `id DESC` 寻找最近一条不命中
该模式的事件，并用它的 `current_step` 作为 `pod_step`。连续多个、来源混合为 `heartbeat` /
`heartbeat_resume` 的 Skill 扫描行会一次跳过；若没有前序非扫描事件，则 `pod_step=null`。

`heartbeat_resume` 必须纳入扫描判定：ingest 对同 session、同 `status/current_step` 且距最后确认心跳
超过 180 秒的事件写成 `heartbeat_resume`。因此同一 `skill: <name>` 跨断档再次补采时确实会走这条写路径，
不能只覆盖 `heartbeat`。

选择同一 session 是为了避免并发 session 时从另一轮借到不相关步骤。扫描事件仍然：

- 原样保留在 `events`；
- 正常写入 / 幂等更新 `skill_uses`；
- 保持 `/api/state.feed` 既有来源规则：`source=heartbeat` 的扫描行保留在历史流，
  `source=heartbeat_resume` 仍作为内部恢复边界被 feed 排除；
- 原样保留在 `sessions[].current_step`，供 AgentDetail、Agents 和其它既有消费者继续使用；
- 继续参与既有终态质量事实，不改变 `status=done`。

实现应把扫描判定收进一个窄、可测的服务端 helper，并同时覆盖 `heartbeat` / `heartbeat_resume`，
避免在 SQL 多处复制字符串条件。可采用一次有界补查或等价 SQL 投影；不得为此把全历史 events 拉入
Python。`/api/state` 最多 200 张卡，补查须限定 identity、session 和倒序首条，并利用现有事件查询路径。

`pod_step` 是 board 只读 API 的加法字段，不是 TATP 写协议字段：shim 不上报它，ingest 不接收或落库它。
旧客户端忽略未知字段；前端类型把它声明为可选以兼容尚未升级的服务端。

### 2. 前端：纯函数投影步骤文案

新增 `frontend/src/lib/podStepPresentation.ts`（名称可在实现时按现有命名微调），提供不依赖 React 的纯函数：

```ts
type PodStepPresentation = { text: string; showMarker: boolean }
presentPodStep(step: string | null | undefined, status: Status, lang: Lang): PodStepPresentation
```

规则顺序：

1. 精确识别 `tool done:`，保留冒号后的工具对象，输出本地化「已完成命令 / Finished command」；
2. 精确识别 `tool:`，输出本地化「正在运行命令 / Running command」；
3. 精确识别生命周期 `turn end`，返回本地化状态且不显示步骤 marker；
4. 防御性识别 `skill:`，返回本地化状态且不显示步骤 marker，覆盖无前序事件或旧服务端 payload；
5. 缺失或只有空白时返回本地化状态且不显示步骤 marker；
6. 其它自由文本返回原始输入并显示步骤 marker，不做大小写、空白、截断或翻译改写。

识别时可对前缀做大小写不敏感和外围空白容错，但未知文本的返回值必须是原始值，保证安全退化不丢信息。
`AgentCard` 使用：

```ts
const step = agent.pod_step !== undefined ? agent.pod_step : agent.current_step
```

然后把 `step` 交给纯函数，并只在返回的 `showMarker=true` 时加现有 `▸ ` 前缀。必须用“字段是否为
`undefined`”判断兼容旧服务端，不能用 `||` 或 `??`：
新服务端显式返回的 `pod_step=null` 表示没有安全回退步骤，若回退原始 `current_step` 会重新泄漏 Skill 文案。
真实步骤保留现有 `▸ ` 前缀；状态兜底不伪装成步骤。任务行、chips、metrics、链接和样式不变。

中英文短语可由该纯模块内的小型常量承载，或加入现有 i18n；实现时选择更符合当前类型约束、且能避免
重复文案的一种。不得把翻译判断散落在 JSX。

AgentDetail、`/api/agents` 等既有消费者继续读取原始 `current_step`，不消费 `pod_step`；因此本变更不改变
这些页面的现有可见值、组件、版式或交互。用户可见验收只针对 `/` Pods 卡片。

### 3. 活动流范围判断

本次不把同一函数接入 `Feed`，原因不是技术限制，而是产品边界：

- 用户明确只关心卡片最新状态；
- Feed 表示最近历史事件，当前规格要求它保留真实状态转变；
- 对 feed 做相同抑制会改变历史证据呈现，并引出是否删除 Skill / 生命周期记录的另一个产品决策。

因此 `Feed` 继续显示 `item.current_step || item.task || ''`；普通 `heartbeat` scan 行继续进入 feed，
`heartbeat_resume` 继续按 ADR-0003 被排除。本变更的测试要显式锁定该边界，避免实现时顺手把 feed
一并“清洗”或把恢复边界放入历史流。

### 4. 线框同步

实现时只修改 `docs/wireframes/pages/board.md`：

- 三个断点的卡片步骤示例由 `▸ current_step` 改成 `▸ 已完成命令 Bash`（或等宽可容纳的同义示例）；
- 注释 ② 说明步骤行会归一工具前缀、抑制 `turn end` / `skill:`、未知文本原样退化；
- 注释 ③ 明确活动流仍为原始历史事件摘要；
- 使用 `docs/wireframes/AGENTS.md` 的东亚宽度脚本校验 120 / 64 / 31 列。

无页面、路由或跳转变化，`flow.md` 不改。

## 测试设计

### 服务端定向测试

在 `tests/test_board.py` 增加同 session 顺序：

```text
running / tool: Bash
running / tool done: Bash
done    / turn end
done    / skill: alpha + skill=alpha
done    / skill: beta  + skill=beta
```

断言：

- `/api/state.sessions` 仍只有一张合并卡；
- 卡片状态仍为 `done`；
- 原始 `current_step` 仍为最新 `skill: beta`；
- `pod_step` 回退到 `turn end`，供 Pods 前端按终态显示；
- 两个 Skill 使用记录仍正常存在，统计不丢；
- `/api/state.feed` 仍含 `source=heartbeat` 的原始 Skill 扫描与生命周期事件；
- AgentDetail / `/api/agents` 继续读取原始 `current_step`，不发生可见字段替换；
- 另造 `task="接入自检", current_step="tf-doctor"`，task 与未知步骤均原样返回。

另增加写路径矩阵：

- 首条 Skill 扫描为 `source=heartbeat`；
- 同 `status/current_step` 跨 180 秒恢复的 Skill 扫描为 `source=heartbeat_resume`；
- 两者都被 `pod_step` 回退逻辑跳过，而原始 `current_step` 不变；feed 继续只包含
  `source=heartbeat`，不得因本变更新增 `heartbeat_resume`。

可通过可控服务端时间走真实 ingest，或用与 ingest 契约一致的数据库 fixture 构造
`heartbeat_resume`；测试必须断言 source，不能只手写期望。另覆盖只有扫描事件、没有前序非扫描事件的
失败路径：`current_step` 原样保留，`pod_step=null`，接口正常返回、不抛错。

### 前端纯函数测试

覆盖：

- `tool:` / `tool done:` 中英文；
- 工具名与对象文本保留；
- `turn end` / `skill:` / 空值回退本地化状态；
- `接入自检`、`tf-doctor`、带标点和空白的未知自由文本原样返回；
- 未知 status 继续沿用 `statusName` 的安全退化。

### 项目验证

- `python -m py_compile server/*.py server/routes/*.py`
- `python -m coverage run -m pytest && python -m coverage report --include='server/**/*.py'`，整体行覆盖率 ≥ 95%
- `npm --prefix frontend run test:unit`
- `npm --prefix frontend run build`
- `npm --prefix frontend run lint`（若基线存在与本变更无关的失败，必须单独报告，不得误称全绿）
- wireframe 显示列宽校验

## 真实运行验收

实现完成后由 @qa 在真实运行应用逐条复核；仅测试 / build 通过不能替代这些观察：

1. **工具开始**
   - 入口：打开 `/`，切中文；
   - 操作：向同一 session 上报 `status=running,current_step="tool: Bash"`；
   - 断言：对应 Pod 卡片步骤行显示 `▸ 正在运行命令 Bash`，该卡片步骤行内不出现原文
     `tool: Bash`；Activity 是否出现原文不属于此断言。
2. **工具完成**
   - 操作：同 session 上报 `status=running,current_step="tool done: Bash"`；
   - 断言：对应 Pod 卡片步骤行更新为 `▸ 已完成命令 Bash`，该步骤行内不出现
     `tool done: Bash`，且不增加 shell 命令详情。
3. **终态**
   - 操作：同 session 上报 `status=done,current_step="turn end"`；
   - 断言：对应 Pod 卡片步骤行内不出现 `turn end`，而显示中文终态 `完成`；
     同卡片底部既有状态仍为 `完成`。
4. **Skill 扫描不覆盖**
   - 操作：终态后连续上报 `skill: alpha`、`skill: beta`，分别携带同名 `skill`；
   - 断言：对应 Pod 卡片步骤行内不出现 `skill: alpha/beta`，仍表达终态；
     Activity 可保留原文，SKILLS 统计可查到 alpha / beta。
5. **真实任务与安全退化**
   - 操作：另一个身份上报 `task="接入自检",current_step="tf-doctor"`，再用自由文本
     `current_step="同步发布说明 · 等待复核"` 复核；
   - 断言：对应 Pod 卡片任务行完整显示 `接入自检`；该卡片步骤行先完整显示 `tf-doctor`，
     更新后完整显示 `同步发布说明 · 等待复核`，不被翻译或清空。
6. **英文**
   - 操作：切换 EN，重复工具开始 / 完成；
   - 断言：对应 Pod 卡片步骤行分别显示 `▸ Running command Bash`、`▸ Finished command Bash`，
     该步骤行内不出现 `tool:` / `tool done:` 原始前缀。
7. **范围守门**
   - 入口：仍在 `/` 查看右侧 Activity；
   - 断言：Activity 容器内继续展示 `tool done: Bash`、`turn end`、`skill: alpha/beta` 等原始历史
     事件摘要；同时对应 Pod 卡片步骤行保持上述归一结果。

## 权衡

- 选择“Pods 专用 `pod_step` + 前端文案投影”，而不是直接改 `current_step`：保留所有既有消费者的
  原始事件语义，只让用户点名的 Pods 卡片获得安全回退；代价是 board 响应增加一个加法字段。
- 不增加 TATP 写协议或数据库字段：只能根据现有窄前缀识别工具活动，无法展示实际命令。
- 不归一 feed：严格遵守“只关心最新状态”的范围，代价是同页历史流仍可见内部前缀；如后续要改，
  应单独确认历史证据的产品语义。

## 风险与回滚

- **误判用户自由文本 `skill: ...`**：服务端判定同时限定 `status=done`、
  `source IN ('heartbeat','heartbeat_resume')` 和精确前缀，且只影响 `pod_step`；原始 `current_step`、
  事件与 feed 不丢。
- **并发 session 串步**：回退查询必须限定同一 session，不允许从同身份其它 session 借步骤。
- **前序事件缺失**：返回空步骤并由状态兜底，不抛错、不显示扫描文案。
- **查询开销**：只对最新行命中扫描模式的卡片做有界首条补查；实现后用测试确认没有全表 Python 扫描。
- **新旧服务端混用**：`pod_step` 可选；字段缺失时前端回退原始 `current_step`，同时纯函数防御性抑制
  `skill:`。字段显式为 `null` 时不得回退原始值。
- **回滚**：删除 `pod_step` 投影与前端纯函数接入即可；无迁移、无数据回写。
