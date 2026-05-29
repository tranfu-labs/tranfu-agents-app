# Tranfu Agent Telemetry Protocol (TATP) v0.1

A tiny, vendor-neutral protocol so a team can see what everyone's AI agents are
doing in real time — regardless of whether they run Claude Code, Codex, Open Claw,
Hermes, Manus, MuleRun, ChatGPT, etc.

Field names deliberately follow the **OpenTelemetry GenAI semantic conventions**
(`gen_ai.*`) so you can later forward the same data into Grafana / Langfuse /
Datadog with zero schema migration.

---

## 1. The event

Every agent emits a small JSON event whenever its state changes: when it starts,
changes step, finishes, errors, or blocks waiting for input. One `POST` per event.

```
POST {SERVER}/v1/events
Content-Type: application/json
X-TF-Key: <接入密钥>
```

```jsonc
{
  "operator":   "bob",              // REQUIRED. which teammate (the PERSON)
  "agent":      "copy",             // optional. this teammate's named agent/lane: "copy" / "code" / "research"
  "runtime":    "open-claw",        // REQUIRED. claude-code | codex | open-claw | hermes | manus | mulerun | chatgpt ...
  "session_id": "ab12cd34",         // REQUIRED. stable per run; reuse across an agent's lifecycle
  "status":     "running",          // REQUIRED. see enum below
  "task":       "Refactor payments module",   // human-readable goal
  "current_step": "editing payments.py",       // what it's doing right now
  "ts":         "2026-05-29T10:03:00Z",        // RFC3339; server fills if omitted


  // --- optional content (the feedback-loop payload) ---
  "input":  "full prompt text ...",   // only sent when content capture is ON
  "output": "model output / diff ...",

  // --- optional free-form ---
  "meta": { "repo": "payments-svc", "branch": "feat/x" }
}
```

### `status` enum
| value     | meaning                                  |
|-----------|------------------------------------------|
| `started` | session began                            |
| `running` | actively working                         |
| `waiting` | blocked on human input / approval        |
| `blocked` | stuck (rate limit, error it can't pass)  |
| `done`    | finished successfully                    |
| `error`   | failed                                   |
| `idle`    | alive but doing nothing                  |

## Identity model — one person, several agents

Three levels of identity, so a teammate running multiple agents is the natural case:

| field        | scope        | example          | set where |
|--------------|--------------|------------------|-----------|
| `operator`   | the person   | `bob`            | global (shell profile) |
| `agent`      | a named lane | `copy`, `code`   | **per run** (wrapper `--agent`) |
| `runtime`    | the tool     | `open-claw`, `codex` | **per run** |
| `session_id` | one run      | `copy-1717…`     | auto |

So Bob's two agents are just two streams under `operator=bob`:
`bob/copy` on Open Claw and `bob/code` on Codex. The board shows them as separate
cards grouped under Bob, all under `operator=bob`. `agent` is optional — if you omit it, the board
falls back to showing the `runtime`, which is enough when each agent is a
different tool. You only *need* `agent` to tell two instances of the *same*
runtime apart (e.g. two Codex sessions, one for code and one for docs).

That's the whole protocol. Everything below is about *how each kind of agent
emits it*.

---

## 2. Three fidelity tiers

Heterogeneous agents give you different amounts of visibility. Be honest about
which tier each one is in — the dashboard renders all three.

### Tier A — hook  → 实时状态/步骤
**Claude Code** (或任何带钩子的本地 agent)。用钩子在每步上报 status/step。
见 `shims/claude-code/`。

### Tier B — wrapper  → 状态(开始/心跳/结束)
**Codex CLI, Open Claw / Claw Code, Hermes, 任意本地 CLI / API 脚本。**
用通用包装器 `tf-run`,自动发 `started` → `running` 心跳 → `done`/`error`。见 `shims/wrapper/`。

### Tier C — cloud black box  → run-level start/end only
**Manus, MuleRun, ChatGPT web.** You can't see inside these. You instrument the
*submission* point: emit `started` when you dispatch the task and `done` when it
returns (via their API/webhook if available, or a manual wrapper around your
dispatch script). No internal steps. The dashboard marks
these sessions as `coarse` so nobody mistakes silence for inactivity.

---

## 3. Privacy

Default posture: send `operator`, `runtime`, `status`, `task`, `current_step`,
and usage numbers — but **not** `input`/`output`. Content capture is opt-in via
`TF_CAPTURE_CONTENT=1` on the shim side, because you explicitly want the
feedback loop. When on, restrict dashboard read access (VPN / SSO) since
prompts and code will be visible. OpenTelemetry's own guidance is the same:
identifiers and operation names by default, full payloads opt-in.
