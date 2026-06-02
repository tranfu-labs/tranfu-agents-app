#!/usr/bin/env bash
# TRANFU//AGENTS — 轻量上报客户端 (bash)。
#   source tf_client.sh
#   tf_emit running --task "改写文案" --step "drafting hero"
#   TF_WITH_PROFILE=1 tf_emit started --task "..."     # 附带自动探测的 profile
#
# 环境变量:
#   TF_SERVER         例 https://agents.tranfu.com   (必填)
#   TF_KEY            团队写入密钥(若服务端开启校验则必填)
#   TF_TOKEN          per-operator 令牌(开启强制归因时必填;tf_report enroll 获取)
#   TF_OPERATOR       你的名字 (默认 $USER)
#   TF_PARENT_SESSION 父 run 的 session_id(子 agent 挂到父 run 下,可选)
#   TF_RUNTIME        agent 工具 (默认 shell)
#   TF_AGENT          用途标签,如 copy / code (可选)
#   TF_SESSION        会话 id (默认随机,本 shell 内稳定)
#   TF_WITH_PROFILE=1 该事件附带自动探测的 profile(版本/终端/MCP/技能/集成…)
#   TF_CAPTURE_CONTENT=1  连带回传 --input / --output
TF_OPERATOR="${TF_OPERATOR:-$USER}"
TF_RUNTIME="${TF_RUNTIME:-shell}"
TF_AGENT="${TF_AGENT:-}"
TF_SESSION="${TF_SESSION:-$(date +%s)-$RANDOM}"

# 解析本脚本所在目录(bash/zsh 兼容),兜底到 ~/.tranfu(install.sh 安装位置)
_TF_DIR="${TF_SHIM_DIR:-}"
if [ -z "$_TF_DIR" ]; then
  _TF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)" || _TF_DIR=""
fi
[ -f "$_TF_DIR/tf_report.py" ] || _TF_DIR="$HOME/.tranfu"

tf_emit() {
  local st="$1"; shift
  local task="" step="" model="" inp="" outp="" agent="$TF_AGENT"
  while [ $# -gt 0 ]; do case "$1" in
    --agent) agent="$2"; shift 2;;
    --task) task="$2"; shift 2;;
    --step) step="$2"; shift 2;;
    --model) model="$2"; shift 2;;
    --input) inp="$2"; shift 2;;
    --output) outp="$2"; shift 2;;
    *) shift;;
  esac; done
  local args=(--status "$st" --session "$TF_SESSION")
  [ -n "$agent" ] && args+=(--agent "$agent")
  [ -n "$task" ]  && args+=(--task "$task")
  [ -n "$step" ]  && args+=(--step "$step")
  [ -n "$model" ] && args+=(--model "$model")
  if [ "${TF_CAPTURE_CONTENT:-0}" = "1" ]; then
    [ -n "$inp" ]  && args+=(--input "$inp")
    [ -n "$outp" ] && args+=(--output "$outp")
  fi
  [ "${TF_WITH_PROFILE:-0}" = "1" ] && args+=(--profile)
  TF_OPERATOR="$TF_OPERATOR" TF_RUNTIME="$TF_RUNTIME" TF_SESSION="$TF_SESSION" TF_AGENT="$agent" \
    python3 "$_TF_DIR/tf_report.py" "${args[@]}" || echo "tf_emit: report failed" >&2
}
