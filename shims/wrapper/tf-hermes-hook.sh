#!/usr/bin/env bash
# TRANFU//AGENTS — Hermes shell-hook wrapper.
# Hermes runs hook commands via shlex.split (shell=False), so we can't inline
# `. env; python` there. This wrapper loads Hermes's per-runtime identity, then
# dispatches to the shared tf_hook.py. stdin (the hook JSON) flows through to it.
# Register in ~/.hermes/config.yaml:
#     hooks:
#       on_session_start: [{command: "~/.tranfu/tf-hermes-hook.sh"}]
#       pre_llm_call:     [{command: "~/.tranfu/tf-hermes-hook.sh"}]
#       pre_tool_call:    [{command: "~/.tranfu/tf-hermes-hook.sh"}]
#       post_llm_call:    [{command: "~/.tranfu/tf-hermes-hook.sh"}]
#       on_session_end:   [{command: "~/.tranfu/tf-hermes-hook.sh"}]
. "$HOME/.tranfu/tf_env.hermes.sh" 2>/dev/null
exec python3 "$HOME/.tranfu/tf_hook.py"
