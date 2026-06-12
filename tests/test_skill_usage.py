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
            "SELECT session_id,skill,operator,runtime,day FROM skill_uses ORDER BY session_id,skill")]


def _set_skill_day(app_mod, session_id, skill, days_ago):
    day = (datetime.now(timezone.utc).date() - timedelta(days=days_ago)).isoformat()
    with app_mod.db() as conn:
        conn.execute("UPDATE skill_uses SET day=? WHERE session_id=? AND skill=?",
                     (day, session_id, skill))
        conn.commit()


def test_skill_use_dedupes_per_session(client, app_mod):
    assert ev(client, session_id="s1", skill="openai-docs").status_code == 200
    assert ev(client, session_id="s1", skill="openai-docs").status_code == 200
    assert _skill_rows(app_mod) == [{
        "session_id": "s1", "skill": "openai-docs", "operator": "alice",
        "runtime": "codex", "day": datetime.now(timezone.utc).date().isoformat(),
    }]


def test_skill_use_counts_different_sessions(client, app_mod):
    ev(client, session_id="s1", skill="openai-docs")
    ev(client, session_id="s2", skill="openai-docs")
    assert _skill_count(app_mod) == 2


def test_same_session_can_count_different_skills(client, app_mod):
    ev(client, session_id="s1", skill="openai-docs", current_step="tool: Skill")
    ev(client, session_id="s1", skill="skill-creator", current_step="tool: Skill")
    assert {(r["session_id"], r["skill"]) for r in _skill_rows(app_mod)} == {
        ("s1", "openai-docs"), ("s1", "skill-creator")
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
    assert alpha["sessions_7d"] == 2
    assert alpha["sessions_30d"] == 2
    assert alpha["sessions_total"] == 3
    assert alpha["users_30d"] == 2


def test_tf_report_print_includes_optional_skill():
    env = os.environ.copy()
    env.update({"TF_OPERATOR": "alice", "TF_RUNTIME": "codex", "TF_AGENT": "code"})
    env.pop("TF_SERVER", None)
    r = subprocess.run(
        [sys.executable, "shims/tf_report.py", "--status", "running",
         "--session", "s1", "--skill", "openai-docs", "--print"],
        cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    assert json.loads(r.stdout)["skill"] == "openai-docs"


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
