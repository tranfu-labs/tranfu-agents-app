#!/usr/bin/env python3
"""Read-only preview for unsupported synthetic turn-heartbeat history."""
import argparse
import hashlib
import html
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo


ACTIVE_ST = frozenset({"running", "started", "waiting", "blocked"})
TERMINAL_ST = frozenset({"done", "error", "idle"})
SYNTHETIC_STEPS = frozenset({"turn heartbeat"})
STATS_TZ = ZoneInfo("Asia/Shanghai")
ACTIVE_SEGMENT_GAP_SECONDS = 900


def _parse(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _iso(value):
    return value.isoformat()


def _hms(seconds):
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def _is_synthetic(row):
    return row["status"] == "running" and (row["current_step"] or "") in SYNTHETIC_STEPS


def _intervals(rows):
    intervals = []
    active_start = active_last = None
    for row in rows:
        event_time = _parse(row["rt_time"])
        last_seen = max(event_time, _parse(row["ls"]))
        if (active_start is not None
                and (event_time - active_last).total_seconds() > ACTIVE_SEGMENT_GAP_SECONDS):
            if active_last > active_start:
                intervals.append((active_start, active_last))
            active_start = active_last = None
        if row["status"] in ACTIVE_ST:
            if active_start is None:
                active_start = event_time
            active_last = max(active_last or event_time, last_seen)
        elif row["status"] in TERMINAL_ST and active_start is not None:
            if event_time > active_start:
                intervals.append((active_start, event_time))
            active_start = active_last = None
    if active_start is not None and active_last > active_start:
        intervals.append((active_start, active_last))
    return intervals


def _bucket(rows):
    result = defaultdict(float)
    for start, end in _intervals(rows):
        current = start.astimezone(STATS_TZ)
        end = end.astimezone(STATS_TZ)
        while current < end:
            day_end = datetime.combine(
                current.date() + timedelta(days=1), datetime.min.time(), STATS_TZ,
            )
            segment_end = min(end, day_end)
            result[current.date().isoformat()] += (segment_end - current).total_seconds()
            current = segment_end
    return result


def _correct_session(rows, max_silence_seconds):
    corrected = []
    changes = []
    trusted_anchor = None
    terminal = False
    terminal_row_id = None
    for raw in rows:
        row = dict(raw)
        if _is_synthetic(row):
            reason = None
            cutoff = None
            if terminal:
                reason = "after_terminal"
            elif trusted_anchor is None:
                reason = "no_trusted_activity"
            else:
                cutoff = trusted_anchor + timedelta(seconds=max_silence_seconds)
                if _parse(row["rt_time"]) > cutoff:
                    reason = "after_activity_deadline"
                elif _parse(row["ls"]) > cutoff:
                    original = row["ls"]
                    row["ls"] = _iso(cutoff)
                    changes.append({
                        "row_id": row["id"],
                        "action": "cap_last_seen",
                        "reason": "last_seen_past_activity_deadline",
                        "recv": row["rt_time"],
                        "original_last_seen": original,
                        "corrected_last_seen": row["ls"],
                        "cutoff": _iso(cutoff),
                        "terminal_row_id": terminal_row_id,
                    })
            if reason:
                changes.append({
                    "row_id": row["id"],
                    "action": "remove_row",
                    "reason": reason,
                    "recv": row["rt_time"],
                    "original_last_seen": row["ls"],
                    "corrected_last_seen": None,
                    "cutoff": _iso(cutoff) if cutoff else None,
                    "terminal_row_id": terminal_row_id,
                })
                continue
            corrected.append(row)
            continue
        corrected.append(row)
        if row["status"] in ACTIVE_ST:
            trusted_anchor = _parse(row["rt_time"])
            terminal = False
            terminal_row_id = None
        elif row["status"] in TERMINAL_ST:
            terminal = True
            terminal_row_id = row["id"]
    return corrected, changes


def _merge(target, values):
    for day, seconds in values.items():
        target[day] += seconds


def _session_rows(conn):
    query = """SELECT id,operator,COALESCE(agent,runtime) agent,runtime,session_id,
        status,current_step,COALESCE(recv,ts) rt_time,
        COALESCE(last_seen,recv,ts) ls
      FROM events
      ORDER BY operator,COALESCE(agent,runtime),runtime,session_id,id"""
    current_key = None
    rows = []
    for row in conn.execute(query):
        key = (row["operator"], row["agent"], row["runtime"], row["session_id"])
        if current_key is not None and key != current_key:
            yield current_key, rows
            rows = []
        current_key = key
        rows.append(row)
    if rows:
        yield current_key, rows


def _file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_preview(db_path, start_day="2026-07-31", max_silence_seconds=14400):
    path = Path(db_path).expanduser().resolve()
    before_hash = _file_sha256(path)
    before_stat = path.stat()
    uri = f"file:{quote(str(path))}?mode=ro"
    before_by_identity = defaultdict(lambda: defaultdict(float))
    after_by_identity = defaultdict(lambda: defaultdict(float))
    candidates = []
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        for key, rows in _session_rows(conn):
            corrected, changes = _correct_session(rows, max_silence_seconds)
            before = _bucket(rows)
            after = _bucket(corrected)
            identity = (key[0], key[1])
            _merge(before_by_identity[identity], before)
            _merge(after_by_identity[identity], after)
            if not changes:
                continue
            session_days = sorted(set(before) | set(after))
            candidates.append({
                "operator": key[0],
                "agent": key[1],
                "runtime": key[2],
                "session_id": key[3],
                "reasons": sorted({change["reason"] for change in changes}),
                "changes": changes,
                "daily": [
                    {
                        "day": day,
                        "before_seconds": round(before.get(day, 0)),
                        "after_seconds": round(after.get(day, 0)),
                        "delta_seconds": round(after.get(day, 0) - before.get(day, 0)),
                    }
                    for day in session_days
                    if day >= start_day and round(before.get(day, 0) - after.get(day, 0))
                ],
            })
    after_hash = _file_sha256(path)
    after_stat = path.stat()
    all_days = {
        day
        for identities in (before_by_identity, after_by_identity)
        for values in identities.values()
        for day in values
    }
    days = sorted(day for day in all_days if day >= start_day)
    daily = []
    for day in days:
        # The Agents API rounds each final identity's daily series first, then
        # sums those integer segments. Mirroring that order keeps the preview
        # exact at one-second boundaries.
        before = sum(round(values.get(day, 0)) for values in before_by_identity.values())
        after = sum(round(values.get(day, 0)) for values in after_by_identity.values())
        daily.append({
            "day": day,
            "before_seconds": before,
            "before_hms": _hms(before),
            "after_seconds": after,
            "after_hms": _hms(after),
            "delta_seconds": after - before,
            "delta_hms": "-" + _hms(before - after) if after < before else _hms(after - before),
        })
    return {
        "source": {
            "path": str(path),
            "sha256_before": before_hash,
            "sha256_after": after_hash,
            "size_before": before_stat.st_size,
            "size_after": after_stat.st_size,
            "mtime_ns_before": before_stat.st_mtime_ns,
            "mtime_ns_after": after_stat.st_mtime_ns,
            "query_only_unchanged": (
                before_hash == after_hash
                and before_stat.st_size == after_stat.st_size
                and before_stat.st_mtime_ns == after_stat.st_mtime_ns
            ),
        },
        "policy": {
            "synthetic_steps": sorted(SYNTHETIC_STEPS),
            "max_silence_seconds": max_silence_seconds,
            "active_segment_gap_seconds": ACTIVE_SEGMENT_GAP_SECONDS,
            "stats_timezone": str(STATS_TZ),
            "start_day": start_day,
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
        "daily": daily,
    }


def render_markdown(report):
    lines = [
        "# Orphan turn-heartbeat correction preview",
        "",
        f"- Source: `{report['source']['path']}`",
        f"- SHA-256: `{report['source']['sha256_before']}`",
        f"- Query-only unchanged: `{str(report['source']['query_only_unchanged']).lower()}`",
        f"- Candidate sessions: `{report['candidate_count']}`",
        "",
        "## Daily before / after",
        "",
        "| Day | Before | After | Delta |",
        "|---|---:|---:|---:|",
    ]
    for row in report["daily"]:
        lines.append(
            f"| {row['day']} | {row['before_hms']} | {row['after_hms']} | {row['delta_hms']} |",
        )
    lines += ["", "## All candidate sessions", ""]
    for index, candidate in enumerate(report["candidates"], 1):
        lines += [
            f"### {index}. `{candidate['session_id']}`",
            "",
            f"- Identity: `{candidate['operator']} / {candidate['agent']} / {candidate['runtime']}`",
            f"- Reasons: `{', '.join(candidate['reasons'])}`",
            "",
            "| Row | Action | Reason | recv | Original last_seen | Corrected last_seen |",
            "|---:|---|---|---|---|---|",
        ]
        for change in candidate["changes"]:
            lines.append(
                "| {row_id} | {action} | {reason} | {recv} | {original_last_seen} | {corrected} |".format(
                    corrected=change["corrected_last_seen"] or "—", **change,
                ),
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def render_html(report):
    title = "Orphan turn-heartbeat correction preview"
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{title}</title><style>
body{{margin:0 auto;max-width:1200px;padding:24px;font:14px/1.5 ui-monospace,monospace;color:#202124}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
</style></head><body><pre>{content}</pre></body></html>
""".format(title=html.escape(title), content=html.escape(render_markdown(report)))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("db")
    parser.add_argument("--start-day", default="2026-07-31")
    parser.add_argument("--max-silence-seconds", type=int, default=14400)
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    parser.add_argument("--html-output")
    args = parser.parse_args(argv)
    report = build_preview(args.db, args.start_day, args.max_silence_seconds)
    if args.json_output:
        Path(args.json_output).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    if args.markdown_output:
        Path(args.markdown_output).write_text(render_markdown(report), encoding="utf-8")
    if args.html_output:
        Path(args.html_output).write_text(render_html(report), encoding="utf-8")
    if not args.json_output and not args.markdown_output and not args.html_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({
            "candidate_count": report["candidate_count"],
            "query_only_unchanged": report["source"]["query_only_unchanged"],
            "daily": report["daily"],
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
