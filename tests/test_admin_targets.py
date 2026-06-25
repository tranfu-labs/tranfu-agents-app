"""admin 清理域:targets 解析、清理算子、legacy DELETE /v1/events 旧路径。
对应 server/app.py 的 _validate_targets / _session_ids_by_operator /
_session_ids_before_day / _restore_admin_batch / _maybe_prune_trash 与 DELETE /v1/events。
由 add-server-app-test-baseline 引入。
"""
from contextlib import closing
from conftest import ev

ADMIN_HEADERS = {"X-TF-Admin-Key": "adminkey"}


def _enable_admin(app_mod):
    app_mod.ADMIN_KEY = "adminkey"


def _preview(client, body):
    return client.post("/api/admin/preview", json=body, headers=ADMIN_HEADERS)


# ---- _validate_targets:合法的 6 种 target kind ---------------------------
def test_targets_valid_kinds_each_resolve(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="s1", current_step="x")
    ev(client, operator="bob", session_id="s2", current_step="x")
    # 让 admin preview 不被活跃会话拦下:让 sessions 老化(用 done 状态)
    ev(client, session_id="s1", status="done")
    ev(client, operator="bob", session_id="s2", status="done")
    for tgt in (
        {"session_ids": ["s1"]},
        {"operator": "alice"},
        {"operator": "alice", "agent": "codex"},
        {"operator": "alice", "runtime": "codex"},
        {"before_day": "2099-12-31", "operator": "alice"},
    ):
        r = _preview(client, {"targets": [tgt]})
        assert r.status_code == 200, (tgt, r.text)


def test_targets_skill_kind_resolves(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="s1", current_step="x", skill="my-skill")
    r = _preview(client, {"targets": [{"skill": "my-skill"}]})
    assert r.status_code == 200
    assert r.json()["counts"]["skill_uses"] >= 1


# ---- _validate_targets:各种非法形态 --------------------------------------
def test_targets_empty_array_400(client, app_mod):
    _enable_admin(app_mod)
    assert _preview(client, {"targets": []}).status_code == 400


def test_targets_non_dict_element_400(client, app_mod):
    _enable_admin(app_mod)
    assert _preview(client, {"targets": ["oops"]}).status_code == 400


def test_targets_no_kind_400(client, app_mod):
    _enable_admin(app_mod)
    assert _preview(client, {"targets": [{}]}).status_code == 400


def test_targets_multi_kind_400(client, app_mod):
    _enable_admin(app_mod)
    r = _preview(client, {"targets": [{"session_ids": ["a"], "operator": "x"}]})
    assert r.status_code == 400


def test_targets_session_ids_not_array_400(client, app_mod):
    # session_ids: str → 服务端会规范化为 [str](合法);要触发 400 需要 含非字符串元素 / 非数组非字符串
    _enable_admin(app_mod)
    assert _preview(client, {"targets": [{"session_ids": [123]}]}).status_code == 400
    assert _preview(client, {"targets": [{"session_ids": 5}]}).status_code == 400


def test_targets_session_ids_empty_array_is_legal_with_zero_effects(client, app_mod):
    # 空数组合法(校验通过),counts 为 0(没东西可清)
    _enable_admin(app_mod)
    r = _preview(client, {"targets": [{"session_ids": []}]})
    assert r.status_code == 200
    assert r.json()["total_rows"] == 0


def test_targets_before_day_invalid_400(client, app_mod):
    _enable_admin(app_mod)
    # before_day 必须是 10 字符
    assert _preview(client, {"targets": [{"before_day": "bad", "operator": "x"}]}).status_code == 400
    # before_day 必须配 operator
    assert _preview(client, {"targets": [{"before_day": "2099-12-31"}]}).status_code == 400


def test_targets_skill_empty_string_400(client, app_mod):
    _enable_admin(app_mod)
    assert _preview(client, {"targets": [{"skill": "   "}]}).status_code == 400


def test_targets_operator_must_be_string_400(client, app_mod):
    _enable_admin(app_mod)
    assert _preview(client, {"targets": [{"operator": 12345}]}).status_code == 400


# ---- _session_ids_by_operator / _session_ids_before_day 联合查询 --------
def test_session_ids_by_operator_with_agent_and_runtime(client, app_mod):
    _enable_admin(app_mod)
    ev(client, agent="codex-a", session_id="A1", current_step="x")
    ev(client, agent="codex-b", session_id="B1", current_step="x")
    ev(client, agent="codex-a", session_id="A1", status="done")
    ev(client, agent="codex-b", session_id="B1", status="done")
    # 按 agent 收口
    r = _preview(client, {"targets": [{"operator": "alice", "agent": "codex-a"}]})
    sids = {s["session_id"] for s in r.json()["active_sessions"]}
    # 已 done 不在 active_sessions;但 counts 反映 events 数
    assert r.json()["counts"]["events"] >= 1
    # 按 runtime 收口
    r2 = _preview(client, {"targets": [{"operator": "alice", "runtime": "codex"}]})
    assert r2.status_code == 200


def test_session_ids_before_day_strict_less_than(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="old", current_step="x")
    ev(client, session_id="old", status="done")
    # before_day 未来 → 全选;过去 → 不选(strict <)
    fut = _preview(client, {"targets": [{"before_day": "2099-12-31", "operator": "alice"}]})
    past = _preview(client, {"targets": [{"before_day": "2000-01-01", "operator": "alice"}]})
    assert fut.json()["counts"]["events"] >= 1
    assert past.json()["counts"]["events"] == 0


def test_before_day_with_agent_and_runtime_filters(client, app_mod):
    _enable_admin(app_mod)
    ev(client, agent="x", session_id="s1", current_step="step")
    ev(client, agent="x", session_id="s1", status="done")
    r = _preview(client, {"targets": [{
        "before_day": "2099-12-31", "operator": "alice",
        "agent": "x", "runtime": "codex"}]})
    assert r.status_code == 200


# ---- skill_uses 来源的 session 也被纳入 -----------------------------------
def test_operator_target_picks_up_skill_uses_session(client, app_mod):
    _enable_admin(app_mod)
    # 一个只通过 skill 报上来、events 已删的会话
    ev(client, session_id="orphan", current_step="x", skill="k1")
    with closing(app_mod.db()) as conn:
        conn.execute("DELETE FROM events WHERE session_id='orphan'")
        conn.commit()
    r = _preview(client, {"targets": [{"operator": "alice"}]})
    # skill_uses 表里还有 orphan
    assert r.json()["counts"]["skill_uses"] >= 1


# ---- admin restore 三态 --------------------------------------------------
def test_restore_unknown_batch_404(client, app_mod):
    _enable_admin(app_mod)
    r = client.post("/api/admin/restore", json={"batch_id": "nope"}, headers=ADMIN_HEADERS)
    assert r.status_code == 404


def test_restore_missing_batch_id_400(client, app_mod):
    _enable_admin(app_mod)
    r = client.post("/api/admin/restore", json={}, headers=ADMIN_HEADERS)
    assert r.status_code == 400


def test_restore_already_restored_409(client, app_mod):
    _enable_admin(app_mod)
    # 造一次删除拿 batch_id
    ev(client, session_id="del", current_step="x")
    ev(client, session_id="del", status="done")
    r = client.request("DELETE", "/v1/events", json={"session_id": "del", "force": True},
                       headers=ADMIN_HEADERS)
    batch = r.json()["batch_id"]
    r1 = client.post("/api/admin/restore", json={"batch_id": batch}, headers=ADMIN_HEADERS)
    assert r1.status_code == 200
    r2 = client.post("/api/admin/restore", json={"batch_id": batch}, headers=ADMIN_HEADERS)
    assert r2.status_code == 409


# ---- DELETE /v1/events 旧路径校验 ----------------------------------------
def test_legacy_delete_active_session_requires_force(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="alive", current_step="x")  # 仍 running
    r = client.request("DELETE", "/v1/events", json={"session_id": "alive"},
                       headers=ADMIN_HEADERS)
    assert r.status_code == 400


def test_legacy_delete_session_ids_non_string_400(client, app_mod):
    _enable_admin(app_mod)
    r = client.request("DELETE", "/v1/events", json={"session_ids": [123]},
                       headers=ADMIN_HEADERS)
    assert r.status_code == 400


def test_legacy_delete_invalid_body_400(client, app_mod):
    _enable_admin(app_mod)
    # body 非 dict
    r = client.request("DELETE", "/v1/events", content=b"[]",
                       headers={**ADMIN_HEADERS, "Content-Type": "application/json"})
    assert r.status_code == 400
    # body 非 JSON
    r = client.request("DELETE", "/v1/events", content=b"not-json",
                       headers={**ADMIN_HEADERS, "Content-Type": "application/json"})
    assert r.status_code == 400


def test_legacy_delete_confirm_count_required_for_large(client, app_mod):
    _enable_admin(app_mod)
    app_mod.ADMIN_MAX_ROWS = 1  # 强制超过阈值
    ev(client, session_id="a", current_step="x")
    ev(client, session_id="a", status="done")
    ev(client, session_id="b", current_step="x")
    ev(client, session_id="b", status="done")
    r = client.request("DELETE", "/v1/events",
                       json={"operator": "alice", "force": True},
                       headers=ADMIN_HEADERS)
    assert r.status_code == 400  # 缺 confirm_count


# ---- /api/admin/data 校验 preview_token + requires_force/confirm --------
def test_data_endpoint_requires_preview_token_409(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="x", current_step="x")
    ev(client, session_id="x", status="done")
    r = client.request("DELETE", "/api/admin/data",
                       json={"targets": [{"session_ids": ["x"]}],
                             "preview_token": "wrong"},
                       headers=ADMIN_HEADERS)
    assert r.status_code == 409


def test_data_endpoint_full_flow(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="full", current_step="x")
    ev(client, session_id="full", status="done")
    pr = _preview(client, {"targets": [{"session_ids": ["full"]}]})
    tok = pr.json()["preview_token"]
    r = client.request("DELETE", "/api/admin/data",
                       json={"targets": [{"session_ids": ["full"]}],
                             "preview_token": tok},
                       headers=ADMIN_HEADERS)
    assert r.status_code == 200


def test_data_endpoint_active_session_requires_force(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="alive2", current_step="x")  # 仍 running
    pr = _preview(client, {"targets": [{"session_ids": ["alive2"]}]})
    tok = pr.json()["preview_token"]
    r = client.request("DELETE", "/api/admin/data",
                       json={"targets": [{"session_ids": ["alive2"]}],
                             "preview_token": tok},
                       headers=ADMIN_HEADERS)
    assert r.status_code == 400  # active sessions require force=true


def test_data_endpoint_confirm_count_branch(client, app_mod):
    _enable_admin(app_mod)
    app_mod.ADMIN_MAX_ROWS = 1
    ev(client, session_id="m1", current_step="x"); ev(client, session_id="m1", status="done")
    ev(client, session_id="m2", current_step="x"); ev(client, session_id="m2", status="done")
    pr = _preview(client, {"targets": [{"operator": "alice"}]})
    tok = pr.json()["preview_token"]
    total = pr.json()["total_rows"]
    bad = client.request("DELETE", "/api/admin/data",
                         json={"targets": [{"operator": "alice"}],
                               "preview_token": tok, "confirm_count": -1},
                         headers=ADMIN_HEADERS)
    assert bad.status_code == 400
    ok = client.request("DELETE", "/api/admin/data",
                        json={"targets": [{"operator": "alice"}],
                              "preview_token": tok, "confirm_count": total},
                        headers=ADMIN_HEADERS)
    assert ok.status_code == 200


# ---- /api/admin/trash + 软删除可见性 -------------------------------------
def test_trash_lists_recent_batches(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="trash1", current_step="x"); ev(client, session_id="trash1", status="done")
    client.request("DELETE", "/v1/events", json={"session_id": "trash1", "force": True},
                   headers=ADMIN_HEADERS)
    r = client.get("/api/admin/trash", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert any(b["counts"]["events"] >= 1 for b in r.json()["trash"])


# ---- 兼容路径 + cascade_children -----------------------------------------
def test_cascade_children_expands_descendant_sessions(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="root", current_step="x")
    ev(client, session_id="root", status="done")
    ev(client, session_id="child", parent_session_id="root", current_step="x")
    ev(client, session_id="child", status="done")
    pr = _preview(client, {"targets": [{"session_ids": ["root"]}],
                           "cascade_children": True})
    sids = pr.json()["counts"]
    # 触发 _expand_child_sessions 路径(L1186 附近)
    assert pr.status_code == 200
