# 设计：use-shanghai-stats-day

## 方案
1. 在 `server/db.py` 增加统计时区工具:
   - `STATS_TZ = ZoneInfo("Asia/Shanghai")`。
   - `stats_now()` 返回基于 `app.datetime.now(timezone.utc)` 转换到统计时区的 aware datetime。
   - `stats_today()` / `stats_day()` / `stats_day_cutoff(days)` 提供统一日级日期。
   - `now_iso()` 保持 UTC,不改变已有具体时刻语义。

2. 修改 ingest 写入:
   - `POST /v1/events` 在收到事件时生成一次 `day = stats_day()`。
   - `skill_uses.day`、`skills_seen.first_day`、`events.day` 都写这个上海日。
   - `recv`、`first_seen`、`last_seen` 仍写 UTC `recv`。

3. 修改 board 读侧:
   - `_iter_sessions()` 的 90 天窗口用 `stats_day_cutoff(WINDOW_DAYS)` 过滤 `events.day`。
   - `metrics()` 用 `stats_now()` 生成 `today`、本周起点、7/90 天轴,活跃时段按 `Asia/Shanghai` 日边界拆分后回填到上海日 bucket。
   - `leverage()`、`skill_usage()`、`skills_overview()`、`operator_detail_payload()`、`skill_detail_payload()` 全部用统计日计算 `today`、d7/d14/d30 与返回 `today`。
   - 这些查询仍读取 `day` 列。旧数据不迁移,因此旧行的日桶保持历史 UTC 语义,新行进入上海日桶。

4. 更新测试:
   - 固定 UTC 当前时间为 `2026-06-12T16:05:00Z`,断言新写入事件和 skill 使用的 `day` 为 `2026-06-13`。
   - `/api/skills?days=30` 在同一固定时间返回 `today=2026-06-13`。
   - 构造跨上海午夜的 running/done 事件,断言 `/api/state` 的活跃 series 按上海日拆分。

## 权衡
- 不用 Docker `TZ`:应用层显式统计时区,部署环境变化不会改变口径。
- 不用 SQLite `localtime`:避免依赖容器本地时区,也避免 SQL 与 Python 两套日历口径漂移。
- 不迁移旧数据:满足本次需求边界,降低上线风险;代价是切换点附近历史日桶不会被重算。
- 不把 `recv` 改为上海时区字符串:UTC instant 更适合排序、比较、stale 判断和跨时区展示。

## 风险
- 旧数据与新数据日桶语义不同,跨切换点的趋势可能有一天级偏差。此偏差按需求接受,不做回填。
- 活跃时长按上海日边界拆分后,与旧版本同一天的 today/week 数值可能变化。这是本变更目标行为。
- Python `zoneinfo` 依赖系统时区数据库;当前 Docker 基于 Python 官方镜像通常可用。若极端环境缺失 tzdata,启动或调用统计工具会暴露错误,需要在镜像中补 tzdata。
