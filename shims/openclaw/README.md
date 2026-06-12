# TRANFU OpenClaw Skill Reporter

Native OpenClaw plugin for the `openclaw-equipped-skill-usage` change.

It observes `llm_input`, extracts only skill names from OpenClaw's compact skill XML block, and reports each session's deduped names to TRANFU//AGENTS as `skill_mode=equipped`.

It never logs or posts prompt text, skill descriptions, parameters, code, or model output. Diagnostics are written to `~/.tranfu/logs/openclaw-skill.log`.

## Runtime behavior

- `llm_input` reads the system prompt shape OpenClaw gives the plugin and keeps a per-session set of extracted skill names.
- `session_end` schedules one background POST per deduped skill and returns immediately. Network errors, timeouts, missing config, and parser drift are swallowed so telemetry cannot break the host agent.
- The local log writes a `session_end` summary after the background POSTs settle, including `llmInputs`, `promptMissing`, `blockSeen`, `driftWarnings`, `skillCount`, `postOk`, and `postFail`.
- `flush()` in `reporter.mjs` is for tests only. The production plugin does not wait for it.

## Config

The installer writes plugin config from the same values as the normal TRANFU shim:

- `server`: collector base URL.
- `key`: team write key, sent as `X-TF-Key`.
- `operator`: teammate name.
- `agent`: optional lane name.
- `runtime`: defaults to `open-claw`.
- `reportSkills`: optional; `false` or `TF_REPORT_SKILLS=0` disables equipped skill reporting.

## Verification

Local unit checks:

```bash
node --check shims/openclaw/index.js shims/openclaw/reporter.mjs shims/openclaw/skill-extract.mjs shims/openclaw/logger.mjs
node --test tests/test_openclaw_skill_reporter.mjs
```

True-machine verification still has to confirm the exact OpenClaw `llm_input` payload shape and injected skill XML shape before broad rollout.
