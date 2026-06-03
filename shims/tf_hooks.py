#!/usr/bin/env python3
"""
TRANFU//AGENTS — local agent hook settings manager.

Maintains user-level hook config for supported local agents:
  - Claude Code: ~/.claude/settings.json
  - Codex:       ~/.codex/hooks.json

The script is stdlib-only, idempotent, and preserves non-TRANFU hooks.

Examples:
  python3 ~/.tranfu/tf_hooks.py --target claude status
  python3 ~/.tranfu/tf_hooks.py --target codex install
  python3 ~/.tranfu/tf_hooks.py --target codex uninstall
  python3 ~/.tranfu/tf_hooks.py --target claude restore
"""
import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Each target sources its OWN per-runtime identity file (tf_env.<runtime>.sh),
# NOT the shared tf_env.sh. This is critical when multiple agents share one
# machine (e.g. Claude Code + Hermes): a single shared file gets clobbered by
# whichever install ran last, silently mis-attributing one agent's activity to
# the other. Per-runtime files keep each agent's identity isolated. The hook
# still sources a file (vs inheriting env) because hooks run in a non-interactive
# shell that does NOT read ~/.zshrc — see install.sh.
RUNTIME_FOR_TARGET = {"claude": "claude-code", "codex": "codex"}


def _command(target):
    env_file = f'$HOME/.tranfu/tf_env.{RUNTIME_FOR_TARGET[target]}.sh'
    return f'. "{env_file}" 2>/dev/null; python3 "$HOME/.tranfu/tf_hook.py"'


COMMON_EVENTS = (
    ("SessionStart", None),
    ("UserPromptSubmit", None),
    ("PreToolUse", ""),
    ("Stop", None),
    ("SessionEnd", None),
)
CODEX_EVENTS = (
    ("SessionStart", None),
    ("UserPromptSubmit", None),
    ("PreToolUse", None),
    ("Stop", None),
    ("SessionEnd", None),
)
TARGETS = {
    "claude": {
        "label": "Claude Code",
        "path": lambda: Path.home() / ".claude" / "settings.json",
        "events": COMMON_EVENTS,
        "timeout": None,
    },
    "codex": {
        "label": "Codex",
        "path": lambda: Path.home() / ".codex" / "hooks.json",
        "events": CODEX_EVENTS,
        "timeout": 5,
    },
}


def _settings_path(target):
    return TARGETS[target]["path"]()


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _unique_path(path):
    if not path.exists():
        return path
    for i in range(1, 1000):
        candidate = Path(str(path) + f".{i}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not create unique backup path for {path}")


def _load_settings(path):
    if not path.exists():
        return {}, False
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}, True
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data, True


def _write_settings(path, cfg):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tranfu.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _backup(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    base = path.with_name(path.name + f".tranfu.bak.{_timestamp()}")
    if path.exists():
        backup = _unique_path(base)
        shutil.copy2(path, backup)
    else:
        backup = _unique_path(Path(str(base) + ".missing"))
        backup.write_text("settings file did not exist before this TRANFU operation\n", encoding="utf-8")
    return backup


def _backup_current_for_restore(path):
    if not path.exists():
        return None
    backup = _unique_path(path.with_name(path.name + f".tranfu.pre-restore.{_timestamp()}"))
    shutil.copy2(path, backup)
    return backup


def _is_tranfu_hook(hook):
    if not isinstance(hook, dict):
        return False
    cmd = hook.get("command")
    if not isinstance(cmd, str):
        return False
    normalized = cmd.replace("\\", "/")
    return "tf_hook.py" in normalized and ".tranfu" in normalized


def _entry(target, event):
    item = {"hooks": [{"type": "command", "command": _command(target)}]}
    timeout = TARGETS[target]["timeout"]
    if timeout is not None:
        item["hooks"][0]["timeout"] = timeout
    matcher = dict(TARGETS[target]["events"])[event]
    if matcher is not None:
        item["matcher"] = matcher
    return item


def _require_hooks_object(cfg):
    hooks = cfg.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("settings field 'hooks' must be a JSON object")
    return hooks


def _count_for_event(groups):
    if not isinstance(groups, list):
        return 0
    count = 0
    for group in groups:
        if not isinstance(group, dict):
            continue
        hooks = group.get("hooks")
        if not isinstance(hooks, list):
            continue
        count += sum(1 for hook in hooks if _is_tranfu_hook(hook))
    return count


def hook_counts(cfg, target):
    hooks = cfg.get("hooks")
    events = TARGETS[target]["events"]
    if not isinstance(hooks, dict):
        return {event: 0 for event, _matcher in events}
    return {event: _count_for_event(hooks.get(event)) for event, _matcher in events}


def install_hooks(cfg, target):
    hooks = _require_hooks_object(cfg)
    changed = False
    actions = []

    for event, _matcher in TARGETS[target]["events"]:
        groups = hooks.get(event)
        if groups is None:
            hooks[event] = [_entry(target, event)]
            changed = True
            actions.append(f"added {event}")
            continue
        if not isinstance(groups, list):
            raise ValueError(f"settings field 'hooks.{event}' must be a JSON array")

        seen = False
        removed = 0
        upgraded = 0
        new_groups = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                new_groups.append(group)
                continue

            new_hook_list = []
            group_changed = False
            for hook in group["hooks"]:
                if _is_tranfu_hook(hook):
                    if not seen:
                        seen = True
                        # upgrade an older TRANFU hook to the current command form
                        # (e.g. one that sourced the shared tf_env.sh -> per-runtime)
                        want = _command(target)
                        if hook.get("command") != want:
                            hook = dict(hook)
                            hook["command"] = want
                            upgraded += 1
                            group_changed = True
                        new_hook_list.append(hook)
                    else:
                        removed += 1
                        group_changed = True
                else:
                    new_hook_list.append(hook)

            if new_hook_list:
                if group_changed:
                    group = dict(group)
                    group["hooks"] = new_hook_list
                new_groups.append(group)

        if removed or upgraded:
            hooks[event] = new_groups
            changed = True
            if removed:
                actions.append(f"deduped {event}")
            if upgraded:
                actions.append(f"upgraded {event}")

        if not seen:
            new_groups.append(_entry(target, event))
            hooks[event] = new_groups
            changed = True
            actions.append(f"added {event}")

    if not actions:
        actions.append("already installed")
    return changed, actions


def uninstall_hooks(cfg):
    hooks = cfg.get("hooks")
    if not isinstance(hooks, dict):
        return False, ["not installed"]

    changed = False
    removed_total = 0
    for event in list(hooks.keys()):
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        new_groups = []
        removed_event = 0
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                new_groups.append(group)
                continue
            kept = [hook for hook in group["hooks"] if not _is_tranfu_hook(hook)]
            removed = len(group["hooks"]) - len(kept)
            removed_event += removed
            if kept:
                if removed:
                    group = dict(group)
                    group["hooks"] = kept
                new_groups.append(group)
        if removed_event:
            changed = True
            removed_total += removed_event
            if new_groups:
                hooks[event] = new_groups
            else:
                del hooks[event]
    if changed and not hooks:
        cfg.pop("hooks", None)
    return changed, [f"removed {removed_total} hook(s)" if removed_total else "not installed"]


def latest_backup(path):
    backups = sorted(path.parent.glob(path.name + ".tranfu.bak.*"))
    return backups[-1] if backups else None


def restore_backup(path, backup):
    if backup is None:
        backup = latest_backup(path)
    if backup is None:
        raise FileNotFoundError(f"no TRANFU backup found next to {path}")
    if not backup.exists():
        raise FileNotFoundError(str(backup))

    pre = _backup_current_for_restore(path)
    if backup.name.endswith(".missing"):
        if path.exists():
            path.unlink()
        return backup, pre, "removed settings file created after missing backup"

    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, path)
    return backup, pre, "restored backup"


def print_status(path, cfg, target, as_json=False):
    counts = hook_counts(cfg, target)
    missing = [event for event, count in counts.items() if count == 0]
    duplicated = [event for event, count in counts.items() if count > 1]
    installed = not missing and not duplicated
    data = {
        "target": target,
        "label": TARGETS[target]["label"],
        "settings": str(path),
        "installed": installed,
        "missing": missing,
        "duplicated": duplicated,
        "counts": counts,
    }
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    state = "installed" if installed else "needs repair" if any(counts.values()) else "not installed"
    print(f"TRANFU {TARGETS[target]['label']} hooks: {state}")
    print(f"settings: {path}")
    for event, count in counts.items():
        label = "missing" if count == 0 else "ok" if count == 1 else f"duplicate x{count}"
        print(f"- {event}: {label}")


def cmd_status(args):
    cfg, _existed = _load_settings(args.settings)
    print_status(args.settings, cfg, args.target, args.json)
    return 0


def cmd_install(args):
    cfg, _existed = _load_settings(args.settings)
    changed, actions = install_hooks(cfg, args.target)
    if changed:
        backup = _backup(args.settings)
        _write_settings(args.settings, cfg)
        print(f"TRANFU {TARGETS[args.target]['label']} hooks installed/repaired")
        print("actions: " + ", ".join(actions))
        print(f"backup: {backup}")
    else:
        print(f"TRANFU {TARGETS[args.target]['label']} hooks already installed")
    print(f"settings: {args.settings}")
    return 0


def cmd_uninstall(args):
    cfg, _existed = _load_settings(args.settings)
    changed, actions = uninstall_hooks(cfg)
    if changed:
        backup = _backup(args.settings)
        _write_settings(args.settings, cfg)
        print(f"TRANFU {TARGETS[args.target]['label']} hooks uninstalled")
        print("actions: " + ", ".join(actions))
        print(f"backup: {backup}")
    else:
        print(f"TRANFU {TARGETS[args.target]['label']} hooks not installed")
    print(f"settings: {args.settings}")
    return 0


def cmd_restore(args):
    backup = Path(args.backup).expanduser() if args.backup else None
    restored, pre, message = restore_backup(args.settings, backup)
    print(f"TRANFU {TARGETS[args.target]['label']} hooks restore: {message}")
    print(f"restored: {restored}")
    if pre:
        print(f"current backup: {pre}")
    print(f"settings: {args.settings}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Manage TRANFU local agent hooks")
    parser.add_argument("--target", choices=sorted(TARGETS), default="claude",
                        help="agent hook config to manage (default: claude)")
    parser.add_argument("--settings", type=Path, default=None,
                        help="hook settings JSON path (default depends on --target)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="show installed/missing hook state")
    p.add_argument("--json", action="store_true", help="print machine-readable status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("install", help="idempotently install or repair hooks")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("uninstall", help="remove TRANFU hooks")
    p.set_defaults(func=cmd_uninstall)

    p = sub.add_parser("restore", help="restore latest or specified TRANFU backup")
    p.add_argument("--backup", default="", help="backup file to restore")
    p.set_defaults(func=cmd_restore)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.settings is None:
        args.settings = _settings_path(args.target)
    args.settings = args.settings.expanduser()
    try:
        return args.func(args)
    except Exception as exc:
        sys.stderr.write(f"tf_hooks: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
