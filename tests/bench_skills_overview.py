"""Synthetic `/api/skills` benchmark helper.

This is not a pytest test. Run it manually when changing SKILLS overview
aggregation logic:

    python tests/bench_skills_overview.py --rows 300000 --reps 5
"""
import argparse
import os
import random
import tempfile
import time
import sys
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=300_000)
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    os.environ["TF_DB"] = tmp.name
    os.environ.setdefault("TF_SKILLS_CATALOG_SYNC", "0")

    from server.db import db, init_db
    from server.routes.board import skills_overview

    rng = random.Random(args.seed)
    base = date(2026, 7, 2)
    runtimes = ["codex", "claude-code", "hermes", "open-claw"]

    try:
        init_db()
        with closing(db()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO catalog_cache(id,json,fetched_at) VALUES(1,?,?)",
                ('{"items":[]}', "2026-07-02T00:00:00+00:00"),
            )
            batch = []
            for i in range(args.rows):
                day = (base - timedelta(days=rng.randrange(0, 180))).isoformat()
                batch.append((
                    f"s{i // 2}",
                    f"skill{i % 900}",
                    "used",
                    f"op{i % 40}",
                    runtimes[i % len(runtimes)],
                    day,
                    f"{day}T00:00:00+00:00",
                ))
                if len(batch) >= 5000:
                    conn.executemany(
                        """INSERT OR IGNORE INTO skill_uses
                          (session_id,skill,mode,operator,runtime,day,first_seen)
                          VALUES(?,?,?,?,?,?,?)""",
                        batch,
                    )
                    batch.clear()
            if batch:
                conn.executemany(
                    """INSERT OR IGNORE INTO skill_uses
                      (session_id,skill,mode,operator,runtime,day,first_seen)
                      VALUES(?,?,?,?,?,?,?)""",
                    batch,
                )
            conn.commit()

            skills_overview(conn, 30, "7d")
            timings = []
            for _ in range(args.reps):
                start = time.perf_counter()
                payload = skills_overview(conn, 30, "7d")
                timings.append(time.perf_counter() - start)

            timings.sort()
            avg = sum(timings) / len(timings)
            print(
                "rows={rows} best={best:.3f}s avg={avg:.3f}s p95~={p95:.3f}s "
                "table={table} op_table={op_table}".format(
                    rows=args.rows,
                    best=timings[0],
                    avg=avg,
                    p95=timings[-1],
                    table=len(payload["table"]),
                    op_table=len(payload["operator_table"]),
                )
            )

            explain = conn.execute(
                """EXPLAIN QUERY PLAN
                SELECT day, operator, skill, COALESCE(runtime,'') runtime, COUNT(*) sessions
                FROM skill_uses
                WHERE mode='used' AND day IS NOT NULL AND day >= ?
                  AND trim(COALESCE(operator,'')) <> ''
                GROUP BY day, operator, skill, runtime""",
                ("2026-06-19",),
            ).fetchall()
            print("operator_daily_plan=", [tuple(row) for row in explain])
    finally:
        for suffix in ("", "-shm", "-wal"):
            try:
                os.unlink(tmp.name + suffix)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
