"""board 域:metrics 分支、_snapshot.card 边界、/api/agent /api/operator /api/skill。
对应 server/app.py 的 metrics / _snapshot / agent_detail / operator_detail / skill_detail。
由 add-server-app-test-baseline 引入。
"""
from datetime import datetime, timezone

from conftest import ev, set_ingest_clock


def _set_ingest_times(monkeypatch, *values):
    set_ingest_clock(monkeypatch, *values)


# ---- /api/agent/{key} -----------------------------------------------------
def test_agent_detail_404_for_unknown_key(client):
    r = client.get("/api/agent/unknown%3A%3Anope")
    assert r.status_code == 404


def test_agent_detail_returns_card_for_known_key(client):
    ev(client, session_id="s", current_step="x", agent="codex-a")
    # key = operator::agent
    r = client.get("/api/agent/alice%3A%3Acodex-a")
    assert r.status_code == 200
    assert r.json()["agent"] == "codex-a"


# ---- /api/operator/{name} -------------------------------------------------
def test_operator_detail_404_when_no_used_skill(client):
    # 没有 used 记录 → 404
    r = client.get("/api/operator/ghost")
    assert r.status_code == 404


def test_operator_detail_success(client):
    ev(client, session_id="op1", current_step="x", skill="my-skill")
    r = client.get("/api/operator/alice")
    assert r.status_code == 200
    body = r.json()
    assert body["operator"] == "alice"
    assert body["metrics"]["sessions_total"] >= 1
    assert any(s["name"] == "my-skill" for s in body["skills"])


def test_operator_detail_resolves_case_variants(client):
    ev(client, operator="NEZHA", session_id="s", current_step="x", skill="k")
    # 用小写访问应解到 first-seen 大小写
    r = client.get("/api/operator/nezha")
    assert r.status_code == 200
    assert r.json()["operator"] == "NEZHA"


# ---- /api/skill/{name} ---------------------------------------------------
def test_skill_detail_404_for_unknown(client):
    r = client.get("/api/skill/no-such-skill")
    assert r.status_code == 404


def test_skill_detail_success(client):
    ev(client, session_id="sk1", current_step="x", skill="charted")
    r = client.get("/api/skill/charted")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "charted"
    assert body["metrics"]["sessions_total"] >= 1


def test_skill_detail_separates_used_and_equipped(client):
    ev(client, session_id="u", current_step="x", skill="dual", skill_mode="used")
    ev(client, session_id="e", current_step="x", skill="dual", skill_mode="equipped")
    body = client.get("/api/skill/dual").json()
    assert body["metrics"]["sessions_total"] >= 1
    assert body["metrics"]["equipped_total"] >= 1


# ---- metrics:blocked / auto_rate / 跨天 -----------------------------------
def test_blocked_status_counted_in_quality(client):
    ev(client, session_id="b1", current_step="rate", status="blocked")
    sessions = client.get("/api/state").json()["sessions"]
    card = next(c for c in sessions if c["operator"] == "alice")
    assert card["quality"]["blocked"] >= 1


def test_auto_rate_drops_on_waiting_session(client):
    # 一个会话:running → waiting → done(不计入 auto)
    ev(client, session_id="w1", current_step="run", status="running")
    ev(client, session_id="w1", current_step="ask", status="waiting")
    ev(client, session_id="w1", current_step="done", status="done")
    # 另一个会话:running → done(计入 auto)
    ev(client, session_id="w2", current_step="run", status="running")
    ev(client, session_id="w2", current_step="done", status="done")
    cards = client.get("/api/state").json()["sessions"]
    card = next(c for c in cards if c["operator"] == "alice")
    assert card["quality"]["runs"] >= 2
    # auto_rate < 1 因为 w1 命中 waiting
    assert card["quality"]["auto_rate"] < 1.0


def test_done_then_error_yields_runs_and_error_counts(client):
    ev(client, session_id="r1", current_step="x", status="running")
    ev(client, session_id="r1", current_step="x", status="done")
    ev(client, session_id="r2", current_step="x", status="running")
    ev(client, session_id="r2", current_step="x", status="error")
    cards = client.get("/api/state").json()["sessions"]
    card = next(c for c in cards if c["operator"] == "alice")
    q = card["quality"]
    assert q["runs"] >= 2
    assert q["error"] >= 1
    assert q["success"] >= 1


def test_active_time_buckets_split_on_shanghai_midnight(client, app_mod, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 6, 12, 16, 5, tzinfo=timezone.utc)
            return value if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(app_mod, "datetime", FixedDatetime)
    with app_mod.db() as conn:
        conn.execute("""INSERT INTO events
          (ts,recv,day,last_seen,operator,runtime,session_id,status,current_step,source)
          VALUES(?,?,?,?,?,?,?,?,?,?)""",
          ("2026-06-12T15:59:00+00:00", "2026-06-12T15:59:00+00:00", "2026-06-12",
           "2026-06-12T15:59:00+00:00", "alice", "codex", "midnight", "running", "run", "heartbeat"))
        conn.execute("""INSERT INTO events
          (ts,recv,day,last_seen,operator,runtime,session_id,status,current_step,source)
          VALUES(?,?,?,?,?,?,?,?,?,?)""",
          ("2026-06-12T16:01:00+00:00", "2026-06-12T16:01:00+00:00", "2026-06-13",
           "2026-06-12T16:01:00+00:00", "alice", "codex", "midnight", "done", "done", "heartbeat"))
        conn.commit()

    body = client.get("/api/state").json()
    card = next(c for c in body["sessions"] if c["session_id"] == "midnight")
    assert card["active_series"][-2:] == [60, 60]
    assert card["today_active"] == 60
    assert body["totals"]["today_active"] == 60


# ---- _snapshot.card:input/output 截断、quality.reuse -----------------------
def test_long_input_truncated_in_card(client, app_mod):
    app_mod.READ_AUTH_OK = True
    big = "a" * 5000
    ev(client, session_id="big", current_step="x", input=big)
    cards = client.get("/api/state").json()["sessions"]
    card = next(c for c in cards if c["session_id"] == "big")
    assert card.get("input")
    assert len(card["input"]) <= 4100  # 4000 + truncate suffix
    assert card["input"].endswith("…[truncated]")


def test_reuse_map_attached_when_skills_shared_across_operators(client):
    # 两个 operator 都用过同名 skill,quality.reuse 应被注入
    ev(client, operator="alice", session_id="a1", current_step="x",
       skills={"local": [{"name": "shared"}]})
    ev(client, operator="bob", session_id="b1", current_step="x",
       skills={"local": [{"name": "shared"}]})
    cards = client.get("/api/state").json()["sessions"]
    alice = next(c for c in cards if c["operator"] == "alice")
    assert "reuse" in alice.get("quality", {})
    assert alice["quality"]["reuse"] > 0


def test_state_now_field_present_and_iso(client):
    body = client.get("/api/state").json()
    assert isinstance(body["now"], str) and "T" in body["now"]


def test_pod_step_skips_skill_scans_without_rewriting_other_consumers(client, app_mod):
    ev(client, session_id="pod-step", status="running", current_step="tool: Bash")
    ev(client, session_id="pod-step", status="running", current_step="tool done: Bash")
    ev(client, session_id="pod-step", status="done", current_step="turn end")
    ev(client, session_id="pod-step", status="done", current_step="skill: alpha", skill="alpha")
    ev(client, session_id="pod-step", status="done", current_step="skill: beta", skill="beta")

    state = client.get("/api/state").json()
    card = next(item for item in state["sessions"] if item["session_id"] == "pod-step")
    assert card["status"] == "done"
    assert card["current_step"] == "skill: beta"
    assert card["pod_step"] == "turn end"
    feed_steps = [item["current_step"] for item in state["feed"]]
    assert "turn end" in feed_steps
    assert "skill: alpha" in feed_steps
    assert "skill: beta" in feed_steps

    detail = client.get("/api/agent/alice%3A%3Acodex").json()
    assert detail["current_step"] == "skill: beta"
    assert detail["pod_step"] == "turn end"
    agents = client.get("/api/agents").json()
    agent_row = next(item for item in agents["agents"] if item["session_id"] == "pod-step")
    assert agent_row["current_step"] == "skill: beta"
    assert agent_row["pod_step"] == "turn end"

    with app_mod.db() as conn:
        uses = conn.execute(
            "SELECT skill FROM skill_uses WHERE session_id=? ORDER BY skill",
            ("pod-step",),
        ).fetchall()
    assert [row["skill"] for row in uses] == ["alpha", "beta"]


def test_pod_step_skips_heartbeat_resume_skill_scan(client, app_mod, monkeypatch):
    app_mod.HEARTBEAT_BATCH_SECONDS = 0
    _set_ingest_times(
        monkeypatch,
        "2026-06-12T00:00:00+00:00",
        "2026-06-12T00:00:01+00:00",
        "2026-06-12T00:03:02+00:00",
    )
    ev(client, session_id="resume-scan", status="done", current_step="turn end")
    ev(client, session_id="resume-scan", status="done", current_step="skill: alpha", skill="alpha")
    ev(client, session_id="resume-scan", status="done", current_step="skill: alpha", skill="alpha")

    with app_mod.db() as conn:
        rows = conn.execute(
            "SELECT source,current_step FROM events WHERE session_id=? ORDER BY id",
            ("resume-scan",),
        ).fetchall()
    assert [(row["source"], row["current_step"]) for row in rows] == [
        ("heartbeat", "turn end"),
        ("heartbeat", "skill: alpha"),
        ("heartbeat_resume", "skill: alpha"),
    ]

    state = client.get("/api/state").json()
    card = next(item for item in state["sessions"] if item["session_id"] == "resume-scan")
    assert card["current_step"] == "skill: alpha"
    assert card["pod_step"] == "turn end"
    assert [item["current_step"] for item in state["feed"]].count("skill: alpha") == 1


def test_pod_step_does_not_borrow_from_another_session(client):
    ev(client, session_id="other-session", current_step="other session step")
    ev(client, session_id="scan-only", status="done", current_step="skill: only", skill="only")

    state = client.get("/api/state").json()
    card = next(item for item in state["sessions"] if item["session_id"] == "scan-only")
    assert card["current_step"] == "skill: only"
    assert card["pod_step"] is None


def test_snapshot_keeps_latest_session_step_and_raw_current_step(client):
    ev(client, agent="scanner", session_id="old", current_step="tool: Read")
    ev(client, agent="scanner", session_id="new", current_step="tool: Bash")
    ev(client, agent="scanner", session_id="new", status="done",
       current_step="skill: current", skill="current")

    body = client.get("/api/state").json()
    card = next(c for c in body["sessions"] if c["agent"] == "scanner")
    assert card["session_id"] == "new"
    assert card["current_step"] == "skill: current"
    assert card["pod_step"] == "tool: Bash"
    assert "display_current_step" not in card

    agents = client.get("/api/agents?w=today").json()["agents"]
    agent = next(row for row in agents if row["agent"] == "scanner")
    assert agent["current_step"] == "skill: current"
    assert agent["pod_step"] == "tool: Bash"
    assert "display_current_step" not in agent

    detail = client.get("/api/agent/alice%3A%3Ascanner").json()
    assert detail["current_step"] == "skill: current"
    assert detail["pod_step"] == "tool: Bash"
    assert "display_current_step" not in detail


def test_snapshot_skips_consecutive_skill_scans_without_n_plus_one_fallback(client):
    ev(client, agent="scanner", session_id="scans", current_step="tool: Read")
    ev(client, agent="scanner", session_id="scans", status="done",
       current_step="skill: first", skill="first")
    ev(client, agent="scanner", session_id="scans", status="done",
       current_step="skill: second", skill="second")

    body = client.get("/api/state").json()
    card = next(c for c in body["sessions"] if c["agent"] == "scanner")
    assert card["current_step"] == "skill: second"
    assert card["pod_step"] == "tool: Read"
    assert card["status"] == "done"
    assert {row["name"] for row in body["skills"]} >= {"first", "second"}


def test_snapshot_skips_empty_heartbeat_before_skill_scan(client):
    ev(client, agent="scanner", session_id="blank", current_step="tool: Read")
    ev(client, agent="scanner", session_id="blank", current_step="")
    ev(client, agent="scanner", session_id="blank", status="done",
       current_step="skill: blank", skill="blank")

    body = client.get("/api/state").json()
    card = next(c for c in body["sessions"] if c["agent"] == "scanner")
    assert card["current_step"] == "skill: blank"
    assert card["pod_step"] == "tool: Read"


def test_snapshot_skill_scan_without_previous_step_has_null_pod_step(client):
    ev(client, agent="scan-only", session_id="scan-only", status="done",
       current_step="skill: only", skill="only")

    body = client.get("/api/state").json()
    card = next(c for c in body["sessions"] if c["agent"] == "scan-only")
    assert card["current_step"] == "skill: only"
    assert card["pod_step"] is None
    assert card["status"] == "done"


def test_pod_step_preserves_real_task_and_free_step(client):
    ev(
        client,
        operator="bob",
        session_id="doctor",
        task="接入自检",
        current_step="tf-doctor",
    )

    card = next(
        item for item in client.get("/api/state").json()["sessions"]
        if item["session_id"] == "doctor"
    )
    assert card["task"] == "接入自检"
    assert card["current_step"] == "tf-doctor"
    assert card["pod_step"] == "tf-doctor"


# ---- /api/skills daily/operator_daily/funnel ----------------------------
def test_skills_overview_includes_runtime_and_operator(client):
    ev(client, session_id="s", current_step="x", skill="vis-skill")
    body = client.get("/api/skills?days=30").json()
    assert "table" in body and any(t["name"] == "vis-skill" for t in body["table"])
    assert "operator_table" in body
    assert "daily" in body
    assert "operator_daily" in body


def test_skills_overview_invalid_days_400(client):
    assert client.get("/api/skills?days=42").status_code == 400


# ---- /api/state shim 顶层信息 ---------------------------------------------
def test_state_includes_shim_version(client):
    body = client.get("/api/state").json()
    assert body["shim"]["version"]
    assert body["shim"]["files"] >= 1
