import hashlib
import importlib.util
import sqlite3
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "preview_orphan_turn_heartbeat.py"
SPEC = importlib.util.spec_from_file_location("orphan_preview", SCRIPT)
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _insert(conn, recv, status, step, last_seen=None):
    day = recv[:10]
    conn.execute(
        """INSERT INTO events
        (ts,recv,day,last_seen,operator,agent,runtime,session_id,status,current_step)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (recv, recv, day, last_seen or recv, "alice", "codex", "codex", "s1", status, step),
    )


def test_preview_scans_all_candidates_and_never_writes_source(tmp_path):
    db_path = tmp_path / "source.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""CREATE TABLE events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, recv TEXT, day TEXT,
          last_seen TEXT, operator TEXT, agent TEXT, runtime TEXT,
          session_id TEXT, status TEXT, current_step TEXT
        )""")
        _insert(conn, "2026-07-31T00:00:00+00:00", "running", "prompt")
        _insert(
            conn, "2026-07-31T00:01:00+00:00", "running", "turn heartbeat",
            "2026-08-01T00:00:00+00:00",
        )
        _insert(conn, "2026-08-01T00:01:00+00:00", "done", "turn end")
        _insert(conn, "2026-08-01T00:02:00+00:00", "running", "turn heartbeat")
        conn.commit()
    before_hash = _sha(db_path)
    before_mtime = db_path.stat().st_mtime_ns

    report = preview.build_preview(db_path, "2026-07-31", 14400)

    assert report["candidate_count"] == 1
    assert {change["action"] for change in report["candidates"][0]["changes"]} == {
        "cap_last_seen", "remove_row",
    }
    assert {change["reason"] for change in report["candidates"][0]["changes"]} == {
        "last_seen_past_activity_deadline", "after_terminal",
    }
    assert report["source"]["query_only_unchanged"] is True
    rendered = preview.render_html(report)
    assert "Candidate sessions: `1`" in rendered
    assert "&lt;html" not in rendered
    assert _sha(db_path) == before_hash
    assert db_path.stat().st_mtime_ns == before_mtime
    assert [row["day"] for row in report["daily"]] == ["2026-07-31", "2026-08-01"]


def test_preview_preserves_real_long_task_with_periodic_trusted_activity(tmp_path):
    db_path = tmp_path / "clean.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""CREATE TABLE events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, recv TEXT, day TEXT,
          last_seen TEXT, operator TEXT, agent TEXT, runtime TEXT,
          session_id TEXT, status TEXT, current_step TEXT
        )""")
        _insert(conn, "2026-08-01T00:00:00+00:00", "running", "prompt")
        _insert(conn, "2026-08-01T03:00:00+00:00", "running", "tool: exec")
        _insert(
            conn, "2026-08-01T03:01:00+00:00", "running", "turn heartbeat",
            "2026-08-01T06:30:00+00:00",
        )
        conn.commit()

    report = preview.build_preview(db_path, "2026-07-31", 14400)

    assert report["candidate_count"] == 0
    assert all(row["before_seconds"] == row["after_seconds"] for row in report["daily"])
