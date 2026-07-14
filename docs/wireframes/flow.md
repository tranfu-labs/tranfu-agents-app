# 页面流转图

> 项目级一份。画**页面之间怎么走**，与单页 `pages/*.md`（页面内部）正交。
> 按用户流程分节，每节一张字符流程图 + 一张步骤表。规则见 [AGENTS.md](AGENTS.md)「流转图」一节，画法见 [legend.md](legend.md)。
> 节点=真实页面（实线框，内部一行指向其 `pages/<page>.md`），可跨流程复现；同页态变化用虚线框 `┄┊` 节点，不伪造成新页面。
> 编号与步骤表一一对应、无孤儿编号。本图是流程图、不是视口，不套比例尺、不分断点。
> 路由来源：`frontend/src/App.tsx`（含 `/admin` 直链后台 Route）+ `frontend/src/components/TopBar.tsx`（顶栏三标签全局导航）。

## 顶部导航全局切换

顶栏三标签在任意页面常驻，互相直达；`*` 兜底路由回落 Pods 看板。

```
                  ┌─ Pods 看板 / ─────┐
            ┌─ ① ─│ → pages/board.md  │◀─ ③ ─┐
            ▼      └───────────────────┘      │
┌─ Agents 列表 /agents ─┐  ── ② ─▶  ┌─ SKILLS 统计 /skills ─┐
│ → pages/agents.md     │ ◀──────   │ → pages/skills.md     │
└───────────────────────┘           └───────────────────────┘
```

| 步 | 从 | 到 | 触发 |
|---|---|---|---|
| ① | 任意页顶栏 | Pods 看板 `/` | 点标签「Pods」（或未知路径 `*` 兜底） |
| ② | 任意页顶栏 | Agents `/agents`、SKILLS `/skills` | 点对应标签 |
| ③ | 任意页顶栏 | 回 Pods 看板 | 点标签「Pods」 |

## 看板巡检 → Agent 详情

看板按 operator 分组展示 Agent 卡片；轮询 `/api/state` 同页刷新卡片，不跳页。

```
┌─ Pods 看板 / ─────┐   ① 点 Agent 卡片    ┌─ Agent 详情 /agent/:key ─┐
│ → pages/board.md  │ ───────────────────▶ │ → pages/agent-detail.md  │
└───────────────────┘                      └──────────────────────────┘
        │  ◀──────────── ② ←返回列表 ────────────────┘ 落到 /agents
        ▼
┌┄ 同页刷新：轮询 /api/state，卡片/活动流原地更新 ┄┐
┊（无跳转）                                        ┊
└┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┘
```

| 步 | 从 | 到 | 触发 |
|---|---|---|---|
| ① | Pods 看板 `/` | Agent 详情 `/agent/:key` | 点 Pod 内某张 Agent 卡片（整卡 Link） |
| ② | Agent 详情 | Agents 列表 `/agents` | 点「← 返回列表」 |

## Agents 列表 → Agent 详情

```
┌─ Agents 列表 /agents ─┐ ① 点 Agent 明细行 ┌─ Agent 详情 /agent/:key ─┐
│ → pages/agents.md     │ ───────────────▶ │ → pages/agent-detail.md  │
│                       │ ◀── ② ←返回列表  │                          │
└───────────────────────┘                  └──────────────────────────┘
```

| 步 | 从 | 到 | 触发 |
|---|---|---|---|
| ① | Agents `/agents` | Agent 详情 `/agent/:key` | 点 Agent 明细表任意行（整行可点，键盘可达） |
| ② | Agent 详情 | Agents `/agents` | 点「← 返回列表」 |

## SKILLS 统计下钻

控制条、选中态和视角切换只改 URL query、同页刷新；按 Skill 视角点明细行先开抽屉，抽屉内保留「前往详情页」逃逸口；新增发布 Skill 入口进入独立列表页；按人视角仍点整行进入操作员详情，返回时带回 query。

```
┌─ SKILLS 统计 /skills ─┐   ② 点 Skill 明细行   ┌┄ 右侧 Skill 抽屉 ┄┐
│ → pages/skills.md     │ ───────────────────▶ ┊ 同页态 sel=skill  ┊
│                       │ ◀────── ③ 关闭抽屉 ─ └┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┘
│                       │   ④ 记录 icon         ┌─ SKILLS 记录页 /skills/evidence ─┐
│                       │ ───────────────────▶ │ → pages/skills-evidence.md       │
│                       │ ◀── ⑤ ←SKILLS(query) │                                  │
│                       │                       └──────────────────────────────────┘
│                       │   ⑥ 待处理查看        ┌─ Clue 详情 /skills/clues/:kind ─┐
│                       │ ───────────────────▶ │ → pages/skills-clues.md          │
│                       │ ◀── ⑦ ←SKILLS(query) │                                  │
│                       │                       └──────────────────────────────────┘
│                       │   ⑫ 新增发布入口      ┌─ 新增发布 Skill /skills/new ─┐
│                       │ ───────────────────▶ │ → pages/skills-new.md        │
│                       │ ◀── ⑬ ←SKILLS(query) │                               │
│                       │                       └───────────────────────────────┘
│                       │   ⑧ 前往详情页        ┌─ Skill 详情 /skill/:name ─┐
│                       │ ───────────────────▶ │ → pages/skill-detail.md   │
│                       │ ◀── ⑨ ←SKILLS(query) │                            │
│                       │                       └───────────────────────────┘
│                       │   ⑩ 点操作员          ┌─ Operator 详情 /operator/:name ─┐
│                       │ ───────────────────▶ │ → pages/operator-detail.md      │
│                       │ ◀── ⑪ ←SKILLS(view)  │                                  │
└───────────────────────┘                       └──────────────────────────────────┘
        │  ▲
        ① 改控制条/视角/选中态（搜索/runtime/来源/w/topn/hz/view/sel）
        ▼  │
┌┄ 同页态：query 写入 URL，KPI/图表/排行/明细原地重筛 ┄┐
┊（无跳转）                                             ┊
└┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┘
```

| 步 | 从 | 到 | 触发 |
|---|---|---|---|
| ① | SKILLS `/skills` | 同页（query 变化） | 改控制条、视角或选中态（搜索框 / runtime / 来源 / 时间窗 `w` / Top N / 隐藏 0 / 按 skill / 按人 / `sel`） |
| ② | SKILLS `/skills` | 右侧 Skill 抽屉（同页） | 在按 Skill 视角点明细表任意行；写入 `sel` 并打开抽屉 |
| ③ | 右侧 Skill 抽屉 | SKILLS 同页 | 点关闭按钮或 backdrop |
| ④ | SKILLS `/skills` | SKILLS 记录页 `/skills/evidence?kind=...` | 点摘要格/问题线索/排行的记录 icon；保留当前 window 和筛选 query |
| ⑤ | SKILLS 记录页 | SKILLS `/skills` | 点「← SKILLS」（删除 evidence-only 参数,回填进入时的 query） |
| ⑥ | SKILLS `/skills` | Clue 详情 `/skills/clues/:kind` | 点待处理线索查看图标或 mobile 待处理事实行；`untracked/idle/zero-install` 分别进入专用版型 |
| ⑦ | Clue 详情 | SKILLS `/skills` | 点「← SKILLS」（回填进入时的 query）；旧 `/skills/evidence?kind=untracked|idle|zero_install` 兼容跳转到 clue |
| ⑧ | 右侧 Skill 抽屉 | Skill 详情 `/skill/:name` | 点「前往详情页」按钮（附带 `location.search`） |
| ⑨ | Skill 详情 | SKILLS `/skills` | 点「← SKILLS」（回填进入时的 query） |
| ⑩ | SKILLS `/skills` | Operator 详情 `/operator/:name` | 按人视角点排行表任意行（整行跳转，附带 `location.search`） |
| ⑪ | Operator 详情 | SKILLS `/skills?view=operator...` | 点「← SKILLS」（强制回按人视角并回填 query） |
| ⑫ | SKILLS `/skills` | 新增发布 Skill `/skills/new` | 点当前时间窗变化或问题线索中的「新增发布 Skill」记录 icon；保留 `w/wstart/wend/q` 与 own/meta 来源 |
| ⑬ | 新增发布 Skill | SKILLS `/skills` | 点「← SKILLS」（回填进入时的 window/search query） |

## 后台清理台进入与删除流程

`/admin` 是受保护的独立页面，不在顶栏导航，靠直链进入；进页先过钥匙浮层，删除走「预览即承诺 → 二次确认」，同页态推进、不跳转。

```
┌─ 直链 /admin ─┐  ① 输 X-TF-Admin-Key   ┌┄ 钥匙浮层（同页态）┄┐  ② 401 ┄▶ ┊报错+denied 审计┊
│ 浏览器地址栏  │ ─────────────────────▶ ┊ → pages/admin.md   ┊                └┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┘
└───────────────┘                         └┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┘
                                                   │ ③ 认证通过
                                                   ▼
┌─ 后台清理台 /admin ─┐ ④ 勾选→预览  ┌┄ 预览态(dry-run)┄┐ ⑤ 确认  ┌┄ 二次确认浮层 ┄┐ ⑥ 永久删除
│ → pages/admin.md    │ ───────────▶ ┊ token+副作用    ┊ ──────▶ ┊ 超阈手输行数  ┊ ─────▶ ┐
│                     │ ◀── ⑦ 取消/集合变 409 重看 ──┘          └┄┄┄┄┄┄┄┄┄┄┄┄┄┘        │
│                     │ ◀──────────── ⑧ Toast 实删数 + 列表刷新 ◀────────────────────────┘
│  回收站 Trash tab   │ ⑨ 点恢复 ──▶ 整批 restore（键冲突回报）→ 列表刷新
└─────────────────────┘
```

| 步 | 从 | 到 | 触发 |
|---|---|---|---|
| ① | 直链 `/admin` | 钥匙浮层 | 输入 `X-TF-Admin-Key`（存 sessionStorage） |
| ② | 钥匙浮层 | 同页报错态 | 401：钥匙错或 `TF_ADMIN_KEY` 未配置；写 denied 审计 |
| ③ | 钥匙浮层 | 清理台主页面 | 认证通过 |
| ④ | 清理台 | 预览态（同页） | 勾选对象点「预览删除影响」→ `POST /api/admin/preview` |
| ⑤ | 预览态 | 二次确认浮层 | 点「确认删除」 |
| ⑥ | 二次确认 | 执行删除 | 超 `TF_ADMIN_MAX_ROWS`/跨多 operator 须手输行数 → `DELETE /api/admin/data`（回带 token） |
| ⑦ | 预览/确认 | 回清理台 | 取消，或集合变动返回 409 需重新预览 |
| ⑧ | 删除完成 | 回清理台（刷新） | Toast 回显各表实删行数，列表自动刷新 |
| ⑨ | 回收站 Trash | 回清理台（刷新） | 点「恢复」→ `POST /api/admin/restore` 整批回滚 |
