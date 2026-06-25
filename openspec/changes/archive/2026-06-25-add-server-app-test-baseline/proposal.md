# 变更提案:add-server-app-test-baseline(为重构铺测试地基)

- 状态:Proposed
- 关联:`server/app.py`、`tests/test_*`、后续 change `refactor-server-app-by-domain`(本变更是它的前置依赖)
- 触发事件:2026-06-25 用户复审 server/app.py 发现单文件 2648 行,需按 spec 域(admin/board/ingest/onboarding)
  拆分。重构启动前先用「行为锁定测试」(characterization tests)冻结现有行为,作为拆分的契约保证。

## 背景 / 问题
`server/app.py` 现有 1456 个可测语句,基线行覆盖 86%(210 行 missing),分布在:

1. **catalog 取/存/解析**(`_fetch_catalog`、`_parse_catalog_payload`、`_load_catalog_cache`)缺测试。
2. **admin 清理算子**(`_validate_targets` 多种 target kind 的错误分支、`_session_ids_by_operator/before_day`
   的 agent+runtime 联合查询、`_restore_admin_batch` 三态、`DELETE /v1/events` 旧路径)只有主路径覆盖。
3. **admin_inventory** 的 profile-only identity、有 skill_uses 无 event 的 session、runtime-only operator、
   active 标记跨表传染等分支未触达。
4. **board 域**(`metrics` 的 `blocked/auto_rate` 分支、`card` 心跳过期翻 idle、`/api/agent`/`/api/operator`/
   `/api/skill` 的 404 路径)缺端点级测试。
5. **onboarding 域**(`shim_file` 目录穿越拒绝)缺安全测试。
6. **enroll 限流命中、ingest 带 skill 无 session_id 的「忽略」路径** 没有断言。

下一个 change(`refactor-server-app-by-domain`)要把 2648 行按 spec 域拆成 ~12 个文件,**任何拆分都需要
强行为契约才能确保零回归**——当前 86% 不够,需要先把覆盖率推到 ≥ 95%。

## 目标
- `coverage report --include='server/app.py'` 行覆盖 ≥ **95%**。
- 全部 pytest 用例(现有 155 + 新增约 35)绿。
- 剩下未覆盖的行 100% 在豁免名单内(`# pragma: no cover` 标记)。
- 测试文件按 spec 域分组(`test_catalog.py` / `test_admin_targets.py` / `test_admin_inventory.py` /
  `test_board.py` / `test_onboarding.py`),与下个 change 的目录拆分预先对齐,后续不需要挪测试。

## 非目标
- 不动 `server/app.py` 任何业务代码(只在豁免名单的行上加 `# pragma: no cover` 注释)。
- 不拆分文件(那是下一个 change)。
- 不优化 CPU / 缓存 / 写路径(完全独立的工作)。
- 不追求分支覆盖(branch coverage)95%,仅行覆盖 95%。
- 不扩大到 `shims/` 或 `frontend/`,本变更只锁 `server/app.py` 的行为。

## 方案概述(详见 design.md)
1. **装 coverage、加 pytest 配置**:`coverage` 加入 `server/requirements.txt`(dev 段);
   在 `pyproject.toml`(或新建 `.coveragerc`)写入 source、omit、`exclude_lines = pragma: no cover`。
2. **补 6 组测试**(预先按 Change B 的拆分边界分文件),覆盖 catalog / admin targets /
   admin inventory / board endpoints / onboarding / 现有 protocol 的剩余分支。
3. **加豁免标记**:对 `__main__` 块、catalog 后台线程、`except Exception: pass` 防御性兜底、
   FileNotFoundError 兜底、启动期弱钥告警等约 60 行加 `# pragma: no cover`。
4. **验收门槛**:`coverage report --include='server/app.py'` ≥ 95%。

## 影响
- 新增测试文件 5 个、扩展现有测试文件 1 个;`tests/conftest.py` 可能补 1-2 个夹具(伪 catalog 响应、
  伪 admin actor)。
- `server/app.py` 仅追加 `# pragma: no cover` 行级注释,无业务逻辑变化。
- 新增依赖 `coverage`(开发期);CI workflow 可选择性追加覆盖率门槛(本变更不强制改 CI)。
- 不影响任何对外 API、协议、UI、运维配置。
- **spec 不变**:测试是行为事实源的锁定工具,不是行为本身,故本变更无 `spec-delta`。
