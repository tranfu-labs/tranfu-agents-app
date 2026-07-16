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
AUTO_UPDATE="${TF_AUTO_UPDATE:-1}"
CLAUDE_HOOKS=""; CLAUDE_SETTINGS=""
CODEX_HOOKS=""; CODEX_SETTINGS=""
OPENCLAW_PLUGIN=""
while [ $# -gt 0 ]; do case "$1" in
  --server) SERVER="$2"; shift 2;; --key) KEY="$2"; shift 2;;
  --operator) OPERATOR="$2"; shift 2;; --runtime) RUNTIME="$2"; shift 2;;
  --agent) AGENT="$2"; shift 2;; --role) ROLE="$2"; shift 2;;
  --about) ABOUT="$2"; shift 2;; --tips) TIPS="$2"; shift 2;;
  --models) MODELS="$2"; shift 2;;
  --auto-update) AUTO_UPDATE="$2"; shift 2;;
  --no-auto-update) AUTO_UPDATE="0"; shift;;
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
_die() { echo "✗ $1" >&2; exit 1; }

# 预检:任何一项不满足就明确报错并停,绝不做半截安装(对标 tranfu-skills/INSTALL.md 的 pre-checks)。
[ -z "$SERVER" ] && _die "缺 --server <接入地址>"
case "$SERVER" in
  http://*|https://*) ;;
  *) _die "--server 需是完整地址(http:// 或 https:// 开头),当前: $SERVER";;
esac
command -v python3 >/dev/null 2>&1 || _die "需要 python3(安装上报工具与注册都依赖它);装好后重跑,不要用 sudo。"
command -v curl    >/dev/null 2>&1 || _die "需要 curl;装好后重跑。"

mkdir -p ~/.tranfu 2>/dev/null || _die "无法创建 ~/.tranfu(检查 HOME 权限);不要用 sudo。"
[ -w "${HOME}/.tranfu" ] || _die "~/.tranfu 不可写(检查归属/权限);不要用 sudo。"

BASE="${SERVER%/}/shims"

# 看板域名 + shim 清单可达性:够不到就停,把「连不上」暴露在这里而不是半装之后。
curl -fsSL --max-time 8 -o /dev/null "$BASE/manifest" \
  || _die "连不上看板($BASE/manifest):多半是服务端没部署好/域名没通,或需连公司 VPN。确认 ${SERVER} 能打开后重跑。"

# 重装时若未显式传 --key,沿用本机已存的 key:tf-doctor --identity 故意不回显明文,
# 由这里负责保留,让「重装不必再问 key」成立。优先本 runtime 的 env 文件,再退共享文件。
if [ -z "$KEY" ]; then
  _RT_SLUG=$(printf '%s' "$RUNTIME" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9._-' '-')
  for ef in "${HOME}/.tranfu/tf_env.${_RT_SLUG}.sh" "${HOME}/.tranfu/tf_env.sh"; do
    [ -f "$ef" ] || continue
    k=$(sed -n 's/^export TF_KEY="\(.*\)"$/\1/p' "$ef" | head -1)
    [ -n "$k" ] && { KEY="$k"; echo "(沿用本机已存的 key)"; break; }
  done
fi

# runtime 自动识别:agent 通常已传 --runtime(它知道自己是谁)。没传时,用「进程内」
# 环境信号兜底——这些标志的是「现在正在跑哪个 agent」,而非「机器上装了哪个」(配置目录
# 在多 runtime 机器上会歧义,故不采信)。识别不出就保持空,按 cli 注册、不接 hooks(与原行为一致)。
_detect_runtime() {
  if [ -n "${CLAUDECODE:-}" ] || [ -n "${CLAUDE_CODE_ENTRYPOINT:-}" ]; then echo "claude-code"; return; fi
  if [ -n "${CODEX_SANDBOX:-}" ] || [ -n "${CODEX_HOME:-}" ]; then echo "codex"; return; fi
  if [ -n "${OPENCLAW_AGENT_ID:-}" ] || [ -n "${OPENCLAW_HOME:-}" ]; then echo "openclaw"; return; fi
  if [ -n "${HERMES_SESSION:-}" ] || [ -n "${HERMES_HOME:-}" ]; then echo "hermes"; return; fi
  echo ""
}
if [ -z "$RUNTIME" ]; then
  RUNTIME="$(_detect_runtime)"
  [ -n "$RUNTIME" ] && echo "自动识别 runtime:$RUNTIME(用户无需指定)"
fi

_install_from_manifest() {
  TF_INSTALL_BASE="$BASE" TF_INSTALL_HOME="${HOME}/.tranfu" python3 - <<'PY'
import hashlib, json, os, urllib.parse, urllib.request
from pathlib import Path

base = os.environ["TF_INSTALL_BASE"].rstrip("/")
root = Path(os.environ["TF_INSTALL_HOME"]).expanduser()

def fetch(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return r.read()

def safe_target(target):
    target = str(target).replace("\\", "/")
    if target.startswith("/"):
        raise ValueError("absolute target")
    parts = [p for p in target.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise ValueError("unsafe target")
    path = root.joinpath(*parts).resolve()
    r = root.resolve()
    if path != r and not str(path).startswith(str(r) + os.sep):
        raise ValueError("target escapes install root")
    return path

manifest = json.loads(fetch(base + "/manifest").decode("utf-8"))
files = manifest.get("files")
if not isinstance(files, list):
    raise ValueError("manifest.files must be a list")
root.mkdir(parents=True, exist_ok=True)
for item in files:
    src = item["path"]
    dst = safe_target(item["target"])
    data = fetch(base + "/" + urllib.parse.quote(src, safe="/"))
    if hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise ValueError("sha256 mismatch: " + src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(str(tmp), str(dst))
    os.chmod(str(dst), 0o755 if item.get("executable") else 0o644)

# legacy 清理:删掉 ~/.tranfu 顶层属于我们命名空间(tf_*/tf-*)、但已不在新清单里的
# 孤儿 shim(服务端重命名/移除旧文件后会残留)。只动顶层常规文件,保护身份/状态文件,不碰子目录。
keep = set()
for item in files:
    p = safe_target(item["target"])
    if p.parent.resolve() == root.resolve():
        keep.add(p.name)
for child in root.iterdir():
    if not child.is_file():
        continue
    name = child.name
    if name in keep or name in ("manifest.json", "spool.ndjson"):
        continue
    if name.startswith("tf_env") or name.startswith(".") or name.endswith(".tmp"):
        continue
    if name.startswith("tf_") or name.startswith("tf-"):
        try:
            child.unlink()
        except Exception:
            pass

tmp = root / "manifest.json.tmp"
tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(str(tmp), str(root / "manifest.json"))
PY
}

if ! _install_from_manifest; then
  for f in tf_client.sh tf_client.py tf_profile.py tf_report.py tf_hook.py tf_selfupdate.py tf_rollout_scan.py tf_hooks.py tf_claude_hooks.py tf_codex_hook_guard.py wrapper/tf-run wrapper/tf-hermes-hook.sh wrapper/tf-doctor; do
    curl -fsSL "$BASE/$f" -o ~/.tranfu/"$(basename "$f")"
  done
  rm -f ~/.tranfu/manifest.json
fi
chmod +x ~/.tranfu/tf-run ~/.tranfu/tf_hooks.py ~/.tranfu/tf_claude_hooks.py ~/.tranfu/tf_codex_hook_guard.py ~/.tranfu/tf_selfupdate.py ~/.tranfu/tf-hermes-hook.sh ~/.tranfu/tf-doctor

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
  echo "export TF_AUTO_UPDATE=\"$AUTO_UPDATE\""
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

# 接入自检:hooks 都装完后跑一遍,给人即时确认(取代过去手动发 tf_emit 测试)。
# 自检会发一条合法心跳,看板应据此出现这张卡。doctor 非零退出不影响安装结果。
echo ""
echo "接入自检 (tf-doctor):"
TF_SERVER="$SERVER" TF_KEY="$KEY" TF_OPERATOR="$OPERATOR" \
TF_RUNTIME="${RUNTIME:-cli}" TF_AGENT="$AGENT" \
python3 ~/.tranfu/tf-doctor --runtime "${RUNTIME:-cli}" || true
