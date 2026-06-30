# TRANFU//AGENTS — open-source observability for AI coding agents

**TRANFU//AGENTS is a free, self-hosted, vendor-neutral dashboard that shows, in real time, what every teammate's AI agent is doing.** It tracks who is running which agent, the current step, the status, and how long each agent has been active — across Claude Code, Codex, Open Claw, Hermes, Manus, MuleRun, ChatGPT, and any other CLI agent. One team, many different agents, one live view.

> 中文一句话:TRANFU//AGENTS 是一个开源、可自托管、跨厂商的实时看板,让团队在一个页面上看到每个人的 AI agent 在干什么——谁、哪个 agent、当前到哪一步、状态、活跃了多久。支持 Claude Code、Codex、Open Claw、Hermes、Manus、MuleRun、ChatGPT 等。

*Last updated: 2026-06 · License: MIT · Status: production-ready starter · Home: https://tranfu.com*

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
- Understand **which Skills are actually adopted, and by whom**: a dedicated SKILLS page switches between skill and operator views, with continuous 7/30/90-day Asia/Shanghai timelines, hover breakdowns, used-only rankings, per-skill/per-operator drilldowns, and company catalog adoption.
- Monitor **optional downstream KEY token cost**: a separate Token Usage tab can read an existing distribution platform and show KEY spend ranking, usage trend, model mix, risk alerts, and health metrics.
- Support **one person with many agents**: each agent is labelled by purpose (for example, "copy" vs "code").
- Stay **heterogeneous by design**: local CLI agents (Claude Code, Codex, Open Claw, Hermes) report step-level detail; cloud agents (Manus, MuleRun, ChatGPT) report at start/end granularity.

## Supported agents

| Agent | Type | What the board shows |
|---|---|---|
| Claude Code | local CLI / desktop | status + current step + active time via hooks |
| Codex | local CLI / desktop | status + current step + active time via hooks or wrapper |
| Open Claw | local CLI | status + active time; optional equipped Skill reporting via native plugin |
| Hermes | local CLI | status + current step + active time via shell hooks, or wrapper fallback |
| Manus | cloud | start / end (coarse) |
| MuleRun | cloud | start / end (coarse) |
| ChatGPT | web | start / end (coarse) |

## Architecture

```
   Claude Code / Codex hooks ───┐
   Hermes shell hooks ──────────┤
   Open Claw / CLI wrapper ────tf-run wrapper──▶ server ──▶ dashboard (live)
   OpenClaw native plugin ──skill_mode=equipped─┤        status · active time · skills
   Manus / MuleRun / ChatGPT ─tf-run --coarse───┘     │
                                                     └─ SQLite store
```

## Quick start (Coolify)

```bash
cp .env.example .env      # set TF_KEY (the access key)
```

In Coolify, deploy the root `compose.yml`, set `TF_KEY`, and configure the `server` service Domain as `https://your-domain.example:8788`.
The `:8788` is the container's internal port; public traffic still uses HTTPS on 443. Full instructions are in `DEPLOY.md`.

### Optional: enable Token Usage with real distribution data

The **Token 用量** tab is isolated from the existing Pods, Agents, SKILLS, and Admin tabs. Deploying this version does not change the agent event protocol or the local SQLite telemetry store.

By default the Token Usage tab does not read your distribution platform. To show real KEY usage, set these server-side environment variables in Coolify or your runtime environment, then redeploy:

```bash
TF_TOKEN_USAGE_BASE_URL=https://api.tranfu.com
TF_TOKEN_USAGE_PATH=/api/data/keys
TF_TOKEN_USAGE_USER_ID=<distribution-platform-user-id>
TF_TOKEN_USAGE_ACCESS_TOKEN=<long-lived-read-token>
TF_TOKEN_USAGE_DEMO=0
```

If your distribution platform does not provide a long-lived read token yet, you can temporarily use a login cookie instead:

```bash
TF_TOKEN_USAGE_COOKIE=<distribution-platform-login-cookie>
TF_TOKEN_USAGE_DEMO=0
```

For production, prefer `TF_TOKEN_USAGE_ACCESS_TOKEN` or a dedicated service account token. Cookies can expire and should not be committed to GitHub, Docker images, README examples, or frontend code.

Optional tuning:

```bash
TF_TOKEN_USAGE_TIMEOUT=15
TF_TOKEN_USAGE_CACHE_TTL=90
```

After deploy, open `/token-usage`. If credentials are missing or expired, the rest of the dashboard still works; only the Token Usage tab will be unable to show real distribution usage.

Current Token Usage dashboard capabilities:

- Default view opens on **today** with an **hourly** trend.
- Top cards show spend, period-over-period change, growth rate, projected monthly spend, tokens, requests, active KEY count, failure rate, and risk KEY count.
- KEY ranking supports Top 5 / Top 10 / Top 20 with the remaining KEYs grouped as "Other".
- Clicking a KEY highlights it across the ranking, trend, model mix, table, and opens a detail drawer.
- Risk alerts cover spend spikes, high failure rate, high latency, low or exhausted quota, disabled-but-consuming KEYs, and Dapp model mismatches.
- The KEY table supports sorting, quick personal/Dapp filters, hiding zero-spend KEYs, search highlighting, and CSV export.
- The header shows freshness metadata: last update time, upstream status, and whether the response came from backend cache.

These analytics are computed from the existing distribution-platform response. No extra environment variables are required beyond the Token Usage credentials above.

Post-deploy API check:

```bash
curl -sS "https://your-domain.example/api/token-usage?days=1&time_granularity=hour" | head
```

Upgrade an existing deployment:

1. Keep the existing `TF_KEY`, SQLite volume, and agent/shim configuration unchanged.
2. Keep the Token Usage credentials configured only on the server (`TF_TOKEN_USAGE_*` variables); do not place credentials in frontend code or GitHub.
3. Deploy the new app image or rebuild the existing service from the latest tag.
4. Verify `/`, `/agents`, `/skills`, and `/token-usage` after deployment.

The Token Usage module is additive. It does not change existing Pods, Agents, SKILLS, Admin, shim install flow, or the event reporting protocol.

### Post-deploy checks for browser and Lark icons

The dashboard serves favicon, Apple touch icon, manifest, and Open Graph image files from the same domain as the app. After a deploy, verify these paths return `200` before sharing the URL in browsers or Lark:

```bash
curl -I https://your-domain.example/favicon.ico
curl -I https://your-domain.example/favicon.svg
curl -I https://your-domain.example/apple-touch-icon.png
curl -I https://your-domain.example/manifest.json
curl -I https://your-domain.example/og-image-1200x630.png
```

If Lark still shows an old preview after these checks pass, send a fresh URL or wait for Lark's link-preview cache to expire.

## How a teammate connects an agent (natural language)

A teammate just tells their own agent, in plain language:

> Install TRANFU//AGENTS from github.com/tranfu-labs/tranfu-agents-app — I'm bob, using Open Claw for copywriting.

The agent reads `SKILL.md` and self-installs. For a second agent, they say another sentence (for example, "I'm bob, using Codex for code"). Full guide in `USAGE.md`.

## Documentation

- `DEPLOY.md` — deploy the server (for the administrator).
- `USAGE.md` — install and use (for team members, natural-language flow).
- `INSTALL.md` — the one-step install runbook an agent reads and executes (auto-detects its own runtime).
- `PROTOCOL.md` — the event protocol and privacy posture.
- `SKILL.md` — agent-readable self-install skill (slim; points to `INSTALL.md`).
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

**Does it track tokens or cost?**
Core agent telemetry does not collect token or cost data. The optional Token Usage tab can display downstream KEY token cost only when you configure read-only distribution-platform credentials on the server.

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
├── server/              # FastAPI collector + React dashboard host
├── frontend/            # Vite + React + TypeScript dashboard source
└── shims/               # tf_client.sh / .py, wrapper/tf-run, claude-code/, codex/
```

## License

MIT © TranFu — https://tranfu.com
