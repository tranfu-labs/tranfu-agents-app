"""board 域:metrics 分支、_snapshot.card 边界、/api/agent /api/operator /api/skill。
对应 server/app.py 的 metrics / _snapshot / agent_detail / operator_detail / skill_detail。
由 add-server-app-test-baseline 引入。
"""
from datetime import datetime, timezone

from conftest import ev


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
