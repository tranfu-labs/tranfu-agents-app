# 任务:add-server-app-test-baseline

## 工具与配置
- [ ] `server/requirements.txt`(或新增 dev 段)追加 `coverage>=7.0`。
- [ ] 新增 `pyproject.toml`(或 `.coveragerc`,见 design.md 待决项 1)写入:
      `[tool.coverage.run] source = ["server/app.py"]` 与
      `[tool.coverage.report] exclude_lines = ["pragma: no cover", "if __name__ == .__main__.:"]`。
- [ ] 在 `AGENTS.md` 的「修改后检查」节追加:
      `python -m coverage run --source=server -m pytest && python -m coverage report --include='server/app.py'`
      并写明覆盖率阈值 95%。

## 豁免标记(`# pragma: no cover`)
- [ ] 给 `server/app.py` 的下列行加 `# pragma: no cover`(具体行号以本变更基线为准):
      2647-2648(`__main__`)、89-90(弱钥告警)、670-672 / 677-683 / 687(catalog 后台线程组)、
      327(老 schema ALTER)、449-452(`_rate_prune`)、2584-2585(SPA index FileNotFoundError)、
      以及 design.md 列出的所有 `except Exception: pass` 防御性兜底行。

## 测试文件(按 spec 域分组)

### `tests/test_catalog.py`(新建)
- [ ] `test_parse_payload_accepts_bytes_and_str`
- [ ] `test_parse_payload_dedupes_by_name_and_drops_missing_name`
- [ ] `test_parse_payload_falls_back_external_for_unknown_type`
- [ ] `test_parse_payload_raises_on_non_list_skills`
- [ ] `test_fetch_catalog_success`(monkeypatch urllib)
- [ ] `test_fetch_catalog_timeout_records_error`
- [ ] `test_fetch_catalog_http_error_records_error`
- [ ] `test_save_and_load_catalog_cache_roundtrip`
- [ ] `test_catalog_context_returns_items_byname_meta`

### `tests/test_admin_targets.py`(新建)
- [ ] `_validate_targets` 合法分支 6 个:`session_ids` / `skill` / `operator` / `operator+agent` /
      `operator+runtime` / `before_day+operator`
- [ ] `_validate_targets` 非法分支:`targets=[]` / `target` 非 dict / 无 kind / 多 kind /
      `session_ids` 非数组 / 非字符串元素 / 空数组 / `before_day` 不是 10 字符 / 缺 operator /
      `skill` 是空串
- [ ] `_session_ids_by_operator`:无 agent/无 runtime / 带 agent / 带 runtime / 同时带;
      不带 agent 时通过 `skill_uses` 来源的 session 也被纳入
- [ ] `_session_ids_before_day`:同上 + 严格 `<` 日期边界
- [ ] `_restore_admin_batch` 404 / 409 / 成功 三态,成功路径校验 `admin_audit` 写一条
- [ ] `DELETE /v1/events` 旧路径:既无 sids 又无 operator → 400;sids 含非字符串 → 400;
      operator 路径活跃会话无 force → 400;rows 超 `ADMIN_MAX_ROWS` 无 `confirm_count` → 400

### `tests/test_admin_inventory.py`(新建)
- [ ] 空库:四类返回均为 []
- [ ] 单 operator 单 session:四类各一行
- [ ] profile-only identity(无 events 仅 profiles)出现在 `identities`
- [ ] 有 `skill_uses` 无 `events` 的 session 出现在 `sessions`
- [ ] runtime-only operator(无 agent 字段)在 `identities.name` 退化为 runtime
- [ ] `q` 大小写不敏感;命中字段串包含匹配
- [ ] `limit/offset` 边界:`limit=1` / `offset >= 总数`
- [ ] active 标记跨表传染:活跃 session → operator/identity/skill 同时 `active=true`

### `tests/test_board.py`(新建)
- [ ] `metrics.blocked` 计数
- [ ] `metrics.auto_rate`:`saw_wait=True` 的 done 不计入;`saw_wait=False` 的 done 计入
- [ ] `metrics` 跨天 active(`started` 23:59 + `done` 次日 00:01)→ 两个 day 桶
- [ ] `_snapshot.card`:心跳过期 `running` → `idle`
- [ ] `_snapshot.card`:`input`/`output` > 4000 截断
- [ ] `_snapshot.card`:`quality.reuse` 注入
- [ ] `GET /api/agent/{key}` 404 + 成功
- [ ] `GET /api/operator/{name}` 404 + 成功
- [ ] `GET /api/skill/{name}` 404 + 成功

### `tests/test_onboarding.py`(新建)
- [ ] `GET /shims/../app.py` → 404(目录穿越拒绝)
- [ ] `GET /shims/tf_hook.py` → 200 非空(主 shim 文件)
- [ ] `GET /shims/wrapper/tf-run` → 200 非空(wrapper 子目录)
- [ ] `GET /shims/manifest` → 含 `schema/version/files`,每个 file 有 `target` 与 `sha256`
- [ ] `GET /install.sh` 存在态 200;mock 缺失态 404
- [ ] `GET /healthz` → `text/plain` body=`ok`,且未触发 DB 连接

### `tests/test_protocol.py`(扩展)
- [ ] enroll 限流:连续 `TF_ADMIN_RATE_MAX+1` 次错钥 → 429 + `Retry-After`
- [ ] ingest:有 skill 缺 session_id → `{ok: true, logged: false, skill_ignored: true}`
- [ ] ingest:body > `MAX_BODY` → 413

## conftest 扩展(按需)
- [ ] 若 catalog 测试需要,在 `tests/conftest.py` 新增 `fake_catalog` 夹具(替换 `_fetch_catalog`)。
- [ ] 若 admin 测试需要,新增 `admin_client` 夹具(已设 `TF_ADMIN_KEY`)。

## 验收
- [ ] `python -m coverage run --source=server -m pytest -q` 全绿。
- [ ] `python -m coverage report --include='server/app.py'` 输出 ≥ 95%。
- [ ] `python -m coverage report --include='server/app.py' --skip-covered --show-missing` 列出的
      missing 行 100% 在 design.md 豁免名单内。

## AI 验证流程
- [ ] 在本地跑上述三条命令,把输出粘到 PR 描述。
- [ ] 让另一个 agent 抽 3-5 条新测试,确认每条断言的是「行为」而非「字面错误消息」。

## 文档与归档
- [ ] 实施完毕、覆盖率达标后,按 `openspec/changes/AGENTS.md` 的「归档」节执行:
      ① 本目录移入 `archive/<YYYY-MM-DD>-add-server-app-test-baseline/`;
      ② 本变更**无 spec-delta**(测试是事实源的锁定工具,不是行为本身);
      ③ 本变更**无 wireframes.md**,跳过线框图回流。
- [ ] `git commit`(消息引用本 change-id);有 remote 时**问用户**是否 push,不擅自推。
- [ ] 归档完成后,开启下一个 change `refactor-server-app-by-domain` 的实施。
