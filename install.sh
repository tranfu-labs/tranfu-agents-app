#!/usr/bin/env bash
# One-shot installer for a teammate's machine. Installs the shim clients to
# ~/.tranfu and wires up whatever runtime you name.
#
#   curl -fsSL https://raw.githubusercontent.com/tranfu-labs/tranfu-skills/main/tranfu-agent-telemetry/install.sh | bash -s -- \
#       --server https://agents.tranfu.com --key SECRET --operator alice --runtime codex
set -e
SERVER=""; KEY=""; OPERATOR="$USER"; RUNTIME=""
while [ $# -gt 0 ]; do case "$1" in
  --server) SERVER="$2"; shift 2;; --key) KEY="$2"; shift 2;;
  --operator) OPERATOR="$2"; shift 2;; --runtime) RUNTIME="$2"; shift 2;;
  *) shift;; esac; done
[ -z "$SERVER" ] && { echo "need --server"; exit 1; }

mkdir -p ~/.tranfu
BASE="https://raw.githubusercontent.com/tranfu-labs/tranfu-skills/main/tranfu-agent-telemetry/shims"
for f in tf_client.sh tf_client.py wrapper/tf-run; do
  curl -fsSL "$BASE/$f" -o ~/.tranfu/"$(basename "$f")"
done
chmod +x ~/.tranfu/tf-run

PROFILE="${HOME}/.$(basename "$SHELL")rc"
{
  echo ""; echo "# --- tranfu agent telemetry ---"
  echo "export TF_SERVER=\"$SERVER\""
  echo "export TF_KEY=\"$KEY\""
  echo "export TF_OPERATOR=\"$OPERATOR\""
  echo "export PATH=\"\$HOME/.tranfu:\$PATH\""
} >> "$PROFILE"

echo "Installed for operator=$OPERATOR (global). runtime + agent are set PER RUN."
echo "Run each of your agents through the wrapper, labelling what it's for:"
echo "  tf-run --runtime open-claw --agent copy --task \"rewrite landing copy\" -- <copy agent cmd>"
echo "  tf-run --runtime codex     --agent code --task \"build the API\"       -- <code agent cmd>"
[ "$RUNTIME" = "claude-code" ] && echo "Claude Code 也可用钩子上报状态,见 shims/claude-code/README.md。"
