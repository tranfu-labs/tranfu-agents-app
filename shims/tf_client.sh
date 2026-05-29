#!/usr/bin/env bash
# TRANFU//AGENTS — 轻量上报客户端 (bash)。
#   source tf_client.sh
#   tf_emit running --task "改写文案" --step "drafting hero"
#
# 环境变量:
#   TF_SERVER         例 https://agents.tranfu.com   (必填)
#   TF_KEY            接入密钥(若服务端开启校验则必填)
#   TF_OPERATOR       你的名字 (默认 $USER)
#   TF_RUNTIME        agent 工具 (默认 shell)
#   TF_AGENT          用途标签,如 copy / code (可选)
#   TF_SESSION        会话 id (默认随机,本 shell 内稳定)
#   TF_CAPTURE_CONTENT=1  连带回传 --input / --output
TF_OPERATOR="${TF_OPERATOR:-$USER}"
TF_RUNTIME="${TF_RUNTIME:-shell}"
TF_AGENT="${TF_AGENT:-}"
TF_SESSION="${TF_SESSION:-$(date +%s)-$RANDOM}"

tf_emit() {
  local status="$1"; shift
  local task="" step="" model="" input="" output=""
  while [ $# -gt 0 ]; do case "$1" in
    --agent) TF_AGENT="$2"; shift 2;;
    --task) task="$2"; shift 2;;
    --step) step="$2"; shift 2;;
    --model) model="$2"; shift 2;;
    --input) input="$2"; shift 2;;
    --output) output="$2"; shift 2;;
    *) shift;;
  esac; done
  [ "${TF_CAPTURE_CONTENT:-0}" != "1" ] && { input=""; output=""; }
  local body
  body=$(TF_S="$status" TF_T="$task" TF_ST="$step" TF_M="$model" TF_IN="$input" TF_OUT="$output" \
         TF_OP="$TF_OPERATOR" TF_RT="$TF_RUNTIME" TF_SES="$TF_SESSION" TF_AG="$TF_AGENT" python3 - <<'PY'
import os, json
g=lambda k: os.environ.get(k) or None
d={"operator":g("TF_OP"),"agent":g("TF_AG"),"runtime":g("TF_RT"),"session_id":g("TF_SES"),
   "status":g("TF_S"),"task":g("TF_T"),"current_step":g("TF_ST"),"model":g("TF_M"),
   "input":g("TF_IN"),"output":g("TF_OUT")}
print(json.dumps({k:v for k,v in d.items() if v is not None}))
PY
)
  curl -s -m 5 -XPOST "$TF_SERVER/v1/events" \
    -H "content-type: application/json" -H "X-TF-Key: ${TF_KEY:-}" \
    -d "$body" >/dev/null || echo "tf_emit: post failed" >&2
}
