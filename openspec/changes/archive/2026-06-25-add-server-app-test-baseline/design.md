# 设计:add-server-app-test-baseline

## 方案

### 1. 工具与配置

- `server/requirements.txt`(或新增 dev requirements):追加 `coverage>=7.0`(本机已验证 7.14.3 可用)。
- `pyproject.toml` 新增 `[tool.coverage.run]` 与 `[tool.coverage.report]` 节(若项目暂无 `pyproject.toml`,
  改写 `.coveragerc`,实施时择一,见**待决项 1**):
  - `source = ["server/app.py"]`
  - `exclude_lines = ["pragma: no cover", "if __name__ == \"__main__\":"]`
- 测试入口仍是 `pytest`;覆盖率口令 `coverage run --source=server -m pytest && coverage report --include='server/app.py'`,
  写进 `AGENTS.md` 的「修改后检查」节(由 Change B 顺手补,或本变更尾巴补一行)。

### 2. 测试分组(按 spec 域,对齐 Change B 拆分边界)

每个新文件顶部一行注释指明对应 `openspec/specs/<domain>/spec.md`。

#### `tests/test_catalog.py`(新建,~120 行)
- `_parse_catalog_payload`:
  - `bytes` 入参与 `str` 入参都接受
  - `skills` 是 dict 顶层 / 是裸 list
  - 缺 `name` / 重名 / 无效 `type`(走 `external` 兜底)
  - 非法 type(`int`)抛 `ValueError`
- `_fetch_catalog`:monkeypatch `urllib.request.urlopen`
  - 成功:返回合法 JSON
  - 超时 / HTTPError:走异常路径,`_record_catalog_error` 写 `_catalog_state["error"]`
  - 响应 > 768KB:验证截断(若实现保留)或返回 ValueError
- `_save_catalog_cache` ↔ `_load_catalog_cache` 回环:写入后立刻读出,字段一致;
  `_catalog_state` 内存态与 DB 持久态都正确
- `_catalog_context` 输出 `(items, by_name, meta)` 三元组结构

#### `tests/test_admin_targets.py`(新建,~200 行)
- `_validate_targets` 全分支:
  - 合法:`session_ids` / `skill` / `operator` / `operator+agent` / `operator+runtime` / `before_day+operator`
  - 非法:`targets=[]` 抛 400、`target` 非 dict 抛 400、无 kind 抛 400、多 kind 抛 400、
    `session_ids` 非数组 / 非字符串元素 / 空数组 抛 400、`before_day` 不是 10 字符 / 缺 operator 抛 400、
    `skill` 是空串 抛 400
- `_session_ids_by_operator`:
  - 不带 agent/runtime → 收口到该 operator 所有 session
  - 带 agent → 只取该 agent 的 session
  - 带 runtime → 只取该 runtime 的 session
  - 同时带 → AND 收口
  - 不带 agent 时,同时通过 `skill_uses` 表的 session 也算入
- `_session_ids_before_day`:同上 + 日期边界(`day < ?` 严格小于)
- `_restore_admin_batch` 三态:
  - batch_id 不存在 → 404
  - batch_id 已 restored → 409
  - 成功:`restored=1` 标记、`admin_audit` 写一条 `restore`
- `DELETE /v1/events`(旧 curl 路径):
  - 既无 session_ids 又无 operator → 400
  - session_ids 含非字符串 → 400
  - operator 路径 + 活跃会话无 force → 400 "active sessions require force=true"
  - rows 超 `ADMIN_MAX_ROWS` 且无 `confirm_count` → 400

#### `tests/test_admin_inventory.py`(新建,~180 行)
- 空库:`/api/admin/inventory` 返回 `{operators: [], identities: [], sessions: [], skills: []}`
- 单 operator + 单 session:四张表都有一行
- profile-only identity(没 events、只有 profiles 表):`identities` 仍出现该行
- 有 `skill_uses` 无 `events` 的 session:`sessions` 仍出现该行
- runtime-only operator(没 `agent` 字段):`identities` 的 `name` 退化为 runtime
- `q` needle 大小写不敏感、JSON 字段串匹配命中
- `offset/limit` 边界:`limit=1 offset=0` / `offset >= 总数`
- active 标记跨表传染:有活跃 session → operator/identity/skill 都标 `active=true`

#### `tests/test_board.py`(新建,~150 行)
- `metrics`:
  - `blocked` 状态计数(`q["blocked"] += 1`)
  - `auto_rate`:`saw_wait=True` 的会话 `done` 不计入 auto;`saw_wait=False` 的 `done` 计入
  - 跨天 active:`started` 在 23:59、`done` 在次日 00:01,要按天边界拆分到两个桶
- `_snapshot` 的 `card`:
  - 心跳过期(超 `STALE_SECONDS=180`)的 `running` 翻为 `idle`
  - `input` / `output` 超 4000 字符截断
  - `quality` 注入 `reuse` 字段(跨人技能重叠)
- `/api/agent/{key}`:404 + 成功(key 拼接 `operator::agent`)
- `/api/operator/{name}`:404(无 used 记录)+ 成功
- `/api/skill/{name}`:404(skill 不存在)+ 成功

#### `tests/test_onboarding.py`(新建,~80 行)
- `/shims/{path}` 目录穿越:`/shims/../app.py` 应该 404,不是 200 也不是 500
- `/shims/{path}` 合法子路径(`tf_hook.py` / `wrapper/tf-run`):200,内容非空
- `/shims/manifest`:返回 `{schema, version, files}`,每个 file 有 `target` 与 `sha256`
- `/install.sh`:文件存在态返 200;mock 缺失态返 404
- `/healthz`:`text/plain` + body=`ok`(同时验证它不打 DB)

#### `tests/test_protocol.py`(扩展,~30 行)
- enroll:同一 IP 连续 `TF_ADMIN_RATE_MAX+1` 次错钥 → 第 N+1 次 429 + `Retry-After`
- ingest:`skill` 有但 `session_id` 缺 → 返回 `{ok: true, logged: false, skill_ignored: true}`
- ingest:body > `MAX_BODY` → 413

### 3. 豁免名单(`# pragma: no cover`)

| 行号(基线) | 内容 | 豁免理由 |
|---|---|---|
| 2647-2648 | `if __name__ == "__main__": uvicorn.run(...)` | 非测试目标,生产由 uvicorn CLI 拉起 |
| 89-90 | `if ADMIN_KEY and (len < 16 or in weak):` 弱钥 print 告警 | 启动期 print,造时间窗困难 |
| 670-672 | `_catalog_loop` while True | 后台线程主循环,conftest 已禁用线程启动 |
| 677-683 | `_start_catalog_sync` 实际启线程的分支 | 同上 |
| 687 | `_startup_catalog_sync` | startup 回调,被 conftest 抢先标 started |
| 423-424、512-513、599-600、716-722、1908-1909、2008-2009、2030、2037-2038、2592-2593 | `except Exception: pass` 防御性兜底 | 只在脏数据 / 异常路径触发,造数据成本远高于价值 |
| 2584-2585 | `FileNotFoundError` SPA index 兜底 | 开发期路径,生产构建必然存在 |
| 327 | `ALTER TABLE` 兼容老 schema 迁移 | 空 DB 永不进 |
| 449-452 | `_rate_prune` stale 清理 | 触发条件是 `_RATE_MAX_ENTRIES=10000` 撑爆,测试夹具不易造 |

豁免后实际可测语句 ≈ 1396;命中 95% 等价 missing ≤ 70。

### 4. conftest 扩展

`tests/conftest.py` 视需要新增:
- `fake_catalog(monkeypatch)`:替换 `urllib.request.urlopen`,返回可控的 JSON 或抛错。
- `admin_client(client)`:已设好 `TF_ADMIN_KEY` 的 client 快捷方式。
- 这些只在新测试需要时再加,不预先扩展。

## 权衡

- **行覆盖 vs 分支覆盖**:选行覆盖 95%。分支覆盖会逼出大量「都是 None 的边角」用例,
  价值低、工作量翻倍;行覆盖配合豁免名单足以保证「拆分时所有正常路径有断言」。
- **测试文件预先按 Change B 边界分**:多此一举吗?不。否则 Change A 写到一半 Change B 拆分时,
  测试位置又要再挪一次,等于做两遍。
- **`# pragma: no cover` vs 强测每行**:防御性 `except` 通常测不到、也不该花成本测——
  豁免它是工程惯例。若担心豁免被滥用,本 design 把豁免名单具体到行号,review 时一眼可数。
- **不引入 `pytest-cov` 插件**:`coverage` 直接跑同样能拿到报告,少一个依赖;
  CI 也好接(`coverage run` 是标准命令)。

## 风险

1. **测试可能锁死不该锁的细节**(错误消息文案、JSON key 顺序、行号)。
   - 缓解:断言行为(状态码 / 关键字段存在),不断言精确字符串;`assert "operator" in body`
     而非 `assert body == "operator must be a string"`。
2. **豁免名单膨胀**:实施中可能想给某个真正业务路径加豁免「省事」。
   - 缓解:design.md 已把豁免名单固化;实施时新增豁免必须在 tasks.md 写一条理由,
     review 时单独看。
3. **catalog 测试涉及网络 monkeypatch**,跨 Python 版本对 urllib 内部接口可能有差异。
   - 缓解:patch `server.app._fetch_catalog` 整个函数级别,而非 `urllib.request.urlopen` 底层。

## 待决项

1. **配置写哪**:`pyproject.toml`(项目无该文件,需新建)vs `.coveragerc`(新增单独文件)。
   倾向 `pyproject.toml`,因为后续若要加 `[tool.pytest.ini_options]` / `[tool.ruff]` 可一并放;
   但若用户希望最小侵入,改 `.coveragerc`。**实施时按用户偏好选择,默认 `pyproject.toml`**。
2. **CI 是否加覆盖率门槛**:`coverage report --fail-under=95` 加进 `.github/workflows/*.yml` 的
   pytest 步骤。本变更**默认不改 CI**,仅本地命令文档化;若用户希望守门,加一条 task。
