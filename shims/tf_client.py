"""TRANFU//AGENTS — 轻量上报客户端 (Python, 仅标准库)。

    from tf_client import TF
    tf = TF(runtime="open-claw", agent="copy", task="改写文案")
    tf.emit("running", step="drafting hero")
    tf.emit("done")

环境变量: TF_SERVER, TF_KEY, TF_TOKEN, TF_OPERATOR, TF_CAPTURE_CONTENT
"""
import os, json, time, random, urllib.request

PROTOCOL_VERSION = "0.1"


class TF:
    def __init__(self, runtime="python", task=None, operator=None, session_id=None,
                 agent=None, parent_session_id=None):
        self.server = os.environ.get("TF_SERVER", "").rstrip("/")
        self.key = os.environ.get("TF_KEY", "")
        self.token = os.environ.get("TF_TOKEN", "")
        self.capture = os.environ.get("TF_CAPTURE_CONTENT", "0") == "1"
        self.base = {
            "v": PROTOCOL_VERSION,
            "operator": operator or os.environ.get("TF_OPERATOR") or os.environ.get("USER") or "unknown",
            "agent": agent or os.environ.get("TF_AGENT"),
            "runtime": runtime,
            "session_id": session_id or f"{int(time.time())}-{random.randint(1000,9999)}",
            "parent_session_id": parent_session_id or os.environ.get("TF_PARENT_SESSION"),
            "task": task,
        }

    def emit(self, status, step=None, model=None, input=None, output=None, meta=None):
        d = dict(self.base)
        d.update(status=status, current_step=step, model=model, meta=meta)
        if self.capture:
            d["input"], d["output"] = input, output
        d = {k: v for k, v in d.items() if v is not None}
        if not self.server:
            return
        headers = {"content-type": "application/json", "X-TF-Key": self.key}
        if self.token:
            headers["X-TF-Token"] = self.token
        req = urllib.request.Request(
            f"{self.server}/v1/events", data=json.dumps(d).encode(),
            headers=headers, method="POST")
        try:                              # §3 fire-and-forget; never break the host
            urllib.request.urlopen(req, timeout=5).read()
        except Exception as ex:
            print(f"[tf] emit failed: {ex}")
