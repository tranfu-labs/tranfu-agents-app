from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from conftest import ev
from server.db import STATS_TZ
from server.routes import board


def _fixed_datetime(value):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    return FixedDatetime


def _card(operator="alice", agent="builder", runtime="codex", **overrides):
    card = {
        "operator": operator,
        "agent": agent,
        "runtime": runtime,
        "status": "done",
        "task": "release dashboard",
        "current_step": "verify",
        "models": ["gpt-5"],
        "ts": "2026-07-14T08:00:00+00:00",
        "last_seen": "2026-07-14T08:00:00+00:00",
        "active_days": [0] * 89 + [120],
        "today_active": 120,
        "week_active": 120,
        "shim_version": "current",
        "quality": {"runs": 4, "success": 2, "error": 1, "blocked": 0},
    }
    card.update(overrides)
    return card


def _insert_run(conn, operator, agent, session_id, start, end, runtime="codex"):
    day = datetime.fromisoformat(start).astimezone(STATS_TZ).date().isoformat()
    conn.execute("""INSERT INTO events
      (ts,recv,day,last_seen,operator,runtime,agent,session_id,status,current_step,source)
      VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
      (start, start, day, start, operator, runtime, agent, session_id, "running", "run", "heartbeat"))
    conn.execute("""INSERT INTO events
      (ts,recv,day,last_seen,operator,runtime,agent,session_id,status,current_step,source)
      VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
      (end, end, day, end, operator, runtime, agent, session_id, "done", "done", "heartbeat"))


def test_state_agent_overview_uses_identity_cards_and_exposes_history(client):
    ev(client, operator="alice", agent="builder", runtime="codex", session_id="a1", status="running", current_step="run")
    ev(client, operator="alice", agent="builder", runtime="codex", session_id="a1", status="done", current_step="done")
    ev(client, operator="alice", agent="builder", runtime="codex", session_id="a2", status="running", current_step="run")
    ev(client, operator="alice", agent="builder", runtime="codex", session_id="a2", status="error", current_step="failed")
    ev(client, operator="bob", runtime="claude-code", session_id="b1", status="blocked", current_step="blocked")

    body = client.get("/api/state").json()
    overview = body["agent_overview"]
    assert len(body["sessions"]) == 2
    assert len(overview["days"]) == 90
    assert len(overview["daily"]) == 90
    assert overview["days"] == sorted(overview["days"])
    assert overview["days"][-1] == overview["today"]
    assert overview["summary"]["agents"] == 2
    assert overview["summary"]["operators"] == 2
    assert overview["summary"]["runs"] >= 2
    assert overview["summary"]["success"] >= 1
    assert overview["summary"]["errors"] >= 1
    assert overview["summary"]["blocked"] >= 1
    assert {row["runtime"] for row in overview["runtime"]} == {"codex", "claude-code"}
    assert {row["operator"] for row in overview["operator"]} == {"alice", "bob"}


def test_state_agent_overview_keeps_legacy_state_fields(client):
    ev(client, session_id="legacy", current_step="x")
    body = client.get("/api/state").json()
    assert body["sessions"]
    assert body["totals"]["agents"] == 1
    assert body["shim"]["version"]
    assert "skills" in body


def test_agents_api_returns_window_ranking_operator_and_merged_identities(client, app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "datetime", _fixed_datetime(datetime(2026, 7, 14, 12, tzinfo=timezone.utc)))
    with app_mod.db() as conn:
        _insert_run(conn, "alice", "builder", "a1", "2026-07-14T01:00:00+00:00", "2026-07-14T01:10:00+00:00")
        _insert_run(conn, "alice", "builder", "a2", "2026-07-14T02:00:00+00:00", "2026-07-14T02:20:00+00:00")
        _insert_run(conn, "bob", "builder", "b1", "2026-07-14T03:00:00+00:00", "2026-07-14T03:05:00+00:00")
        conn.commit()

    body = client.get("/api/agents?w=7d").json()
    assert body["today"] == "2026-07-14"
    assert body["window"]["start"] == "2026-07-08"
    assert body["window"]["end"] == "2026-07-14"
    assert len(body["window"]["days"]) == 7
    assert body["summary"]["agents"] == 2
    assert body["summary"]["active_seconds"] == 2100
    assert [row["operator"] for row in body["ranking"]] == ["alice", "bob"]
    assert [row["active_seconds"] for row in body["ranking"]] == [1800, 300]
    assert body["ranking"][0]["key"] == "alice::builder"
    assert body["agents"][0]["operator"] == "alice"
    assert body["agents"][0]["window_active_days"] == 1
    assert len(body["daily"]) == 7
    assert body["daily"][-1]["active_seconds"] == 2100
    assert {segment["operator"] for segment in body["daily"][-1]["segments"]} == {"alice", "bob"}


def test_agents_api_custom_window_uses_shanghai_days_and_rejects_invalid_ranges(client, app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "datetime", _fixed_datetime(datetime(2026, 7, 14, 12, tzinfo=timezone.utc)))
    start = int(datetime(2026, 7, 13, 1, tzinfo=STATS_TZ).timestamp())
    end = int(datetime(2026, 7, 14, 23, tzinfo=STATS_TZ).timestamp())
    body = client.get(f"/api/agents?w=custom&wstart={start}&wend={end}").json()
    assert body["window"]["days"] == ["2026-07-13", "2026-07-14"]

    assert client.get("/api/agents?w=custom").status_code == 400
    assert client.get(f"/api/agents?w=custom&wstart={end}&wend={start}").status_code == 400
    too_old = int(datetime(2026, 4, 15, tzinfo=STATS_TZ).timestamp())
    assert client.get(f"/api/agents?w=custom&wstart={too_old}&wend={end}").status_code == 400
    old_end = int(datetime(2026, 4, 16, tzinfo=STATS_TZ).timestamp())
    assert client.get(f"/api/agents?w=custom&wstart={too_old}&wend={old_end}").status_code == 400
    future = int(datetime(2026, 7, 20, 23, 59, 59, tzinfo=STATS_TZ).timestamp())
    future_body = client.get(f"/api/agents?w=custom&wstart={end}&wend={future}").json()
    assert future_body["window"]["end"] == "2026-07-20"
    assert future_body["comparison"]["current"]["available"] is True
    assert future_body["daily"][-1]["active_seconds"] == 0
    requested_example = client.get(
        "/api/agents?w=custom&wstart=1783958400&wend=1784563199"
    )
    assert requested_example.status_code == 200
    assert requested_example.json()["window"]["days"] == [
        "2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17",
        "2026-07-18", "2026-07-19", "2026-07-20",
    ]
    assert client.get("/api/agents?w=nope").status_code == 400

    with pytest.raises(HTTPException):
        board._agents_window("custom", "not-a-timestamp", "also-not")


def test_agents_presets_remain_aligned_with_existing_skills_windows(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "datetime", _fixed_datetime(datetime(2026, 7, 14, 12, tzinfo=timezone.utc)))
    for key in ("today", "this_week", "last_week", "7d", "14d", "30d", "90d"):
        agents_window = board._agents_window(key)
        skills_window = board._skills_window(30, w=key)
        assert (agents_window["start"], agents_window["end"]) == (skills_window["start"], skills_window["end"])

    start = int(datetime(2026, 4, 1, tzinfo=STATS_TZ).timestamp())
    end = int(datetime(2026, 7, 14, tzinfo=STATS_TZ).timestamp())
    assert board._skills_window(30, w="custom", wstart=start, wend=end)["days"] == 90
    assert board._skills_window(30, w="custom", wstart=end, wend=start)["key"] == "30d"
    with pytest.raises(HTTPException):
        board._skills_window(30, w="nope")


@pytest.mark.parametrize("window,days", [
    ("today", 1), ("this_week", 2), ("last_week", 7),
    ("7d", 7), ("14d", 14), ("30d", 30), ("90d", 90),
])
def test_agents_api_preset_windows(client, app_mod, monkeypatch, window, days):
    monkeypatch.setattr(app_mod, "datetime", _fixed_datetime(datetime(2026, 7, 14, 12, tzinfo=timezone.utc)))
    body = client.get(f"/api/agents?w={window}").json()
    assert body["window"]["key"] == window
    assert len(body["window"]["days"]) == days
    assert body["window"]["end"] <= body["today"]


def test_agents_payload_filters_signals_and_keeps_operator_out_of_search(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "datetime", _fixed_datetime(datetime(2026, 7, 14, 12, tzinfo=timezone.utc)))
    cards = [
        _card(),
        _card(operator="bob", agent="reviewer", runtime="claude-code", status="running",
              task="review api", active_days=[0] * 89 + [60], today_active=60,
              quality={"runs": 1, "success": 1}, shim_version="current",
              last_seen="2026-07-14T09:00:00+00:00"),
        _card(operator="carol", agent="scout", status="idle", task="research",
              active_days=[0] * 90, today_active=0, week_active=0, quality={}, shim_version=None),
    ]

    payload = board.agents_overview_payload(cards, "current", w="today")
    assert [row["operator"] for row in payload["ranking"]] == ["alice", "bob"]
    assert payload["signals"] == {"error": 1, "shim": 1, "quiet": 1, "quality": 1}
    assert payload["summary"]["attention"] == 2
    assert payload["comparison"]["current"]["available"] is True

    assert board.agents_overview_payload(cards, "current", q="review")["summary"]["agents"] == 1
    assert board.agents_overview_payload(cards, "current", q="bob")["summary"]["agents"] == 0
    assert board.agents_overview_payload(cards, "current", q="claude-code")["summary"]["agents"] == 0
    assert board.agents_overview_payload(cards, "current", status="live")["agents"][0]["operator"] == "bob"
    assert board.agents_overview_payload(cards, "current", status="idle")["agents"][0]["operator"] == "carol"
    assert board.agents_overview_payload(cards, "current", status="done")["agents"][0]["operator"] == "alice"
    assert board.agents_overview_payload(cards, "current", status="attention", signal="quality")["agents"][0]["operator"] == "alice"
    assert board.agents_overview_payload(cards, "current", signal="quiet")["agents"][0]["operator"] == "carol"


@pytest.mark.parametrize("sort", ["recent", "window_time", "window_days", "success", "errors", "name", "today", "week"])
def test_agents_payload_accepts_all_supported_sorts(app_mod, monkeypatch, sort):
    monkeypatch.setattr(app_mod, "datetime", _fixed_datetime(datetime(2026, 7, 14, 12, tzinfo=timezone.utc)))
    cards = [_card(), _card(operator="bob", agent="reviewer", active_days=[0] * 88 + [30, 30])]
    payload = board.agents_overview_payload(cards, "current", w="7d", sort=sort)
    assert len(payload["agents"]) == 2


@pytest.mark.parametrize("params", [
    {"status": "nope"}, {"signal": "nope"}, {"sort": "nope"},
])
def test_agents_payload_rejects_invalid_filters(app_mod, monkeypatch, params):
    monkeypatch.setattr(app_mod, "datetime", _fixed_datetime(datetime(2026, 7, 14, 12, tzinfo=timezone.utc)))
    with pytest.raises(HTTPException) as exc:
        board.agents_overview_payload([_card()], "current", **params)
    assert exc.value.status_code == 400
