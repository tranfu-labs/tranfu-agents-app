from datetime import datetime, timezone, timedelta

import pytest

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
    day = (app_mod.stats_today() - timedelta(days=days_ago)).isoformat()
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
    assert data["today"] == app_mod.stats_day()
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

    assert {x["name"] for x in data["funnel"]["catalog"]} == {"alpha", "idle-own", "meta-tool"}
    assert {x["name"] for x in data["funnel"]["installed"]} == {"alpha", "idle-own"}
    assert {x["name"] for x in data["funnel"]["used_30d"]} == {"alpha"}
    assert {x["name"] for x in data["funnel"]["idle"]} == {"idle-own"}


def test_skills_overview_operator_view_used_only_and_windowed_daily(client, app_mod):
    days = _seed_skill_stats(client, app_mod)
    with app_mod.db() as conn:
        conn.execute("""INSERT INTO skill_uses(session_id,skill,mode,operator,runtime,day,first_seen)
          VALUES('blank-op','alpha','used','','codex',?,?)""",
          (days["used"], f"{days['used']}T12:00:00+00:00"))
        conn.commit()

    data7 = client.get("/api/skills?days=7").json()
    operators = {r["operator"]: r for r in data7["operator_table"]}
    assert set(operators) == {"alice", "bob", "chen"}
    assert operators["alice"]["sessions_7d"] == 1
    assert operators["alice"]["sessions_30d"] == 1
    assert operators["alice"]["sessions_total"] == 2
    assert operators["alice"]["skill_count"] == 1
    assert operators["alice"]["session_count"] == 2
    assert operators["alice"]["runtime_counts"] == {"codex": 2}
    assert operators["alice"]["source_counts"] == {"own": 2}
    assert [r["operator"] for r in data7["operator_table"]] == ["alice", "bob", "chen"]

    daily_ops = {r["operator"] for r in data7["operator_daily"]}
    assert daily_ops == {"alice", "bob", "chen"}
    assert "dan" not in daily_ops
    assert "" not in daily_ops
    assert all(r["day"] != days["old"] for r in data7["operator_daily"])

    data90 = client.get("/api/skills?days=90").json()
    assert any(r["operator"] == "alice" and r["day"] == days["old"] for r in data90["operator_daily"])
    assert {r["operator"]: r["sessions_total"] for r in data90["operator_table"]} == {
        "alice": 2,
        "bob": 1,
        "chen": 1,
    }


def test_skills_overview_governance_untracked_usage_is_windowed_used_only(client, app_mod):
    _set_catalog(app_mod)

    def report_many(skill, count, prefix, days_ago=1, mode="used", operators=None, runtimes=None):
        operators = operators or ["alice"]
        runtimes = runtimes or ["codex"]
        for i in range(count):
            sid = f"{prefix}-{i}"
            ev(client, operator=operators[i % len(operators)], runtime=runtimes[i % len(runtimes)],
               session_id=sid, skill=skill, skill_mode=mode, current_step=sid)
            _set_skill_day(app_mod, sid, skill, days_ago, mode=mode)

    report_many("alpha", 6, "own")                      # own catalog skill
    report_many("beta", 2, "external")                  # catalog external, not untracked
    report_many("ghost-a", 3, "ghost-a", operators=["alice", "bob", "chen"],
                runtimes=["codex", "claude-code"])
    report_many("ghost-b", 1, "ghost-b")
    report_many("ghost-equipped", 3, "ghost-equipped", mode="equipped")
    report_many("ghost-old", 2, "ghost-old", days_ago=20)

    data7 = client.get("/api/skills?days=7").json()["governance"]["untracked_usage"]
    assert data7["total_sessions"] == 12
    assert data7["used_sessions"] == 4
    assert data7["skill_count"] == 2
    assert data7["ratio"] == pytest.approx(4 / 12)
    assert [row["name"] for row in data7["top"]] == ["ghost-a", "ghost-b"]
    assert data7["top"][0]["source"] == "非公司库"
    assert data7["top"][0]["sessions"] == 3
    assert data7["top"][0]["share"] == pytest.approx(3 / 12)
    assert data7["top"][0]["users_30d"] == 3
    assert data7["top"][0]["runtime_counts"] == {"claude-code": 1, "codex": 2}
    assert len(data7["top"][0]["trend_days"]) == 14
    assert len(data7["top"][0]["trend_14d"]) == 14
    assert sum(data7["top"][0]["trend_14d"]) == 3
    assert "beta" not in {row["name"] for row in data7["top"]}
    assert "ghost-equipped" not in {row["name"] for row in data7["top"]}

    data30 = client.get("/api/skills?days=30").json()["governance"]["untracked_usage"]
    assert data30["total_sessions"] == 14
    assert data30["used_sessions"] == 6
    assert data30["ratio"] == pytest.approx(6 / 14)
    assert [row["name"] for row in data30["top"]] == ["ghost-a", "ghost-old", "ghost-b"]


def test_skills_overview_governance_empty_and_tie_sort(client, app_mod):
    _set_catalog(app_mod)
    empty = client.get("/api/skills?days=7").json()["governance"]["untracked_usage"]
    assert empty == {
        "ratio": 0,
        "used_sessions": 0,
        "total_sessions": 0,
        "skill_count": 0,
        "top": [],
    }

    ev(client, operator="alice", runtime="codex", session_id="older", skill="ghost-older", current_step="older")
    ev(client, operator="alice", runtime="codex", session_id="newer", skill="ghost-newer", current_step="newer")
    old_day = _set_skill_day(app_mod, "older", "ghost-older", 2)
    new_day = _set_skill_day(app_mod, "newer", "ghost-newer", 0)

    data = client.get("/api/skills?days=7").json()["governance"]["untracked_usage"]
    assert data["total_sessions"] == 2
    assert data["used_sessions"] == 2
    assert data["ratio"] == 1
    assert [(row["name"], row["last_day"]) for row in data["top"]] == [
        ("ghost-newer", new_day),
        ("ghost-older", old_day),
    ]


def test_skills_overview_today_and_daily_window_use_shanghai_stats_day(client, app_mod, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 6, 12, 16, 5, tzinfo=timezone.utc)
            return value if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(app_mod, "datetime", FixedDatetime)
    _set_catalog(app_mod)
    ev(client, operator="alice", runtime="codex", session_id="today", skill="alpha", current_step="today")
    ev(client, operator="alice", runtime="codex", session_id="edge", skill="alpha", current_step="edge")
    ev(client, operator="alice", runtime="codex", session_id="old", skill="alpha", current_step="old")

    with app_mod.db() as conn:
        conn.execute("UPDATE skill_uses SET day=?, first_seen=? WHERE session_id=?",
                     ("2026-05-15", "2026-05-15T12:00:00+00:00", "edge"))
        conn.execute("UPDATE skill_uses SET day=?, first_seen=? WHERE session_id=?",
                     ("2026-05-14", "2026-05-14T12:00:00+00:00", "old"))
        conn.commit()

    data30 = client.get("/api/skills?days=30").json()
    assert data30["today"] == "2026-06-13"
    assert {r["day"] for r in data30["daily"] if r["skill"] == "alpha"} == {"2026-05-15", "2026-06-13"}

    data7 = client.get("/api/skills?days=7").json()
    assert data7["today"] == "2026-06-13"
    assert {r["day"] for r in data7["daily"] if r["skill"] == "alpha"} == {"2026-06-13"}


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
    assert data["today"] == app_mod.stats_day()
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


def test_operator_detail_used_only_skill_breakdown_and_recent_records(client, app_mod):
    days = _seed_skill_stats(client, app_mod)
    ev(client, operator="alice", runtime="codex", session_id="a-new", skill="beta", current_step="6")
    ev(client, operator="alice", runtime="open-claw", session_id="a-new", skill="meta-tool",
       skill_mode="equipped", current_step="7")
    _set_skill_day(app_mod, "a-new", "beta", 5)
    _set_skill_day(app_mod, "a-new", "meta-tool", 5, mode="equipped")

    data = client.get("/api/operator/alice").json()
    assert data["today"] == app_mod.stats_day()
    assert data["operator"] == "alice"
    assert data["metrics"] == {
        "sessions_7d": 2,
        "sessions_30d": 2,
        "sessions_total": 3,
        "skill_count": 2,
        "session_count": 2,
        "first_day": days["old"],
        "last_day": days["used"],
    }
    daily = {(r["day"], r["skill"]): r["sessions"] for r in data["daily"]}
    assert daily[(days["used"], "alpha")] == 1
    assert daily[(days["used"], "beta")] == 1
    assert (days["used"], "meta-tool") not in daily

    skills = {r["name"]: r for r in data["skills"]}
    assert set(skills) == {"alpha", "beta"}
    assert skills["alpha"]["source"] == "own"
    assert skills["beta"]["source"] == "external"
    assert skills["alpha"]["sessions_total"] == 2
    assert skills["beta"]["sessions_30d"] == 1
    assert data["runtime"] == [{"runtime": "codex", "used": 3}]
    assert all("mode" not in r for r in data["records"])
    assert [r["skill"] for r in data["records"][:2]] == ["alpha", "beta"]


def test_operator_detail_resolves_canonical_operator_identity(client, app_mod):
    ev(client, operator="Alice", runtime="codex", session_id="a1", skill="alpha", current_step="1")

    data = client.get("/api/operator/alice").json()
    assert data["operator"] == "Alice"
    assert data["metrics"]["sessions_total"] == 1


def test_operator_detail_recent_records_are_limited_to_50(client, app_mod):
    _set_catalog(app_mod)
    for i in range(55):
        session = f"a-{i:02d}"
        ev(client, operator="alice", runtime="codex", session_id=session, skill=f"skill-{i:02d}",
           current_step=f"step-{i}")
        _set_skill_day(app_mod, session, f"skill-{i:02d}", 0)

    data = client.get("/api/operator/alice").json()
    assert len(data["records"]) == 50


def test_operator_detail_unknown_or_equipped_only_404(client, app_mod):
    ev(client, operator="dan", runtime="open-claw", session_id="e-new", skill="alpha",
       skill_mode="equipped", current_step="equipped")
    assert client.get("/api/operator/dan").status_code == 404
    assert client.get("/api/operator/nope").status_code == 404


def test_skill_detail_unknown_404(client):
    assert client.get("/api/skill/nope").status_code == 404


def test_skills_overview_rejects_invalid_days(client):
    assert client.get("/api/skills?days=13").status_code == 400
    assert client.get("/api/skills?days=0").status_code == 400
