"""admin 清理域:/api/admin/inventory 各分支(profile-only / skill-only / active /
needle / pagination)。对应 server/app.py 的 _admin_inventory。
由 add-server-app-test-baseline 引入。
"""
from contextlib import closing
from conftest import ev

ADMIN_HEADERS = {"X-TF-Admin-Key": "adminkey"}


def _enable_admin(app_mod):
    app_mod.ADMIN_KEY = "adminkey"


def _inv(client, **q):
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    url = "/api/admin/inventory" + ("?" + qs if qs else "")
    return client.get(url, headers=ADMIN_HEADERS)


def test_inventory_empty_returns_four_empty_lists(client, app_mod):
    _enable_admin(app_mod)
    r = _inv(client)
    assert r.status_code == 200
    j = r.json()
    for k in ("operators", "identities", "sessions", "skills"):
        assert j[k] == []


def test_inventory_basic_event_populates_three_tables(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="s1", current_step="x")
    j = _inv(client).json()
    assert any(o["operator"] == "alice" for o in j["operators"])
    assert any(i["operator"] == "alice" for i in j["identities"])
    assert any(s["session_id"] == "s1" for s in j["sessions"])


def test_inventory_marks_active_session(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="alive", current_step="x")  # running
    j = _inv(client).json()
    op = next(o for o in j["operators"] if o["operator"] == "alice")
    sess = next(s for s in j["sessions"] if s["session_id"] == "alive")
    assert op["active"] is True
    assert sess["active"] is True


def test_inventory_active_skill_flag(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="alive2", current_step="x", skill="hot-skill")
    j = _inv(client).json()
    sk = next(s for s in j["skills"] if s["skill"] == "hot-skill")
    assert sk["active"] is True


def test_inventory_profile_only_identity(client, app_mod):
    _enable_admin(app_mod)
    # 上报含 profile 的事件 → profiles 表有一行
    ev(client, session_id="prof", current_step="x", agent="anya",
       skills={"local": [{"name": "k"}]})
    # 删 events 表把 session 干掉,但 profiles 留着 → 仅 profile 的 identity
    with closing(app_mod.db()) as conn:
        conn.execute("DELETE FROM events")
        conn.commit()
    j = _inv(client).json()
    # profiles 仍贡献 identity
    assert any(i["agent"] == "anya" or i["operator"] for i in j["identities"])


def test_inventory_skill_only_session(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="skill-only", current_step="x", skill="k1")
    # 删 events,留 skill_uses
    with closing(app_mod.db()) as conn:
        conn.execute("DELETE FROM events WHERE session_id='skill-only'")
        conn.commit()
    j = _inv(client).json()
    assert any(s["session_id"] == "skill-only" for s in j["sessions"])


def test_inventory_runtime_only_identity_name(client, app_mod):
    _enable_admin(app_mod)
    # 不传 agent → identity 名退化为 runtime
    ev(client, session_id="s9", current_step="x")  # agent 默认 None
    j = _inv(client).json()
    ident = next(i for i in j["identities"] if i["operator"] == "alice")
    # name 形如 "alice / codex"(runtime 兜底)
    assert "codex" in ident["name"]


def test_inventory_needle_case_insensitive(client, app_mod):
    _enable_admin(app_mod)
    ev(client, session_id="needle-1", current_step="x")
    j = _inv(client, q="ALICE").json()
    assert any(o["operator"] == "alice" for o in j["operators"])


def test_inventory_pagination_limit_offset(client, app_mod):
    _enable_admin(app_mod)
    for i in range(3):
        ev(client, operator=f"op{i}", session_id=f"s{i}", current_step="x")
    j = _inv(client, limit=1).json()
    assert len(j["operators"]) == 1
    j2 = _inv(client, offset=999).json()
    assert j2["operators"] == []


def test_inventory_includes_operator_identities_count(client, app_mod):
    _enable_admin(app_mod)
    ev(client, agent="a", session_id="i1", current_step="x")
    ev(client, agent="b", session_id="i2", current_step="x")
    j = _inv(client).json()
    op = next(o for o in j["operators"] if o["operator"] == "alice")
    assert op["identities"] >= 2


def test_inventory_requires_admin_key(client, app_mod):
    _enable_admin(app_mod)
    assert client.get("/api/admin/inventory").status_code == 403
