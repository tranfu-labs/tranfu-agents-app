"""TATP v0.1 协议契约测试。覆盖 PROTOCOL.md 的关键规则与 ADR-0011~0014。

固化自开发期的 TestClient 冒烟检查,作为 CI 的回归保护。
"""
from conftest import ev
import hashlib

ADMIN_HEADERS = {"X-TF-Admin-Key": "adminkey"}


# ---- 核心字段校验 ----------------------------------------------------------
def test_missing_required_fields_400(client):
    r = client.post("/v1/events", json={"operator": "alice"})
    assert r.status_code == 400


def test_minimal_event_logged(client):
    r = ev(client)
    assert r.status_code == 200 and r.json()["logged"] is True


def test_serves_install_and_nested_shims(client):
    assert client.get("/install.sh").status_code == 200
    r = client.get("/shims/openclaw/openclaw.plugin.json")
    assert r.status_code == 200
    assert "tranfu-skill-reporter" in r.text


def test_shim_manifest_lists_targets_and_hashes(client):
    r = client.get("/shims/manifest")
    assert r.status_code == 200
    manifest = r.json()
    assert manifest["version"] and manifest["files"]
    by_path = {f["path"]: f for f in manifest["files"]}
    assert by_path["tf_hook.py"]["target"] == "tf_hook.py"
    assert by_path["wrapper/tf-run"]["target"] == "tf-run"
    hook_body = client.get("/shims/tf_hook.py").content
    assert by_path["tf_hook.py"]["sha256"] == hashlib.sha256(hook_body).hexdigest()


def test_shims_directory_traversal_rejected(client):
    assert client.get("/shims/../server/app.py").status_code == 404


def test_spa_deep_links_do_not_swallow_system_routes(client):
    for path in ["/", "/agents", "/agent/alice%3A%3Acode", "/skills?win=30&rt=codex", "/skill/%E5%93%81%E7%89%8C"]:
        r = client.get(path)
        assert r.status_code == 200
        assert "TRANFU//AGENTS" in r.text

    assert client.get("/missing-client-route").status_code == 200
    assert client.get("/api/nope").status_code == 404
    assert client.get("/v1/nope").status_code == 404
    assert client.get("/assets/nope.js").status_code == 404
    assert client.get("/install.sh").status_code == 200
    assert client.get("/healthz").text == "ok"
    assert client.get("/llms.txt").status_code == 200
    assert client.get("/robots.txt").status_code == 200


# ---- §4 身份与令牌 (ADR-0011) ---------------------------------------------
def test_enroll_then_verified(client):
    tok = client.post("/v1/enroll", json={"operator": "alice"}).json()["token"]
    assert tok.startswith("ttk_")
    r = ev(client, headers={"X-TF-Token": tok})
    assert r.json()["verified"] is True


def test_token_operator_mismatch_403(client):
    tok = client.post("/v1/enroll", json={"operator": "alice"}).json()["token"]
    # 用 alice 的令牌冒名 bob -> 恒拒,无论是否开强制
    r = ev(client, operator="bob", session_id="s2", headers={"X-TF-Token": tok})
    assert r.status_code == 403


def test_require_token_missing_403(client, app_mod):
    app_mod.REQUIRE_TOKEN = True
    r = ev(client)                       # 强制归因下不带令牌
    assert r.status_code == 403


def test_self_asserted_unverified_when_not_required(client):
    r = ev(client)                       # 未开强制 + 无令牌 -> 接受但未验证
    assert r.status_code == 200 and r.json()["verified"] is False


# ---- §5 读侧鉴权硬闸 (ADR-0012) -------------------------------------------
def test_sensitive_dropped_without_read_auth(client):
    ev(client, status="running", current_step="x", input="secret-prompt")
    cards = client.get("/api/state").json()["sessions"]
    assert not any(c.get("input") for c in cards)


def test_sensitive_kept_with_read_auth(client, app_mod):
    app_mod.READ_AUTH_OK = True
    ev(client, status="running", current_step="y", output="diff-here")
    cards = client.get("/api/state").json()["sessions"]
    assert any(c.get("output") == "diff-here" for c in cards)


# ---- §8 限流 (ADR-0014) ---------------------------------------------------
def test_oversized_body_413(client):
    big = "x" * (300 * 1024)
    r = client.post("/v1/events", json={"operator": "a", "runtime": "r",
                                        "session_id": "s", "status": "running", "task": big})
    assert r.status_code == 413


# ---- §1 blocked 归属 (ADR-0013) -------------------------------------------
def test_blocked_is_live_and_counted(client):
    ev(client, status="blocked", current_step="rate limited")
    cards = client.get("/api/state").json()["sessions"]
    card = next(c for c in cards if c["operator"] == "alice")
    assert card["status"] == "blocked"                  # 存活态,不翻 idle
    assert card["quality"]["blocked"] == 1              # 质量块单列计数


# ---- §6 去重键含 session_id (ADR-0014 修订 ADR-0003) ----------------------
def test_heartbeat_dedup_includes_session(client):
    ev(client, session_id="A", current_step="step")
    r2 = ev(client, session_id="A", current_step="step")   # 同 session 同状态 -> 纯心跳
    assert r2.json().get("heartbeat") is True
    r3 = ev(client, session_id="B", current_step="step")   # 不同 session -> 仍落行,不被吞
    assert r3.json().get("logged") is True


# ---- §1 v 与 parent_session_id 落库 ---------------------------------------
def test_v_and_parent_persisted(client):
    ev(client, session_id="child", parent_session_id="root", current_step="z")
    cards = client.get("/api/state").json()["sessions"]
    card = next(c for c in cards if c["session_id"] == "child")
    assert card["parent_session_id"] == "root"
    assert card["v"] == "0.1"


def test_profile_shim_version_persisted_and_state_exposes_current(client):
    ev(client, session_id="shim1", current_step="profile", shim_version="abc123")
    state = client.get("/api/state").json()
    card = next(c for c in state["sessions"] if c["session_id"] == "shim1")
    assert card["shim_version"] == "abc123"
    assert state["shim"]["version"]


# ---- DELETE /v1/events admin 清理 ------------------------------------------
def test_delete_by_session_id(client, app_mod):
    app_mod.ADMIN_KEY = "adminkey"
    ev(client, session_id="junk1", current_step="x")
    ev(client, session_id="keep1", current_step="x")
    # 活跃会话需 force(遗留端点护栏已与 /api/admin/data 对齐)
    r = client.request("DELETE", "/v1/events", json={"session_id": "junk1", "force": True}, headers=ADMIN_HEADERS)
    assert r.status_code == 200 and r.json()["deleted"] >= 1
    sids = {c["session_id"] for c in client.get("/api/state").json()["sessions"]}
    assert "junk1" not in sids and "keep1" in sids


def test_delete_by_session_ids_list(client, app_mod):
    app_mod.ADMIN_KEY = "adminkey"
    ev(client, session_id="a", current_step="x")
    ev(client, session_id="b", current_step="x")
    r = client.request("DELETE", "/v1/events", json={"session_ids": ["a", "b"], "force": True}, headers=ADMIN_HEADERS)
    assert r.status_code == 200 and r.json()["deleted"] >= 2


def test_delete_by_identity_clears_profile(client, app_mod):
    app_mod.ADMIN_KEY = "adminkey"
    # 一个带 profile 的身份（中文 agent 名，验证 body 传参不受 URL 编码影响）
    ev(client, operator="zoe", runtime="claude-code", agent="赛博测试",
       session_id="s", current_step="x", skills={"local": [{"name": "k"}]})
    r = client.request("DELETE", "/v1/events",
                       json={"operator": "zoe", "agent": "赛博测试", "profile": True, "force": True},
                       headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert r.json()["deleted"] >= 1 and r.json()["cleared_profile"] == 1
    cards = client.get("/api/state").json()["sessions"]
    assert not any(c["operator"] == "zoe" for c in cards)


def test_delete_requires_target_400(client, app_mod):
    app_mod.ADMIN_KEY = "adminkey"
    r = client.request("DELETE", "/v1/events", json={}, headers=ADMIN_HEADERS)
    assert r.status_code == 400


def test_delete_requires_admin_key(client, app_mod):
    app_mod.INGEST_KEY = "secret"
    app_mod.ADMIN_KEY = "adminkey"
    bad = client.request("DELETE", "/v1/events", json={"session_id": "x"},
                         headers={"X-TF-Key": "secret"})
    assert bad.status_code == 403
    ok = client.request("DELETE", "/v1/events", json={"session_id": "x"}, headers=ADMIN_HEADERS)
    assert ok.status_code == 200


# ---- 身份归一化：operator 大小写/空格 + runtime 大小写 合并为一个 Pod ----------
def test_operator_and_runtime_normalized_to_one_card(client):
    ev(client, operator="NEZHA", runtime="Hermes", agent="多儿", session_id="a", current_step="x")
    ev(client, operator=" nezha ", runtime="hermes", agent="多儿", session_id="b", current_step="y")
    cards = client.get("/api/state").json()["sessions"]
    duo = [c for c in cards if c.get("agent") == "多儿"]
    assert len(duo) == 1                                   # 合成一张卡，不再裂成两个
    assert duo[0]["operator"] == "NEZHA"                   # 首次出现的写法作为展示
    assert duo[0]["runtime"] == "hermes"                   # runtime 统一小写
    assert client.get("/api/state").json()["totals"]["operators"] == 1


def test_enroll_token_verifies_across_operator_casing(client):
    tok = client.post("/v1/enroll", json={"operator": "NEZHA"}).json()["token"]
    # 用不同大小写上报，仍应被验证为同一 operator
    r = ev(client, operator="nezha", session_id="s9", headers={"X-TF-Token": tok})
    assert r.json()["verified"] is True
