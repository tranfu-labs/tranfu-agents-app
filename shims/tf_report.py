#!/usr/bin/env python3
"""
TRANFU//AGENTS — unified event emitter (stdlib only). Implements TATP v0.1.

Posts one heartbeat/event. With --profile it also auto-detects and attaches
the optional profile fields (via tf_profile.py). Used by tf_client.sh / tf-run
(on the 'started' event) and can be called directly by hooks.

  python3 tf_report.py --status running --task "改写文案" --step "drafting hero"
  python3 tf_report.py --status started --task "重构支付" --profile
  python3 tf_report.py --status running --step ... --print     # dry-run, no POST
  python3 tf_report.py enroll --operator alice                 # get a per-operator token

Transport (§3): fire-and-forget with a short timeout; on failure the event is
spooled locally (~/.tranfu/spool.ndjson) and retried — best effort, at-least-once
— before the next event. Telemetry must NEVER block or break the host agent.

Env: TF_SERVER (required to POST), TF_KEY (team write key), TF_TOKEN (per-operator
     token), TF_OPERATOR, TF_RUNTIME, TF_AGENT, TF_SESSION, TF_PARENT_SESSION,
     TF_REPORT_SKILLS=0 to suppress event-level skill usage metadata
"""
import os, sys, json, argparse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROTOCOL_VERSION = "0.1"
TIMEOUT = 5                                    # §3 short timeout
SPOOL = os.path.join(os.path.expanduser("~/.tranfu"), "spool.ndjson")
SPOOL_MAX = 1000                               # §3 bounded spool (lines)


def _headers():
    h = {"content-type": "application/json", "X-TF-Key": os.environ.get("TF_KEY", "")}
    tok = os.environ.get("TF_TOKEN", "")
    if tok:
        h["X-TF-Token"] = tok
    return h


def _post(server, payload):
    """One best-effort POST. Returns True on success, False otherwise."""
    req = urllib.request.Request(server + "/v1/events", data=json.dumps(payload).encode(),
                                 headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT):
            return True
    except Exception:
        return False


def _spool_append(payload):
    try:
        os.makedirs(os.path.dirname(SPOOL), exist_ok=True)
        with open(SPOOL, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        # keep bounded: drop oldest lines if over the cap
        with open(SPOOL, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > SPOOL_MAX:
            with open(SPOOL, "w", encoding="utf-8") as f:
                f.writelines(lines[-SPOOL_MAX:])
    except Exception:
        pass


def _flush_spool(server):
    """At-least-once: try to resend spooled events in order before the new one.
    Survives duplicates because the server dedups (§6)."""
    if not os.path.exists(SPOOL):
        return
    try:
        with open(SPOOL, encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
    except Exception:
        return
    remaining = []
    for i, ln in enumerate(lines):
        try:
            ev = json.loads(ln)
        except Exception:
            continue
        if not _post(server, ev):
            remaining = lines[i:]          # stop on first failure, keep the rest
            break
    try:
        if remaining:
            with open(SPOOL, "w", encoding="utf-8") as f:
                f.write("\n".join(remaining) + "\n")
        else:
            os.remove(SPOOL)
    except Exception:
        pass


def _enroll(server, operator):
    req = urllib.request.Request(server + "/v1/enroll",
                                 data=json.dumps({"operator": operator}).encode(),
                                 headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        print(r.read().decode())


def main():
    server = os.environ.get("TF_SERVER", "").rstrip("/")
    # subcommand: enroll
    if len(sys.argv) > 1 and sys.argv[1] == "enroll":
        op = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--operator" else \
            (os.environ.get("TF_OPERATOR") or os.environ.get("USER") or "")
        if not server or not op:
            sys.exit("enroll: need TF_SERVER and --operator <name>")
        _enroll(server, op)
        return

    ap = argparse.ArgumentParser()
    ap.add_argument("--status", required=True)
    ap.add_argument("--task", default="")
    ap.add_argument("--step", default="")
    ap.add_argument("--agent", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--input", dest="inp", default="")
    ap.add_argument("--output", dest="outp", default="")
    ap.add_argument("--session", default="")
    ap.add_argument("--parent", default="")
    ap.add_argument("--skill", default="")
    ap.add_argument("--profile", action="store_true", help="attach auto-detected profile")
    ap.add_argument("--print", dest="dry", action="store_true", help="print payload, don't POST")
    a = ap.parse_args()

    op = os.environ.get("TF_OPERATOR") or os.environ.get("USER") or "unknown"
    rt = os.environ.get("TF_RUNTIME", "cli")
    agent = a.agent or os.environ.get("TF_AGENT") or ""
    sess = a.session or os.environ.get("TF_SESSION") or f"{rt}-{os.getpid()}"
    parent = a.parent or os.environ.get("TF_PARENT_SESSION") or ""

    payload = {"v": PROTOCOL_VERSION, "operator": op, "runtime": rt,
               "session_id": sess, "status": a.status}
    if agent:
        payload["agent"] = agent
    if parent:
        payload["parent_session_id"] = parent
    if a.task:
        payload["task"] = a.task
    if a.step:
        payload["current_step"] = a.step
    if a.model:
        payload["model"] = a.model
    if a.inp:
        payload["input"] = a.inp
    if a.outp:
        payload["output"] = a.outp
    if a.skill.strip() and os.environ.get("TF_REPORT_SKILLS") != "0":
        payload["skill"] = a.skill.strip()

    if a.profile:
        try:
            import tf_profile
            payload.update(tf_profile.collect(runtime=rt))
        except Exception:
            pass  # detection must never break reporting

    if a.dry or not server:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # §3: flush any backlog first, then send; on failure spool (at-least-once).
    _flush_spool(server)
    if not _post(server, payload):
        _spool_append(payload)


if __name__ == "__main__":
    main()
