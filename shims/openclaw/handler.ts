// TRANFU//AGENTS telemetry hook for OpenClaw (TATP v0.1).
// Self-contained: POSTs directly to {TF_SERVER}/v1/events. Fire-and-forget —
// must NEVER throw or block the Gateway (telemetry can't break the host).
//
// Identity & creds come from the Gateway process env:
//   TF_SERVER (required), TF_KEY, TF_TOKEN, TF_OPERATOR, TF_AGENT

const SERVER = (process.env.TF_SERVER || "").replace(/\/+$/, "");
const KEY = process.env.TF_KEY || "";
const TOKEN = process.env.TF_TOKEN || "";
const OPERATOR = process.env.TF_OPERATOR || process.env.USER || "unknown";
const AGENT = process.env.TF_AGENT || "";

// OpenClaw event ("type:action") -> [TATP status, current_step]
const MAP: Record<string, [string, string]> = {
  "command:new": ["started", "session start"],
  "message:received": ["running", "message in"],
  "message:sent": ["running", "message out"],   // NOT done — session is still alive
  "command:stop": ["done", "stopped"],
  "gateway:shutdown": ["done", "gateway shutdown"],
};

const handler = async (event: any) => {
  if (!SERVER) return;
  const key = `${event?.type}:${event?.action}`;
  const m = MAP[key];
  if (!m) return;
  const [status, step] = m;

  const body: Record<string, unknown> = {
    v: "0.1",
    operator: OPERATOR,
    runtime: "open-claw",
    session_id: String(event?.sessionKey ?? "openclaw"),
    status,
    current_step: step,
  };
  if (AGENT) body.agent = AGENT;

  const headers: Record<string, string> = {
    "content-type": "application/json",
    "X-TF-Key": KEY,
  };
  if (TOKEN) headers["X-TF-Token"] = TOKEN;   // per-operator attribution (TATP §4)

  try {
    await fetch(`${SERVER}/v1/events`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),       // short timeout (TATP §3)
    });
  } catch {
    // swallow — never break the Gateway
  }
};

export default handler;
