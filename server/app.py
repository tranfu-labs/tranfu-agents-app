"""
Tranfu Agent Telemetry — collector server.

Two ingest paths into one store:
  POST /v1/events        JSON heartbeat (all agents via shim)

Read paths:
  GET  /api/state        current snapshot the dashboard polls
  GET  /                 the dashboard
  GET  /healthz

Storage is SQLite (file at $TF_DB, default ./tf.db). No external services.
"""
import os, json, sqlite3, time, threading
from datetime import datetime, timezone, date, timedelta
from contextlib import closing
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse

DB_PATH = os.environ.get("TF_DB", "tf.db")
INGEST_KEY = os.environ.get("TF_KEY", "")          # "" = no auth (dev only)
DASH_PATH = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")

app = FastAPI(title="Tranfu Agent Telemetry")
_lock = threading.Lock()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(db()) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT, day TEXT,
          operator TEXT, agent TEXT, runtime TEXT, session_id TEXT,
          status TEXT, task TEXT, current_step TEXT,
          model TEXT,
          input TEXT, output TEXT, meta TEXT, source TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ev_session ON events(operator, runtime, session_id, id);
        CREATE INDEX IF NOT EXISTS idx_ev_day ON events(day, operator, runtime);
        """)
        conn.commit()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def check_auth(key):
    if INGEST_KEY and key != INGEST_KEY:
        raise HTTPException(status_code=401, detail="bad ingest key")


# ---------------------------------------------------------------- ingest: heartbeat
@app.post("/v1/events")
async def ingest_event(request: Request, x_tf_key: str = Header(default="")):
    check_auth(x_tf_key)
    e = await request.json()
    if not all(e.get(k) for k in ("operator", "runtime", "session_id", "status")):
        raise HTTPException(400, "operator, runtime, session_id, status are required")
    ts = e.get("ts") or now_iso()
    row = (
        ts, ts[:10], e["operator"], e.get("agent"), e["runtime"], e["session_id"],
        e["status"], e.get("task"), e.get("current_step"),
        e.get("model"), e.get("input"), e.get("output"),
        json.dumps(e.get("meta")) if e.get("meta") else None, "heartbeat",
    )
    with _lock, closing(db()) as conn:
        conn.execute("""INSERT INTO events
          (ts,day,operator,agent,runtime,session_id,status,task,current_step,model,
           input,output,meta,source)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row)
        conn.commit()
    return {"ok": True}


# ---------------------------------------------------------------- read: snapshot
CLOUD_RUNTIMES = {"manus", "mulerun", "chatgpt"}
STALE_SECONDS = 180  # no event in 3 min -> mark idle


def _age(ts):
    try:
        return time.time() - datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 1e9


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def active_durations(conn):
    """Active running time per (operator, agent|runtime), bucketed by UTC day.
    Active = time between started/running and the next done/error/idle (or now,
    if the session is still alive). Returns today_sec, week_sec (ISO week, Mon),
    and a 7-day series (today-6 .. today) for the sparkline."""
    now = datetime.now(timezone.utc)
    today = now.date()
    win_start = (today - timedelta(days=6)).isoformat()
    rows = conn.execute("""SELECT operator, COALESCE(agent,runtime) k, runtime, session_id, status, ts
        FROM events WHERE day >= ? ORDER BY operator, k, session_id, id""", (win_start,)).fetchall()
    buckets = {}  # key "op\x00k" -> {dayiso: seconds}

    def add(key, a, b):
        if b <= a:
            return
        d = buckets.setdefault(key, {})
        cur = a
        while cur < b:
            day = cur.date()
            day_end = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)
            seg = min(b, day_end)
            d[day.isoformat()] = d.get(day.isoformat(), 0) + (seg - cur).total_seconds()
            cur = seg

    # group rows by (operator, k, session_id)
    cur_sess = None
    active_start = last_ts = None
    key = None
    def flush():
        nonlocal active_start
        if active_start is not None and last_ts is not None:
            end = now if (now - last_ts).total_seconds() < STALE_SECONDS else last_ts
            add(key, active_start, end)
        active_start = None

    for r in rows:
        sk = (r["operator"], r["k"], r["session_id"])
        if sk != cur_sess:
            flush()
            cur_sess = sk
            key = r["operator"] + "\x00" + (r["k"] or "")
            active_start = last_ts = None
        t = _parse(r["ts"])
        last_ts = t
        st = r["status"]
        if st in ("running", "started", "waiting"):
            if active_start is None:
                active_start = t
        elif st in ("done", "error", "idle"):
            if active_start is not None:
                add(key, active_start, t); active_start = None
    flush()

    week_start = (today - timedelta(days=today.weekday())).isoformat()
    days7 = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    out = {}
    for key, d in buckets.items():
        out[key] = {
            "today": round(d.get(today.isoformat(), 0)),
            "week": round(sum(v for day, v in d.items() if day >= week_start)),
            "series": [round(d.get(day, 0)) for day in days7],
        }
    return out


@app.get("/api/state")
def state():
    with closing(db()) as conn:
        sessions = conn.execute("""
          SELECT e.* FROM events e
          JOIN (SELECT operator,runtime,session_id,MAX(id) mid FROM events
                WHERE source='heartbeat' GROUP BY operator,runtime,session_id) last
          ON e.id = last.mid ORDER BY e.operator ASC, e.id DESC LIMIT 80""").fetchall()
        feed = conn.execute("""SELECT * FROM events WHERE source='heartbeat'
          ORDER BY id DESC LIMIT 40""").fetchall()
        durations = active_durations(conn)

    def card(r):
        d = dict(r)
        d["meta"] = json.loads(d["meta"]) if d.get("meta") else None
        d["fidelity"] = "coarse" if r["runtime"] in CLOUD_RUNTIMES else "full"
        dk = r["operator"] + "\x00" + ((r["agent"] if "agent" in r.keys() else None) or r["runtime"] or "")
        dur = durations.get(dk, {"today": 0, "week": 0, "series": [0] * 7})
        d["today_active"], d["week_active"], d["active_series"] = dur["today"], dur["week"], dur["series"]
        st = r["status"]
        if st in ("running", "started") and _age(r["ts"]) > STALE_SECONDS:
            st = "idle"
        d["status"] = st
        for big in ("input", "output"):
            if d.get(big) and len(d[big]) > 4000:
                d[big] = d[big][:4000] + "…[truncated]"
        return d

    cards = [card(r) for r in sessions]
    live = [c for c in cards if c["status"] in ("running", "started", "waiting")]
    ops = {c["operator"] for c in cards}
    agents = {(c["operator"], (c.get("agent") or c["runtime"])) for c in cards}
    return JSONResponse({
        "now": now_iso(),
        "sessions": cards,
        "feed": [card(r) for r in feed],
        "totals": {
            "live": len(live), "operators": len(ops), "agents": len(agents),
            "today_active": sum(v["today"] for v in durations.values()),
        },
    })


@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


@app.get("/")
def dashboard():
    try:
        with open(os.path.abspath(DASH_PATH), encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>dashboard/index.html not found</h1>", status_code=404)


init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8787")))
