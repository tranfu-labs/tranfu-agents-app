from datetime import datetime, timezone

from conftest import ev


def _set_times(monkeypatch, *values):
    import server.routes.ingest as ingest

    seq = iter(datetime.fromisoformat(v).replace(tzinfo=timezone.utc) for v in values)
    monkeypatch.setattr(ingest, "now_utc", lambda: next(seq))


def _event_row(app_mod, session_id="s1"):
    with app_mod.db() as conn:
        return conn.execute(
            "SELECT id,last_seen FROM events WHERE session_id=? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()


def _event_rows(app_mod, session_id):
    with app_mod.db() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT id,recv,last_seen,status,current_step,source FROM events "
            "WHERE session_id=? ORDER BY id",
            (session_id,),
        )]


def _shim_row(app_mod):
    with app_mod.db() as conn:
        return conn.execute("SELECT shim_version,updated FROM agent_shim_versions").fetchone()


def test_pure_heartbeat_batches_last_seen_until_flush(client, app_mod, monkeypatch):
    app_mod.HEARTBEAT_BATCH_SECONDS = 15
    _set_times(
        monkeypatch,
        "2026-06-12T00:00:00+00:00",
        "2026-06-12T00:00:10+00:00",
    )
    ev(client, session_id="batch", current_step="same")
    before = _event_row(app_mod, "batch")

    r = ev(client, session_id="batch", current_step="same")

    assert r.json()["heartbeat"] is True
    assert _event_row(app_mod, "batch")["last_seen"] == before["last_seen"]
    assert dict(app_mod._heartbeat_pending) == {before["id"]: "2026-06-12T00:00:10+00:00"}

    assert app_mod.flush_heartbeat_batch() == 1
    assert _event_row(app_mod, "batch")["last_seen"] == "2026-06-12T00:00:10+00:00"


def test_heartbeat_batch_can_be_disabled(client, app_mod, monkeypatch):
    app_mod.HEARTBEAT_BATCH_SECONDS = 0
    _set_times(
        monkeypatch,
        "2026-06-12T00:00:00+00:00",
        "2026-06-12T00:00:10+00:00",
    )
    ev(client, session_id="nobatch", current_step="same")

    r = ev(client, session_id="nobatch", current_step="same")

    assert r.json()["heartbeat"] is True
    assert _event_row(app_mod, "nobatch")["last_seen"] == "2026-06-12T00:00:10+00:00"
    assert app_mod._heartbeat_pending == {}


def test_same_state_heartbeat_after_stale_gap_starts_new_segment(client, app_mod, monkeypatch):
    app_mod.HEARTBEAT_BATCH_SECONDS = 0
    _set_times(
        monkeypatch,
        "2026-06-12T00:00:00+00:00",
        "2026-06-12T00:03:00+00:00",
        "2026-06-12T00:06:01+00:00",
    )
    ev(client, session_id="gap", current_step="same")
    within = ev(client, session_id="gap", current_step="same")
    resumed = ev(client, session_id="gap", current_step="same")

    assert within.json()["heartbeat"] is True
    assert resumed.json()["logged"] is True
    assert _event_rows(app_mod, "gap") == [
        {
            "id": 1,
            "recv": "2026-06-12T00:00:00+00:00",
            "last_seen": "2026-06-12T00:03:00+00:00",
            "status": "running",
            "current_step": "same",
            "source": "heartbeat",
        },
        {
            "id": 2,
            "recv": "2026-06-12T00:06:01+00:00",
            "last_seen": "2026-06-12T00:06:01+00:00",
            "status": "running",
            "current_step": "same",
            "source": "heartbeat_resume",
        },
    ]
    assert len(client.get("/api/state").json()["feed"]) == 1


def test_pending_heartbeat_is_used_as_last_confirmed_time(client, app_mod, monkeypatch):
    app_mod.HEARTBEAT_BATCH_SECONDS = 3600
    _set_times(
        monkeypatch,
        "2026-06-12T00:00:00+00:00",
        "2026-06-12T00:02:00+00:00",
        "2026-06-12T00:04:30+00:00",
    )
    ev(client, session_id="pending-gap", current_step="same")
    ev(client, session_id="pending-gap", current_step="same")
    latest = ev(client, session_id="pending-gap", current_step="same")

    assert latest.json()["heartbeat"] is True
    assert len(_event_rows(app_mod, "pending-gap")) == 1
    assert list(app_mod._heartbeat_pending.values()) == ["2026-06-12T00:04:30+00:00"]


def test_stale_recovery_persists_pending_endpoint_before_new_segment(client, app_mod, monkeypatch):
    app_mod.HEARTBEAT_BATCH_SECONDS = 3600
    _set_times(
        monkeypatch,
        "2026-06-12T00:00:00+00:00",
        "2026-06-12T00:02:00+00:00",
        "2026-06-12T00:05:01+00:00",
    )
    ev(client, session_id="pending-split", current_step="same")
    ev(client, session_id="pending-split", current_step="same")
    resumed = ev(client, session_id="pending-split", current_step="same")

    assert resumed.json()["logged"] is True
    rows = _event_rows(app_mod, "pending-split")
    assert [row["last_seen"] for row in rows] == [
        "2026-06-12T00:02:00+00:00",
        "2026-06-12T00:05:01+00:00",
    ]
    assert app_mod._heartbeat_pending == {}


def test_skill_heartbeat_stays_immediate(client, app_mod, monkeypatch):
    app_mod.HEARTBEAT_BATCH_SECONDS = 15
    _set_times(
        monkeypatch,
        "2026-06-12T00:00:00+00:00",
        "2026-06-12T00:00:10+00:00",
    )
    ev(client, session_id="skill-batch", current_step="tool: Skill")

    r = ev(client, session_id="skill-batch", current_step="tool: Skill", skill="openai-docs")

    assert r.json()["heartbeat"] is True
    assert _event_row(app_mod, "skill-batch")["last_seen"] == "2026-06-12T00:00:10+00:00"
    with app_mod.db() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM skill_uses").fetchone()["c"] == 1
    assert app_mod._heartbeat_pending == {}


def test_same_shim_version_does_not_touch_updated(client, app_mod, monkeypatch):
    app_mod.HEARTBEAT_BATCH_SECONDS = 15
    _set_times(
        monkeypatch,
        "2026-06-12T00:00:00+00:00",
        "2026-06-12T00:00:10+00:00",
        "2026-06-12T00:00:20+00:00",
    )
    ev(client, session_id="shim", current_step="a", shim_version="v1")
    first = dict(_shim_row(app_mod))

    ev(client, session_id="shim", current_step="b", shim_version="v1")
    second = dict(_shim_row(app_mod))

    ev(client, session_id="shim", current_step="c", shim_version="v2")
    third = dict(_shim_row(app_mod))

    assert first == {"shim_version": "v1", "updated": "2026-06-12T00:00:00+00:00"}
    assert second == first
    assert third == {"shim_version": "v2", "updated": "2026-06-12T00:00:20+00:00"}
