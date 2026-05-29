# Tranfu Agent Telemetry

See what every teammate's AI agent is doing — live — no matter which agent they
run (Claude Code, Codex, Open Claw, Hermes, Manus, MuleRun, ChatGPT…). One tiny
protocol, one collector, one dashboard. Field names follow the OpenTelemetry
GenAI conventions so you can graduate to Grafana/Langfuse later with no rework.

```
   agents (heterogeneous)            ingest                  read
   ───────────────────────          ──────                  ────
   Claude Code (hook) ───────────┐
   Codex / OpenClaw / Hermes ──tf-run wrapper──▶ server ──▶ dashboard (live)
   Manus / MuleRun / ChatGPT ──tf-run --coarse─┘     │        status · 活跃时长
                                                      └─ SQLite store
```

## What you get
- **Live board** of who's running what, current step, status, age.
- **Active-time per agent** (today / this week + 7-day sparkline).
- **Activity feed** + optional prompt/code/output capture for a feedback loop.

> 看板聚焦「谁在跑、在哪一步、状态、活跃时长」。

## Fidelity by runtime
| Runtime | Path | 可见度 |
|---|---|---|
| Claude Code (CLI/desktop) | 钩子 / `tf-run` | 状态 + 步骤 + 活跃时长 |
| Codex, Open Claw, Hermes (local CLI/API) | `tf-run` 包装器 | 状态 + 活跃时长 |
| Manus, MuleRun, ChatGPT (cloud/web) | `tf-run --coarse` | 仅开始/结束(粗粒度) |

## Run the server
```bash
# local
pip install -r server/requirements.txt
TF_KEY=secret python -m uvicorn server.app:app --host 0.0.0.0 --port 8787
# open http://localhost:8787

# or Docker (single container)
cp deploy/.env.example deploy/.env   # set TF_KEY
docker compose -f deploy/docker-compose.yml up -d
# Docker exposes http://localhost:8788
```
Deploy the container to any always-on host (Fly.io, Railway, Render, a small VPS,
Cloud Run). Put the dashboard behind your VPN/SSO if content capture is on.

## Onboard a teammate (natural language)
Because this lives in your `tranfu-skills` repo, a teammate can just tell their
agent: *"install tranfu telemetry, I'm bob on codex"* — the agent reads
`SKILL.md` and runs `install.sh`. Or manually:
```bash
curl -fsSL https://raw.githubusercontent.com/tranfu-labs/tranfu-skills/main/tranfu-agent-telemetry/install.sh \
  | bash -s -- --server https://agents.tranfu.com --key SECRET --operator bob --runtime codex
```

## Files
- `DEPLOY.md` — 部署文档(管理员)
- `USAGE.md` — 安装使用指引(团队成员)
- `PROTOCOL.md` — the event spec + fidelity tiers + privacy posture
- `SKILL.md` — agent-readable self-install (the natural-language path)
- `server/app.py` — collector + quota math + serves the dashboard
- `dashboard/index.html` — the live board (self-contained)
- `shims/` — `tf_client.sh`, `tf_client.py`, `wrapper/tf-run`, `claude-code/`
- `deploy/` — `docker-compose.yml`, `otel-collector-config.yaml`
- `install.sh` — one-shot per-machine setup

> ⚠️ Artifacts (the in-chat preview) can't host an always-on endpoint that your
> teammates' machines POST to — that's why the collector is a small deployable
> server, not an artifact. The dashboard *is* plain HTML and renders anywhere;
> the in-chat preview shows demo data when no server is reachable.
