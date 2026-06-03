"""TATP v0.1 协议契约测试。覆盖 PROTOCOL.md 的关键规则与 ADR-0011~0014。

固化自开发期的 TestClient 冒烟检查,作为 CI 的回归保护。
"""
from conftest import ev


# ---- 核心字段校验 ----------------------------------------------------------
def test_missing_required_fields_400(client):
    r = client.post("/v1/events", json={"operator": "alice"})
    assert r.status_code == 400


def test_minimal_event_logged(client):
    r = ev(client)
    assert r.status_code == 200 and r.json()["logged"] is True


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
