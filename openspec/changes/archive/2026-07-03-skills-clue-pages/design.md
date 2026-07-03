# 设计

## 路由与兼容

用户可见的三类治理详情使用 `/skills/clues/:clueKind`：

- `untracked` 映射 API `kind=untracked`
- `idle` 映射 API `kind=idle`
- `zero-install` 映射 API `kind=zero_install`

底层仍复用 `/api/skills/evidence`，避免扩散服务端端点。旧 `/skills/evidence?kind=untracked|idle|zero_install` 在前端重定向到新 clue 路由；其它 evidence kind 继续走通用记录页。

## 数据

`idle` 需要安装者明细。服务端从 `profiles` 最新快照读取每个 agent 的 skill 列表，按 skill 聚合：

```json
{
  "name": "write-spec",
  "installers": 2,
  "installers_detail": [
    {"operator": "wing", "agent_key": "claude", "runtime": "claude-code", "profile_updated_at": "..."}
  ],
  "last_day": "2026-06-25"
}
```

`zero_install` 明确返回 `installers=0` 和空 `installers_detail`。`idle_installed` 总览 item 同步返回 `last_day`，用于 row 模板展示“上次使用”。

## 版型

### `/skills`

待处理线索保留三列，但 row 内容按 kind 定制：

- 未收录：`7 条记录 · 2 人 · 上次使用 07-02`
- 装了没用：`2 人安装 · 近 7 天 0 次 · 上次使用 06-25`
- 零装机：`0 人安装 · 收录 07-03`

每行只保留两个主操作：查看图标 + `忽略` 文字按钮。移动端仍走更多菜单，但文案一致。

### `/skills/clues/untracked`

第一屏：

```text
← SKILLS   未收录记录
近 7 天 · 2026-06-27 ~ 2026-07-03 · 来源：未收录 · skill：coolify-deploy

Top Operators
空空    5/7 · 71% · 1 skills
Wing    2/7 · 29% · 1 skills

未收录记录
Time · Skill · Operator · Runtime · Session
```

若 URL 已带 `skill=`，隐藏 Top Skills。因为当前页面已经是单 skill 下钻，Top Skills 只会重复。

### `/skills/clues/idle`

第一屏是安装者名单：

```text
← SKILLS   装了没用
近 7 天 · 2026-06-27 ~ 2026-07-03 · skill：write-spec

安装者名单
Skill        人安装   安装者                         上次使用
write-spec   2        wing · claude/claude-code       2026-06-25
                      zoe · code/codex
```

不展示 Top Skills / Top Operators。

### `/skills/clues/zero-install`

第一屏是零装机名单：

```text
← SKILLS   零装机
近 7 天 · 2026-06-27 ~ 2026-07-03

零装机名单
Skill        Source   人安装
meta-tool    meta     0
```

不展示 Top Skills / Top Operators。

## 文案

- 用户可见的 “evidence / 证据” 统一替换为 “records / 记录” 或 “list / 名单”。
- 筛选 chip 用人话：
  - `w=7d` → `近 7 天`
  - `window_start/window_end` → `2026-06-27 ~ 2026-07-03`
  - `src=non_catalog` → `来源：未收录`
  - `src=own,meta` → `来源：公司库`

## 测试

- 单测 URL 映射、旧链接重定向、clue API query。
- 单测筛选 chip 不露 raw key / raw enum。
- 单测 Top Operators 百分比和 skill-scoped Top Skills 隐藏规则。
- 后端测试 `idle` item 安装者明细和 skill filter。
- copy 测试避免相关页面重新出现“证据”旧文案和 `×` 忽略按钮。
