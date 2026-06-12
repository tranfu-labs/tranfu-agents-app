#!/usr/bin/env bash
# One-shot installer for a teammate's machine. Installs the shim clients to
# ~/.tranfu, records this agent's identity, and registers it on the board
# (sends one profile-bearing event so the card AND detail page populate).
#
#   curl -fsSL https://tranfu-agents-app.tranfu.com/install.sh | bash -s -- \
#       --server https://tranfu-agents-app.tranfu.com --key SECRET \
#       --operator nezha --runtime hermes --agent "多儿" --role "哪吒的 Lark 助手,写文档/调研"
#
# --models "MiniMax-M2": label this agent's model(s), comma-separated. Optional —
#   per-runtime, so it never leaks across co-resident agents. Omit it and the
#   model is auto-detected (Claude/Codex read their own config); a runtime that
#   can't be detected (e.g. Hermes) simply shows no model rather than a wrong one.
#
# Claude Code:
#   --runtime claude-code installs idempotent user-level hooks by default.
#   Use --no-claude-hooks to skip, or --claude-hooks status|install|uninstall|restore.
# Codex:
#   --runtime codex installs idempotent user-level hooks by default.
#   Use --no-codex-hooks to skip, or --codex-hooks status|install|uninstall|restore.
set -e
SERVER=""; KEY=""; OPERATOR="$USER"; RUNTIME=""; AGENT=""; ROLE=""; ABOUT=""; TIPS=""; MODELS=""
CLAUDE_HOOKS=""; CLAUDE_SETTINGS=""
CODEX_HOOKS=""; CODEX_SETTINGS=""
OPENCLAW_PLUGIN=""
while [ $# -gt 0 ]; do case "$1" in
  --server) SERVER="$2"; shift 2;; --key) KEY="$2"; shift 2;;
  --operator) OPERATOR="$2"; shift 2;; --runtime) RUNTIME="$2"; shift 2;;
  --agent) AGENT="$2"; shift 2;; --role) ROLE="$2"; shift 2;;
  --about) ABOUT="$2"; shift 2;; --tips) TIPS="$2"; shift 2;;
  --models) MODELS="$2"; shift 2;;
  --install-claude-hooks) CLAUDE_HOOKS="install"; shift;;
  --no-claude-hooks) CLAUDE_HOOKS="skip"; shift;;
  --claude-hooks) CLAUDE_HOOKS="$2"; shift 2;;
  --claude-settings) CLAUDE_SETTINGS="$2"; shift 2;;
  --install-codex-hooks) CODEX_HOOKS="install"; shift;;
  --no-codex-hooks) CODEX_HOOKS="skip"; shift;;
  --codex-hooks) CODEX_HOOKS="$2"; shift 2;;
  --codex-settings) CODEX_SETTINGS="$2"; shift 2;;
  --install-openclaw-plugin) OPENCLAW_PLUGIN="install"; shift;;
  --no-openclaw-plugin) OPENCLAW_PLUGIN="skip"; shift;;
  *) shift;; esac; done
[ -z "$SERVER" ] && { echo "need --server"; exit 1; }

mkdir -p ~/.tranfu
BASE="${SERVER%/}/shims"
for f in tf_client.sh tf_client.py tf_profile.py tf_report.py tf_hook.py tf_rollout_scan.py tf_hooks.py tf_claude_hooks.py wrapper/tf-run wrapper/tf-hermes-hook.sh; do
  curl -fsSL "$BASE/$f" -o ~/.tranfu/"$(basename "$f")"
done
chmod +x ~/.tranfu/tf-run ~/.tranfu/tf_hooks.py ~/.tranfu/tf_claude_hooks.py ~/.tranfu/tf-hermes-hook.sh

_install_openclaw_plugin() {
  mkdir -p "${HOME}/.tranfu/openclaw"
  for f in package.json openclaw.plugin.json index.js skill-extract.mjs logger.mjs reporter.mjs README.md; do
    curl -fsSL "$BASE/openclaw/$f" -o "${HOME}/.tranfu/openclaw/$f"
  done
  if command -v openclaw >/dev/null 2>&1; then
    openclaw plugins install -l "${HOME}/.tranfu/openclaw" >/dev/null 2>&1 || true
    openclaw plugins enable tranfu-skill-reporter >/dev/null 2>&1 || true
    openclaw config set plugins.entries.tranfu-skill-reporter.enabled true >/dev/null 2>&1 || true
    openclaw config set plugins.entries.tranfu-skill-reporter.hooks.allowConversationAccess true >/dev/null 2>&1 || true
    openclaw config set plugins.entries.tranfu-skill-reporter.config.server "$SERVER" >/dev/null 2>&1 || true
    [ -n "$KEY" ] && openclaw config set plugins.entries.tranfu-skill-reporter.config.key "$KEY" >/dev/null 2>&1 || true
    openclaw config set plugins.entries.tranfu-skill-reporter.config.operator "$OPERATOR" >/dev/null 2>&1 || true
    [ -n "$AGENT" ] && openclaw config set plugins.entries.tranfu-skill-reporter.config.agent "$AGENT" >/dev/null 2>&1 || true
    openclaw config set plugins.entries.tranfu-skill-reporter.config.runtime "${RUNTIME:-open-claw}" >/dev/null 2>&1 || true
    echo "OpenClaw plugin: installed/updated. Restart OpenClaw for equipped Skill reporting."
  else
    echo "OpenClaw plugin files copied to ~/.tranfu/openclaw, but openclaw CLI was not found."
    echo "Enable it later with: openclaw plugins install -l ~/.tranfu/openclaw && openclaw plugins enable tranfu-skill-reporter"
  fi
}

# Identity/env files under ~/.tranfu (overwritten each run — re-installing never
# duplicates). Hooks source these directly because they run in a non-interactive
# shell that does NOT read ~/.zshrc; writing identity only into the rc would leave
# hook-based runtimes (claude-code/codex) blind and silently non-reporting.
#
# We write TWO files:
#   tf_env.sh             — generic; sourced by the shell rc / tf-run. Last install
#                           wins here, which is fine: tf-run takes --agent/--runtime
#                           explicitly, so it only needs server/key from this file.
#   tf_env.<runtime>.sh   — per-runtime; the hook for THIS runtime sources ONLY this.
#                           Isolates identity so co-resident agents (e.g. Claude Code
#                           + Hermes on one machine) never clobber each other.
_emit_env() {
  echo "# TRANFU//AGENTS identity — written by install.sh, safe to re-run."
  echo "export TF_SERVER=\"$SERVER\""
  [ -n "$KEY" ]     && echo "export TF_KEY=\"$KEY\"" || true
  echo "export TF_OPERATOR=\"$OPERATOR\""
  [ -n "$RUNTIME" ] && echo "export TF_RUNTIME=\"$RUNTIME\"" || true
  [ -n "$AGENT" ]   && echo "export TF_AGENT=\"$AGENT\"" || true
  [ -n "$ROLE" ]    && echo "export TF_ROLE=\"$ROLE\"" || true
  [ -n "$ABOUT" ]   && echo "export TF_ABOUT=\"$ABOUT\"" || true
  [ -n "$TIPS" ]    && echo "export TF_TIPS=\"$TIPS\"" || true
}
_emit_env > "${HOME}/.tranfu/tf_env.sh"
chmod 600 "${HOME}/.tranfu/tf_env.sh"
if [ -n "$RUNTIME" ]; then
  RT_SLUG=$(printf '%s' "$RUNTIME" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9._-' '-')
  _emit_env > "${HOME}/.tranfu/tf_env.${RT_SLUG}.sh"
  # TF_MODELS is per-runtime and lives ONLY in this runtime's own env file (never
  # the shared tf_env.sh), so one agent's model label can't leak into another's
  # profile. Hooks source THIS file, so an explicit --models wins here; with no
  # --models we `unset` to neutralize any global TF_MODELS the shell rc may have
  # exported (e.g. Hermes's secrets.env), letting tf_profile.py auto-detect.
  if [ -n "$MODELS" ]; then
    echo "export TF_MODELS=\"$MODELS\"" >> "${HOME}/.tranfu/tf_env.${RT_SLUG}.sh"
  else
    echo "unset TF_MODELS" >> "${HOME}/.tranfu/tf_env.${RT_SLUG}.sh"
  fi
  chmod 600 "${HOME}/.tranfu/tf_env.${RT_SLUG}.sh"
fi

# Idempotently wire the shell rc to load it (covers interactive shells, tf-run,
# and non-hook runtimes). One guarded block — re-running never appends duplicates.
PROFILE="${HOME}/.$(basename "$SHELL")rc"
MARKER="# --- tranfu agent telemetry (managed) ---"
if [ ! -f "$PROFILE" ] || ! grep -qF "$MARKER" "$PROFILE"; then
  {
    echo ""
    echo "$MARKER"
    echo '[ -f "$HOME/.tranfu/tf_env.sh" ] && . "$HOME/.tranfu/tf_env.sh"'
    echo 'export PATH="$HOME/.tranfu:$PATH"'
  } >> "$PROFILE"
fi

# register now: one profile-bearing event so the agent shows up WITH its detail
echo "Registering on the board…"
TF_SERVER="$SERVER" TF_KEY="$KEY" TF_OPERATOR="$OPERATOR" \
TF_RUNTIME="${RUNTIME:-cli}" TF_AGENT="$AGENT" TF_ROLE="$ROLE" TF_ABOUT="$ABOUT" TF_TIPS="$TIPS" \
TF_MODELS="$MODELS" \
TF_WITH_PROFILE=1 python3 ~/.tranfu/tf_report.py \
  --status started --task "接入" --step "registered" --profile 2>/dev/null \
  && echo "  ✓ registered (operator=$OPERATOR, agent=${AGENT:-$RUNTIME})" \
  || echo "  ! could not reach $SERVER — check server/key, then re-run"

echo ""
echo "Done. New shells pick up the config automatically (or: source $PROFILE)."
if [ "$RUNTIME" = "claude-code" ] || [ "$RUNTIME" = "codex" ]; then
  echo "${RUNTIME} reports through hooks after restart. For one-off CLI runs you can still use:"
  echo "  tf-run --runtime ${RUNTIME} --agent \"${AGENT:-<label>}\" --task \"…\" -- ${RUNTIME%%-*}"
elif [ "$RUNTIME" = "hermes" ]; then
  echo "Hermes: for live event-driven reporting (no cron heartbeat needed), add to"
  echo "~/.hermes/config.yaml and restart the gateway (hermes gateway restart):"
  echo "  hooks:"
  for ev in on_session_start pre_llm_call pre_tool_call post_llm_call on_session_end; do
    echo "    ${ev}:"
    echo "      - command: \"~/.tranfu/tf-hermes-hook.sh\""
  done
  echo "  hooks_auto_accept: true   # or approve once interactively / pre-seed allowlist"
  echo "One-off CLI runs can still use: tf-run --runtime hermes --agent \"${AGENT:-多儿}\" --task \"…\" -- <cmd>"
else
  echo "From now on, run your agent through the wrapper so steps show live:"
  echo "  tf-run --runtime ${RUNTIME:-<rt>} --agent \"${AGENT:-<label>}\" --task \"…\" -- <your agent command>"
fi

if [ -z "$CLAUDE_HOOKS" ] && [ "$RUNTIME" = "claude-code" ]; then
  CLAUDE_HOOKS="install"
fi
if [ -z "$CODEX_HOOKS" ] && [ "$RUNTIME" = "codex" ]; then
  CODEX_HOOKS="install"
fi
case "$RUNTIME" in
  openclaw|open-claw|claw-code)
    [ -z "$OPENCLAW_PLUGIN" ] && OPENCLAW_PLUGIN="install"
    ;;
esac
if [ -n "$CLAUDE_HOOKS" ] && [ "$CLAUDE_HOOKS" != "skip" ]; then
  case "$CLAUDE_HOOKS" in
    status|install|uninstall|restore) ;;
    *) echo "Unknown --claude-hooks action: $CLAUDE_HOOKS (expected status|install|uninstall|restore|skip)"; exit 1;;
  esac
  echo ""
  echo "Claude Code hooks: $CLAUDE_HOOKS"
  if [ -n "$CLAUDE_SETTINGS" ]; then
    python3 ~/.tranfu/tf_hooks.py --target claude --settings "$CLAUDE_SETTINGS" "$CLAUDE_HOOKS" \
      || echo "  ! could not update Claude Code hooks — run: python3 ~/.tranfu/tf_hooks.py --target claude $CLAUDE_HOOKS"
  else
    python3 ~/.tranfu/tf_hooks.py --target claude "$CLAUDE_HOOKS" \
      || echo "  ! could not update Claude Code hooks — run: python3 ~/.tranfu/tf_hooks.py --target claude $CLAUDE_HOOKS"
  fi
  [ "$CLAUDE_HOOKS" = "install" ] && echo "Restart Claude Code for hooks to take effect." || true
fi
if [ -n "$CODEX_HOOKS" ] && [ "$CODEX_HOOKS" != "skip" ]; then
  case "$CODEX_HOOKS" in
    status|install|uninstall|restore) ;;
    *) echo "Unknown --codex-hooks action: $CODEX_HOOKS (expected status|install|uninstall|restore|skip)"; exit 1;;
  esac
  echo ""
  echo "Codex hooks: $CODEX_HOOKS"
  if [ -n "$CODEX_SETTINGS" ]; then
    python3 ~/.tranfu/tf_hooks.py --target codex --settings "$CODEX_SETTINGS" "$CODEX_HOOKS" \
      || echo "  ! could not update Codex hooks — run: python3 ~/.tranfu/tf_hooks.py --target codex $CODEX_HOOKS"
  else
    python3 ~/.tranfu/tf_hooks.py --target codex "$CODEX_HOOKS" \
      || echo "  ! could not update Codex hooks — run: python3 ~/.tranfu/tf_hooks.py --target codex $CODEX_HOOKS"
  fi
  [ "$CODEX_HOOKS" = "install" ] && echo "Restart Codex for hooks to take effect. If Codex asks to trust the new hook, approve it once." || true
fi
if [ "$OPENCLAW_PLUGIN" = "install" ]; then
  echo ""
  _install_openclaw_plugin
fi
