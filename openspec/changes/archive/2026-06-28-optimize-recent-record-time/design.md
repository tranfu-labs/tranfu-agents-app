# 设计：optimize-recent-record-time

## 方案

### 1. 时间展示规则
对有具体时刻的 ISO 时间戳(如 `first_seen`、`last_seen`、`created`)统一先解析成 `Date`,再按浏览器本地时区格式化。

最近记录专用规则:

| 条件 | 表格可见文本 | hover title |
|---|---|---|
| `first_seen` 无效/缺失,但有 `day` | 原始 `day` | 原始 `day` |
| `first_seen` 是浏览器本地今天,且不晚于当前时间 | 相对时间: `刚刚` / `5分钟前` / `2小时前` | 本地绝对时间 + 浏览器时区 |
| `first_seen` 是浏览器本地昨天或更早 | 本地绝对时间 `YYYY-MM-DD HH:mm:ss` | 本地绝对时间 + 浏览器时区 |
| `first_seen` 在未来或解析异常 | 本地绝对时间或回退文本 | 同可见文本 |

英文界面使用 `just now` / `5m ago` / `2h ago`。相对时间只在本地今天内使用;昨天不显示"昨天",直接显示绝对时间,满足"相对时间克制"。

绝对时间 title 示例:

```text
2026-06-28 10:32:07 Asia/Shanghai
```

`Intl.DateTimeFormat().resolvedOptions().timeZone` 取不到时省略时区名。

### 2. 代码组织
新增 `frontend/src/lib/timeFormat.ts`,避免把可测逻辑散在 JSX 中:

- `formatLocalTimestamp(iso, lang)`:
  返回浏览器本地绝对时间与 title。
- `formatRecentRecordTime(firstSeen, fallbackDay, lang, now?)`:
  返回 `{ label, title }`,其中 `now` 只用于测试注入。

`frontend/src/lib/utils.ts` 保留既有导出,但 `fmtTs()` 改为基于本地绝对时间格式,供 Admin 继续使用。两个详情页不再直接用 `fmtTs()`,而用 `formatRecentRecordTime()`。

### 3. 页面改动

- `SkillDetail.tsx`:最近记录首列:
  - `record.first_seen` 有效时按最近记录规则显示。
  - `title` 属性显示本地绝对时间。
  - `record.first_seen` 缺失时回退 `record.day`。
- `OperatorDetail.tsx`:同上。
- `Admin.tsx`:清单"最近"、删除预览活跃会话、回收站批次时间改为本地绝对时间。Admin 是高风险操作界面,不使用相对时间,避免"几分钟前"这类动态文本影响删除判断。

### 4. 广度审计结论

同类需要修正:

- `frontend/src/views/Admin.tsx` 的 `fmtTs(row.last_seen)` / `fmtTs(session.last_seen)` / `fmtTs(batch.created)`:当前也是截 ISO,应显示浏览器本地绝对时间。
- `frontend/src/views/SkillDetail.tsx` 与 `frontend/src/views/OperatorDetail.tsx` 的 `fmtTs(record.first_seen)`:本次主改动,应显示最近记录专用格式。

不应修正为浏览器时区:

- `day`、`first_day`、`last_day`:这些是服务端 UTC 日统计口径,按 specs/board 与 specs/ingest 仍应保留 UTC 日。
- SKILLS 图表时间轴与 tooltip 日期:依赖服务端 `today` 和 UTC day bucket,不能改成本地日,否则会与后端聚合错位。
- Board 卡片与活动流的 `ago(ts)`:显示的是与当前时间的相对差值,不暴露墙钟时区,不存在 UTC 冒充本地的问题。
- Token 用量页:该页已用 `toLocaleString()` 与请求侧 `timezone_offset_minutes`,不是本问题同源。

## 权衡
- 不把服务端输出改成本地时间。服务端必须保持 UTC 事实源,浏览器本地展示属于前端职责。
- 最近记录只对"今天"显示相对时间,放弃昨天/本周这类更多相对表达,降低认知负担。
- Admin 只改为本地绝对时间,不做相对时间,保持清理操作的可审计性和稳定性。
- 不扩大到 UTC 日统计字段,避免看板统计口径与浏览器本地日界线发生不一致。

## 测试设计

单元测试(新增前端纯函数测试):

1. `TZ=Asia/Shanghai`,当前时间为 `2026-06-28T01:00:00+08:00`,记录 `2026-06-27T16:30:00+00:00`:
   - 浏览器本地为今天 `00:30:00`,可见文本为 `30分钟前`,title 为 `2026-06-28 00:30:00 Asia/Shanghai`。
2. 同一当前时间,记录 `2026-06-27T15:00:00+00:00`:
   - 浏览器本地为昨天 `23:00:00`,可见文本为 `2026-06-27 23:00:00`,不是"1小时前"或"昨天"。
3. 今天 30 秒内:
   - 中文为 `刚刚`,英文为 `just now`。
4. 缺 `first_seen` 但有 `day=2026-06-27`:
   - 可见文本和 title 都是 `2026-06-27`。
5. 绝对时间格式固定补零到秒。

AI 验证流程:

1. `TZ=Asia/Shanghai node --experimental-strip-types --test frontend/src/lib/timeFormat.test.ts`
2. `npm --prefix frontend run build`
3. 启动本地前端后人工/浏览器截图检查:
   - `/skill/:name` 最近记录今天内为相对时间,hover title 是本地绝对时间。
   - `/operator/:name` 同上。
   - `/admin` 仍显示稳定绝对时间,但已按浏览器时区转换。

## 风险
- 浏览器时区来自用户设备,跨成员截图可能显示不同墙钟时间。这符合需求,但文档中必须明确是浏览器时区。
- JS `Date` 对无 offset 的历史脏数据会按浏览器本地解释。当前 `first_seen/last_seen/created` 正常由服务端 ISO with offset 产生;异常数据走兜底。
- title 原生 tooltip 在移动端不可用;移动端可见文本仍按同一规则显示,不额外做浮层。
