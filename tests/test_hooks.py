"""tf_hooks 契约测试：每个 runtime 的 hook 必须 source 各自的身份文件，
避免同机多 agent 共用 tf_env.sh 互相覆盖、把活动串到别的 agent 头上。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shims"))

import tf_hooks


def test_command_is_per_runtime():
    c = tf_hooks._command("claude")
    x = tf_hooks._command("codex")
    assert "tf_env.claude-code.sh" in c and "tf_hook.py" in c
    assert "tf_env.codex.sh" in x
    # 关键：不再 source 会被覆盖的全局 tf_env.sh
    assert "tf_env.sh" not in c.replace("tf_env.claude-code.sh", "")
    assert c != x


def test_install_writes_per_runtime_command():
    cfg = {}
    changed, _ = tf_hooks.install_hooks(cfg, "claude")
    assert changed
    cmd = cfg["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "tf_env.claude-code.sh" in cmd


def test_install_upgrades_old_shared_command():
    # 模拟旧安装：hook 源了共享 tf_env.sh（会被别的 agent 覆盖）
    old = '. "$HOME/.tranfu/tf_env.sh" 2>/dev/null; python3 "$HOME/.tranfu/tf_hook.py"'
    cfg = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": old}]}]}}
    changed, actions = tf_hooks.install_hooks(cfg, "claude")
    assert changed and any("upgraded" in a for a in actions)
    cmd = cfg["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "tf_env.claude-code.sh" in cmd          # 已升级到 per-runtime
    assert tf_hooks._is_tranfu_hook(cfg["hooks"]["SessionStart"][0]["hooks"][0])


def test_idempotent_no_change_on_reinstall():
    cfg = {}
    tf_hooks.install_hooks(cfg, "claude")
    changed, actions = tf_hooks.install_hooks(cfg, "claude")   # 再装一次
    assert changed is False and actions == ["already installed"]
