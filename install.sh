#!/usr/bin/env bash
# One-shot installer for a teammate's machine. Installs the shim clients to
# ~/.tranfu, records this agent's identity, and registers it on the board
# (sends one profile-bearing event so the card AND detail page populate).
#
#   curl -fsSL https://tranfu-agents-app.tranfu.com/install.sh | bash -s -- \
#       --server https://tranfu-agents-app.tranfu.com --key SECRET \
#       --operator nezha --runtime hermes --agent "多儿" --role "哪吒的 Lark 助手,写文档/调研"
set -e
SERVER=""; KEY=""; OPERATOR="$USER"; RUNTIME=""; AGENT=""; ROLE=""; ABOUT=""; TIPS=""
while [ $# -gt 0 ]; do case "$1" in
  --server) SERVER="$2"; shift 2;; --key) KEY="$2"; shift 2;;
  --operator) OPERATOR="$2"; shift 2;; --runtime) RUNTIME="$2"; shift 2;;
  --agent) AGENT="$2"; shift 2;; --role) ROLE="$2"; shift 2;;
  --about) ABOUT="$2"; shift 2;; --tips) TIPS="$2"; shift 2;;
  *) shift;; esac; done
[ -z "$SERVER" ] && { echo "need --server"; exit 1; }

mkdir -p ~/.tranfu
BASE="${SERVER%/}/shims"
for f in tf_client.sh tf_client.py tf_profile.py tf_report.py wrapper/tf-run; do
  curl -fsSL "$BASE/$f" -o ~/.tranfu/"$(basename "$f")"
done
chmod +x ~/.tranfu/tf-run

# persist config to shell rc (so every future run reports with the same identity)
PROFILE="${HOME}/.$(basename "$SHELL")rc"
{
  echo ""; echo "# --- tranfu agent telemetry ---"
  echo "export TF_SERVER=\"$SERVER\""
  echo "export TF_KEY=\"$KEY\""
  echo "export TF_OPERATOR=\"$OPERATOR\""
  [ -n "$RUNTIME" ] && echo "export TF_RUNTIME=\"$RUNTIME\""
  [ -n "$AGENT" ]   && echo "export TF_AGENT=\"$AGENT\""
  [ -n "$ROLE" ]    && echo "export TF_ROLE=\"$ROLE\""
  [ -n "$ABOUT" ]   && echo "export TF_ABOUT=\"$ABOUT\""
  [ -n "$TIPS" ]    && echo "export TF_TIPS=\"$TIPS\""
  echo "export PATH=\"\$HOME/.tranfu:\$PATH\""
} >> "$PROFILE"

# register now: one profile-bearing event so the agent shows up WITH its detail
echo "Registering on the board…"
TF_SERVER="$SERVER" TF_KEY="$KEY" TF_OPERATOR="$OPERATOR" \
TF_RUNTIME="${RUNTIME:-cli}" TF_AGENT="$AGENT" TF_ROLE="$ROLE" TF_ABOUT="$ABOUT" TF_TIPS="$TIPS" \
TF_WITH_PROFILE=1 python3 ~/.tranfu/tf_report.py \
  --status started --task "接入" --step "registered" --profile 2>/dev/null \
  && echo "  ✓ registered (operator=$OPERATOR, agent=${AGENT:-$RUNTIME})" \
  || echo "  ! could not reach $SERVER — check server/key, then re-run"

echo ""
echo "Done. New shells pick up the config automatically (or: source $PROFILE)."
echo "From now on, run your agent through the wrapper so steps show live:"
echo "  tf-run --runtime ${RUNTIME:-<rt>} --agent \"${AGENT:-<label>}\" --task \"…\" -- <your agent command>"
if [ "$RUNTIME" = "claude-code" ]; then
  echo "Claude Code 也可用钩子上报实时步骤,见 shims/claude-code/README.md。"
fi
