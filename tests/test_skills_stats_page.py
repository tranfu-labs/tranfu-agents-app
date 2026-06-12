from datetime import datetime, timezone, timedelta

from conftest import ev


CATALOG = [
    {"name": "alpha", "type": "own", "description": "company skill"},
    {"name": "idle-own", "type": "own", "description": "installed but unused"},
    {"name": "meta-tool", "type": "meta", "description": "company meta skill"},
    {"name": "beta", "type": "external", "description": "external catalog skill"},
]


def _set_catalog(app_mod, skills=CATALOG):
    with app_mod.db() as conn:
        app_mod._save_catalog_cache(
            conn,
            {"version": 1, "generated_at": "2026-06-12T00:00:00Z", "skills": skills},
            "2026-06-12T00:00:00+00:00",
        )
        conn.commit()


def _clear_catalog(app_mod, error=None):
    with app_mod.db() as conn:
        conn.execute("DELETE FROM catalog_cache")
        conn.commit()
    with app_mod._catalog_lock:
        app_mod._catalog_state.update({"items": None, "fetched_at": None, "error": error, "last_attempt": None})


def _set_skill_day(app_mod, session_id, skill, days_ago, mode="used"):
    day = (datetime.now(timezone.utc).date() - timedelta(days=days_ago)).isoformat()
    first_seen = f"{day}T12:00:00+00:00"
    with app_mod.db() as conn:
        conn.execute("""UPDATE skill_uses SET day=?, first_seen=?
          WHERE session_id=? AND skill=? AND mode=?""",
          (day, first_seen, session_id, skill, mode))
        conn.commit()
    return day


def _seed_skill_stats(client, app_mod):
    _set_catalog(app_mod)
    ev(client, operator="alice", runtime="codex", session_id="a-old", skill="alpha", current_step="1")
    ev(client, operator="alice", runtime="codex", session_id="a-new", skill="alpha", current_step="2")
    ev(client, operator="bob", runtime="claude-code", session_id="b-new", skill="alpha", current_step="3")
    ev(client, operator="chen", runtime="hermes", session_id="c-new", skill="beta", current_step="4")
    ev(client, operator="dan", runtime="open-claw", session_id="e-new", skill="alpha",
       skill_mode="equipped", current_step="5")
    ev(client, operator="zoe", runtime="codex", agent="code", session_id="profile",
       current_step="profile", skills={"local": [{"name": "alpha"}, {"name": "idle-own"}]})
    days = {
        "old": _set_skill_day(app_mod, "a-old", "alpha", 31),
        "used": _set_skill_day(app_mod, "a-new", "alpha", 5),
        "used_bob": _set_skill_day(app_mod, "b-new", "alpha", 5),
        "beta": _set_skill_day(app_mod, "c-new", "beta", 1),
        "equipped": _set_skill_day(app_mod, "e-new", "alpha", 1, mode="equipped"),
    }
    return days


def test_catalog_sync_success_then_failure_marks_old_cache_stale(client, app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "_fetch_catalog", lambda: {
        "version": 1,
        "generated_at": "2026-06-12T00:00:00Z",
        "skills": [{"name": "alpha", "type": "own", "description": ""}],
    })
    assert app_mod.sync_catalog_once() is True
    assert client.get("/api/skills").json()["catalog"]["available"] is True

    def fail():
        raise RuntimeError("network down")

    monkeypatch.setattr(app_mod, "_fetch_catalog", fail)
    assert app_mod.sync_catalog_once() is False
    data = client.get("/api/skills").json()
    assert data["catalog"]["stale"] is True
    assert data["funnel"]["available"] is True


def test_skills_overview_used_only_table_daily_and_funnel(client, app_mod):
    days = _seed_skill_stats(client, app_mod)

    data = client.get("/api/skills?days=7").json()
    assert data["catalog"]["available"] is True
    alpha = next(r for r in data["table"] if r["name"] == "alpha")
    assert alpha["source"] == "own"
    assert alpha["sessions_7d"] == 2
    assert alpha["sessions_30d"] == 2
    assert alpha["sessions_total"] == 3
    assert alpha["users_30d"] == 2
    assert alpha["runtime_counts"] == {"claude-code": 1, "codex": 2}

    beta = next(r for r in data["table"] if r["name"] == "beta")
    assert beta["source"] == "external"
    assert all(r["skill"] != "alpha" or r["runtime"] != "open-claw" for r in data["daily"])
    assert sum(r["sessions"] for r in data["daily"] if r["skill"] == "alpha") == 2
    assert {r["day"] for r in data["daily"] if r["skill"] == "alpha"} == {days["used"]}

    all_days = client.get("/api/skills?days=0").json()
    assert sum(r["sessions"] for r in all_days["daily"] if r["skill"] == "alpha") == 3
    assert {x["name"] for x in data["funnel"]["catalog"]} == {"alpha", "idle-own", "meta-tool"}
    assert {x["name"] for x in data["funnel"]["installed"]} == {"alpha", "idle-own"}
    assert {x["name"] for x in data["funnel"]["used_30d"]} == {"alpha"}
    assert {x["name"] for x in data["funnel"]["idle"]} == {"idle-own"}


def test_skills_overview_empty_when_catalog_unavailable(client, app_mod):
    _clear_catalog(app_mod, error="catalog unreachable")
    data = client.get("/api/skills").json()
    assert data["catalog"]["available"] is False
    assert data["catalog"]["stale"] is True
    assert data["funnel"] == {
        "available": False,
        "catalog": [],
        "installed": [],
        "used_30d": [],
        "idle": [],
    }


def test_skill_detail_keeps_used_and_equipped_separate(client, app_mod):
    days = _seed_skill_stats(client, app_mod)
    data = client.get("/api/skill/alpha").json()
    assert data["source"] == "own"
    assert data["metrics"]["sessions_total"] == 3
    assert data["metrics"]["sessions_30d"] == 2
    assert data["metrics"]["equipped_total"] == 1
    assert data["metrics"]["equipped_30d"] == 1

    daily = {r["day"]: r for r in data["daily"]}
    assert daily[days["used"]]["used"] == 2
    assert daily[days["equipped"]]["used"] == 0
    assert daily[days["equipped"]]["equipped"] == 1
    runtime = {r["runtime"]: r for r in data["runtime"]}
    assert runtime["codex"]["used"] == 2
    assert runtime["open-claw"]["equipped"] == 1
    assert any(r["mode"] == "equipped" and r["session_id"] == "e-new" for r in data["records"])


def test_skill_detail_unknown_404(client):
    assert client.get("/api/skill/nope").status_code == 404


def test_skills_overview_rejects_invalid_days(client):
    assert client.get("/api/skills?days=13").status_code == 400
