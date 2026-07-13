from conftest import ev


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
