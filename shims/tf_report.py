#!/usr/bin/env python3
"""
TRANFU//AGENTS — unified event emitter (stdlib only).

Posts one heartbeat/event. With --profile it also auto-detects and attaches
the optional profile fields (via tf_profile.py). Used by tf_client.sh / tf-run
(on the 'started' event) and can be called directly by hooks.

  python3 tf_report.py --status running --task "改写文案" --step "drafting hero"
  python3 tf_report.py --status started --task "重构支付" --profile
  python3 tf_report.py --status running --step ... --print     # dry-run, no POST

Env: TF_SERVER (required to POST), TF_KEY, TF_OPERATOR, TF_RUNTIME, TF_AGENT, TF_SESSION
"""
import os, sys, json, argparse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", required=True)
    ap.add_argument("--task", default="")
    ap.add_argument("--step", default="")
    ap.add_argument("--agent", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--input", dest="inp", default="")
    ap.add_argument("--output", dest="outp", default="")
    ap.add_argument("--session", default="")
    ap.add_argument("--profile", action="store_true", help="attach auto-detected profile")
    ap.add_argument("--print", dest="dry", action="store_true", help="print payload, don't POST")
    a = ap.parse_args()

    server = os.environ.get("TF_SERVER", "").rstrip("/")
    key = os.environ.get("TF_KEY", "")
    op = os.environ.get("TF_OPERATOR") or os.environ.get("USER") or "unknown"
    rt = os.environ.get("TF_RUNTIME", "cli")
    agent = a.agent or os.environ.get("TF_AGENT") or ""
    sess = a.session or os.environ.get("TF_SESSION") or f"{rt}-{os.getpid()}"

    payload = {"operator": op, "runtime": rt, "session_id": sess, "status": a.status}
    if agent:
        payload["agent"] = agent
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

    if a.profile:
        try:
            import tf_profile
            payload.update(tf_profile.collect(runtime=rt))
        except Exception:
            pass  # detection must never break reporting

    if a.dry or not server:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    data = json.dumps(payload).encode()
    req = urllib.request.Request(server + "/v1/events", data=data,
        headers={"content-type": "application/json", "X-TF-Key": key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception as e:
        sys.stderr.write(f"tf_report: post failed: {e}\n")


if __name__ == "__main__":
    main()
