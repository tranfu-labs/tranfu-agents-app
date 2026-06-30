import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from conftest import ev


ROOT = Path(__file__).resolve().parents[1]


def _skill_count(app_mod):
    with app_mod.db() as conn:
        return conn.execute("SELECT COUNT(*) c FROM skill_uses").fetchone()["c"]


def _skill_rows(app_mod):
    with app_mod.db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT session_id,skill,mode,operator,runtime,day FROM skill_uses ORDER BY session_id,skill,mode")]


def _set_skill_day(app_mod, session_id, skill, days_ago):
    day = (app_mod.stats_today() - timedelta(days=days_ago)).isoformat()
    with app_mod.db() as conn:
        conn.execute("UPDATE skill_uses SET day=? WHERE session_id=? AND skill=?",
                     (day, session_id, skill))
        conn.commit()


def test_skill_use_dedupes_per_session(client, app_mod):
    assert ev(client, session_id="s1", skill="openai-docs").status_code == 200
    assert ev(client, session_id="s1", skill="openai-docs").status_code == 200
    assert _skill_rows(app_mod) == [{
        "session_id": "s1", "skill": "openai-docs", "mode": "used", "operator": "alice",
        "runtime": "codex", "day": app_mod.stats_day(),
    }]


def test_skill_and_event_days_use_shanghai_stats_day(client, app_mod, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 6, 12, 16, 5, tzinfo=timezone.utc)
            return value if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(app_mod, "datetime", FixedDatetime)
    ev(client, session_id="s1", skill="openai-docs", current_step="edge")

    with app_mod.db() as conn:
        event = conn.execute("SELECT day, recv FROM events WHERE session_id='s1'").fetchone()
        skill = conn.execute("SELECT day, first_seen FROM skill_uses WHERE session_id='s1'").fetchone()
        seen = conn.execute("SELECT first_day FROM skills_seen WHERE name='openai-docs'").fetchone()

    assert event["day"] == "2026-06-13"
    assert skill["day"] == "2026-06-13"
    assert seen["first_day"] == "2026-06-13"
    assert event["recv"].startswith("2026-06-12T16:05:00")
    assert skill["first_seen"].startswith("2026-06-12T16:05:00")


def test_skill_use_counts_different_sessions(client, app_mod):
    ev(client, session_id="s1", skill="openai-docs")
    ev(client, session_id="s2", skill="openai-docs")
    assert _skill_count(app_mod) == 2


def test_same_session_can_count_different_skills(client, app_mod):
    ev(client, session_id="s1", skill="openai-docs", current_step="tool: Skill")
    ev(client, session_id="s1", skill="skill-creator", current_step="tool: Skill")
    assert {(r["session_id"], r["skill"], r["mode"]) for r in _skill_rows(app_mod)} == {
        ("s1", "openai-docs", "used"), ("s1", "skill-creator", "used")
    }


def test_skill_name_is_trimmed_and_truncated(client, app_mod):
    raw = "  " + ("x" * 200) + "  "
    ev(client, session_id="s1", skill=raw)
    rows = _skill_rows(app_mod)
    assert len(rows) == 1
    assert rows[0]["skill"] == "x" * app_mod.MAX_SKILL_NAME


def test_skill_without_session_is_ignored_not_rejected(client, app_mod):
    r = client.post("/v1/events", json={"operator": "alice", "runtime": "codex",
                                        "status": "running", "skill": "openai-docs"})
    assert r.status_code == 200 and r.json()["skill_ignored"] is True
    assert _skill_count(app_mod) == 0


def test_skill_processed_before_heartbeat_short_circuit(client, app_mod):
    ev(client, session_id="s1", current_step="tool: Skill")
    r = ev(client, session_id="s1", current_step="tool: Skill", skill="openai-docs")
    assert r.json().get("heartbeat") is True
    assert _skill_count(app_mod) == 1


def test_skill_mode_equipped_dedupes_per_session(client, app_mod):
    ev(client, session_id="s1", skill="openai-docs", skill_mode="equipped")
    ev(client, session_id="s1", skill="openai-docs", skill_mode="equipped")
    rows = _skill_rows(app_mod)
    assert len(rows) == 1
    assert rows[0]["mode"] == "equipped"


def test_same_session_can_count_used_and_equipped_for_same_skill(client, app_mod):
    ev(client, session_id="s1", skill="openai-docs", skill_mode="equipped")
    ev(client, session_id="s1", skill="openai-docs", skill_mode="used")
    assert {(r["skill"], r["mode"]) for r in _skill_rows(app_mod)} == {
        ("openai-docs", "equipped"), ("openai-docs", "used")
    }


def test_invalid_and_missing_skill_mode_fall_back_to_used(client, app_mod):
    ev(client, session_id="s1", skill="alpha", skill_mode="nonsense")
    ev(client, session_id="s2", skill="beta")
    assert {(r["skill"], r["mode"]) for r in _skill_rows(app_mod)} == {
        ("alpha", "used"), ("beta", "used")
    }


def test_empty_snapshot_has_skills_array(client):
    assert client.get("/api/state").json()["skills"] == []


def test_skill_usage_snapshot_windows_and_sort(client, app_mod):
    ev(client, operator="alice", session_id="a-old", skill="alpha", current_step="1")
    ev(client, operator="alice", session_id="a-new", skill="alpha", current_step="2")
    ev(client, operator="bob", session_id="b-new", skill="alpha", current_step="3")
    ev(client, operator="chen", session_id="c-new", skill="beta", current_step="4")
    _set_skill_day(app_mod, "a-old", "alpha", 31)
    _set_skill_day(app_mod, "a-new", "alpha", 5)
    _set_skill_day(app_mod, "b-new", "alpha", 5)
    _set_skill_day(app_mod, "c-new", "beta", 1)

    skills = client.get("/api/state").json()["skills"]
    assert [s["name"] for s in skills[:2]] == ["alpha", "beta"]
    alpha = skills[0]
    assert alpha["mode"] == "used"
    assert alpha["sessions_7d"] == 2
    assert alpha["sessions_30d"] == 2
    assert alpha["sessions_total"] == 3
    assert alpha["users_30d"] == 2


def test_skill_usage_snapshot_keeps_used_and_equipped_separate(client, app_mod):
    ev(client, operator="alice", session_id="u1", skill="alpha", skill_mode="used")
    ev(client, operator="bob", session_id="u2", skill="alpha", skill_mode="used")
    ev(client, operator="chen", session_id="e1", skill="alpha", skill_mode="equipped")

    skills = client.get("/api/state").json()["skills"]
    by_mode = {(s["name"], s["mode"]): s for s in skills}
    assert by_mode[("alpha", "used")]["sessions_total"] == 2
    assert by_mode[("alpha", "equipped")]["sessions_total"] == 1


def test_init_db_migrates_old_skill_uses_primary_key(app_mod):
    with app_mod.db() as conn:
        conn.execute("DROP TABLE skill_uses")
        conn.execute("""CREATE TABLE skill_uses (
          session_id TEXT NOT NULL,
          skill TEXT NOT NULL,
          operator TEXT,
          runtime TEXT,
          day TEXT,
          first_seen TEXT,
          PRIMARY KEY (session_id, skill)
        )""")
        conn.execute("""INSERT INTO skill_uses(session_id,skill,operator,runtime,day,first_seen)
          VALUES('s1','alpha','alice','codex','2026-01-01','2026-01-01T00:00:00+00:00')""")
        conn.commit()

    app_mod.init_db()

    with app_mod.db() as conn:
        info = conn.execute("PRAGMA table_info(skill_uses)").fetchall()
        pk = [r["name"] for r in sorted((r for r in info if r["pk"]), key=lambda r: r["pk"])]
        row = dict(conn.execute("SELECT session_id,skill,mode FROM skill_uses").fetchone())
    assert pk == ["session_id", "skill", "mode"]
    assert row == {"session_id": "s1", "skill": "alpha", "mode": "used"}


def test_tf_report_print_includes_optional_skill():
    env = os.environ.copy()
    env.update({"TF_OPERATOR": "alice", "TF_RUNTIME": "codex", "TF_AGENT": "code"})
    env.pop("TF_SERVER", None)
    r = subprocess.run(
        [sys.executable, "shims/tf_report.py", "--status", "running",
         "--session", "s1", "--skill", "openai-docs", "--print"],
        cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    assert json.loads(r.stdout)["skill"] == "openai-docs"


def test_tf_report_print_includes_optional_skill_mode():
    env = os.environ.copy()
    env.update({"TF_OPERATOR": "alice", "TF_RUNTIME": "open-claw", "TF_AGENT": "copy"})
    env.pop("TF_SERVER", None)
    r = subprocess.run(
        [sys.executable, "shims/tf_report.py", "--status", "done",
         "--session", "s1", "--skill", "openai-docs", "--skill-mode", "equipped", "--print"],
        cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    payload = json.loads(r.stdout)
    assert payload["skill"] == "openai-docs"
    assert payload["skill_mode"] == "equipped"


def test_tf_report_skill_env_switch_suppresses_field():
    env = os.environ.copy()
    env.update({"TF_OPERATOR": "alice", "TF_RUNTIME": "codex", "TF_AGENT": "code",
                "TF_REPORT_SKILLS": "0"})
    env.pop("TF_SERVER", None)
    r = subprocess.run(
        [sys.executable, "shims/tf_report.py", "--status", "running",
         "--session", "s1", "--skill", "openai-docs", "--print"],
        cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    assert "skill" not in json.loads(r.stdout)
