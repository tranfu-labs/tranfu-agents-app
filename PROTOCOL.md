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
**Claude Code / Codex** (或任何带钩子的本地 agent)。用钩子在每步上报 status/step。
见 `shims/claude-code/` 与 `shims/codex/`。

### Tier B — wrapper  → 状态(开始/心跳/结束)
**Open Claw / Claw Code, Hermes, 任意本地 CLI / API 脚本;Codex 也可用此方式临时包装。**
用通用包装器 `tf-run`,自动发 `started` → `running` 心跳 → `done`/`error`。见 `shims/wrapper/`。

### Tier C — cloud black box  → run-level start/end only
**Manus, MuleRun, ChatGPT web.** You can't see inside these. You instrument the
*submission* point: emit `started` when you dispatch the task and `done` when it
returns (via their API/webhook if available, or a manual wrapper around your
dispatch script). No internal steps. The dashboard marks
these sessions as `coarse` so nobody mistakes silence for inactivity.

---

## 2.5 Optional profile fields (for the agent detail / governance page)

Any event MAY also carry a few **optional profile fields**. The server keeps the
**latest** one per agent identity (`operator`+`agent`+`runtime`) and shows them on
the agent detail page. They're all optional — send what you can read locally.

```jsonc
{
  // ... the core event fields above ...
  "models":   ["claude-opus-4-6", "gpt-4o"],          // models in use
  "config":   { "temperature": 0.4, "sandbox": "read-only" },  // key params
  "mcp":      ["figma", "github"],                    // connected MCP servers
  "skills":   { "local":  [{"name":"prd-to-wireframe","desc":"需求→框架"}],
                "cross":  [{"name":"组件命名规范","desc":"三段式"}],
                "pitfalls":["别用红底白字"] },
  "integrations": [{"name":"Figma","desc":"读写设计稿"}],       // tools & what they do
  "about":    "一句话需求 → 低保真原型",               // what this agent is good at
  "tips":     "先说清谁用、要完成什么动作",            // dispatcher's how-to-use note
  "cf":       { "ver":"Open Claw v1.4", "role":"品牌文案执行体",
                "location":"~/work/copy", "terminal":"zsh", "ims":["飞书"] },

  // --- sensitive, OPT-IN only (more content leaves the machine) ---
  "instructions": "完整系统提示 ...",                  // opt-in
  "memory":   { "file":"~/.claude/CLAUDE.md", "updated": 7200,
                "conventions":["命名三段式"], "learned":["hero 浅底深字转化更高"] }  // opt-in
}
```

**Computed by the server, never reported:** the quality block
(`runs / success / error / avg_sec / auto_rate`) is derived from event history,
and `reuse` is derived from cross-operator skill overlap. Leverage
(`assets`, `skills_week`) is derived from the skills the team has reported.
The shim should NOT try to compute these.

`instructions` and `memory` are sensitive (they expose how the agent is wired and
what it has learned). Treat them like `input`/`output`: **opt-in**, and restrict
dashboard read access when enabled.

---

## 3. Privacy

Default posture: send `operator`, `runtime`, `status`, `task`, `current_step`,
and usage numbers — but **not** `input`/`output`. Content capture is opt-in via
`TF_CAPTURE_CONTENT=1` on the shim side, because you explicitly want the
feedback loop. When on, restrict dashboard read access (VPN / SSO) since
prompts and code will be visible. OpenTelemetry's own guidance is the same:
identifiers and operation names by default, full payloads opt-in.
