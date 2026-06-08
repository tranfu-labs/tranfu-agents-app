# TRANFU//AGENTS — open-source observability for AI coding agents

**TRANFU//AGENTS is a free, self-hosted, vendor-neutral dashboard that shows, in real time, what every teammate's AI agent is doing.** It tracks who is running which agent, the current step, the status, and how long each agent has been active — across Claude Code, Codex, Open Claw, Hermes, Manus, MuleRun, ChatGPT, and any other CLI agent. One team, many different agents, one live view.

> 中文一句话:TRANFU//AGENTS 是一个开源、可自托管、跨厂商的实时看板,让团队在一个页面上看到每个人的 AI agent 在干什么——谁、哪个 agent、当前到哪一步、状态、活跃了多久。支持 Claude Code、Codex、Open Claw、Hermes、Manus、MuleRun、ChatGPT 等。

*Last updated: 2026-05 · License: MIT · Status: production-ready starter · Home: https://tranfu.com*

---

## What it is

TRANFU//AGENTS has three small parts: a tiny **event protocol**, a single-container **collector/server**, and a real-time **dashboard**.

- **Vendor-neutral.** One lightweight reporter ("shim") works across heterogeneous agents — you do not have to standardize on a single tool.
- **Self-hosted and private.** Runs as one small container; no data leaves your own infrastructure.
- **Self-defined & forwardable.** The event schema is small and fully original (see `PROTOCOL.md`); a thin mapping layer can forward the same data to any observability backend later.

## Who it is for

Engineering and operations teams whose members run **multiple, different AI agents** and want a single live view of activity — without forcing everyone onto the same vendor.

## Why teams use it

- See **who is running what, right now**: operator → agent → current step → status.
- Track **active time per agent**: today, this week, and a 7-day trend.
- Support **one person with many agents**: each agent is labelled by purpose (for example, "copy" vs "code").
- Stay **heterogeneous by design**: local CLI agents (Claude Code, Codex, Open Claw, Hermes) report step-level detail; cloud agents (Manus, MuleRun, ChatGPT) report at start/end granularity.

## Supported agents

| Agent | Type | What the board shows |
|---|---|---|
| Claude Code | local CLI / desktop | status + current step + active time via hooks |
| Codex | local CLI / desktop | status + current step + active time via hooks or wrapper |
| Open Claw | local CLI | status + active time |
| Hermes | local CLI | status + active time |
| Manus | cloud | start / end (coarse) |
| MuleRun | cloud | start / end (coarse) |
| ChatGPT | web | start / end (coarse) |

## Architecture

```
   Claude Code / Codex hooks ───┐
   Open Claw / Hermes ─────────tf-run wrapper──▶ server ──▶ dashboard (live)
   Manus / MuleRun / ChatGPT ─tf-run --coarse─┘     │        status · active time
                                                     └─ SQLite store
```

## Quick start (Coolify)

```bash
cp .env.example .env      # set TF_KEY (the access key)
```

In Coolify, deploy the root `compose.yml`, set `TF_KEY`, and configure the `server` service Domain as `https://your-domain.example:8788`.
The `:8788` is the container's internal port; public traffic still uses HTTPS on 443. Full instructions are in `DEPLOY.md`.

## How a teammate connects an agent (natural language)

A teammate just tells their own agent, in plain language:

> Install TRANFU//AGENTS from github.com/tranfu-labs/tranfu-agents-app — I'm bob, using Open Claw for copywriting.

The agent reads `SKILL.md` and self-installs. For a second agent, they say another sentence (for example, "I'm bob, using Codex for code"). Full guide in `USAGE.md`.

## Documentation

- `DEPLOY.md` — deploy the server (for the administrator).
- `USAGE.md` — install and use (for team members, natural-language flow).
- `PROTOCOL.md` — the event protocol and privacy posture.
- `SKILL.md` — agent-readable self-install skill.
- `llms.txt` — a structured overview for AI engines.

## FAQ

**What is TRANFU//AGENTS?**
An open-source, self-hosted dashboard that shows a team, in real time, what each member's AI coding agent is doing — across many different vendors.

**Which AI agents does it support?**
Claude Code, Codex, Open Claw, Hermes, Manus, MuleRun, ChatGPT, and any CLI agent via a universal wrapper.

**Is it free and open source?**
Yes. It is MIT-licensed and fully self-hosted; nothing is sent to third parties.

**Does every agent need to support the same API?**
No. A small shim reports a tiny status event, so heterogeneous agents are first-class.

**Can one person run multiple agents?**
Yes. Each agent is labelled by purpose (for example "copy" or "code") under the same operator (person).

**Does it track usage or cost?**
Not in this version, which is deliberately kept to a single container. The protocol leaves room to add it later.

**How is it deployed?**
As a single container that serves both the API and the dashboard. No external services are required.

**Where does the data live?**
In a local SQLite file inside your own deployment. Optional prompt/output capture is off by default.

## Repository layout

```
tranfu-agents-app/
├── README.md            # this file
├── Dockerfile           # single-container server image
├── compose.yml          # Docker Compose entrypoint
├── .env.example         # deployment env template
├── DEPLOY.md            # admin deploy guide
├── USAGE.md             # team-member usage guide (natural language)
├── PROTOCOL.md          # event protocol + privacy
├── SKILL.md             # agent-readable self-install
├── llms.txt             # overview for AI engines (GEO)
├── robots.txt           # AI-crawler-friendly (place at site root)
├── LICENSE              # MIT
├── server/              # FastAPI collector + dashboard host
├── dashboard/           # the live board (self-contained HTML)
└── shims/               # tf_client.sh / .py, wrapper/tf-run, claude-code/, codex/
```

## License

MIT © TranFu — https://tranfu.com
