"""tf_profile 技能探测契约测试：按 runtime 区分软链处理。
Hermes 把核心技能(lark-*)软链进自己的 skills 目录 —— 必须算它的；
Claude 的 skills 目录里从共享池软链进来的 —— 是借来的，不算。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shims"))

import tf_profile


def _mk_skill(d, name):
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n", encoding="utf-8")


def test_hermes_counts_symlinked_core_skills(tmp_path, monkeypatch):
    monkeypatch.setattr(tf_profile, "HOME", tmp_path)
    # 共享池里的真实 lark 技能
    pool = tmp_path / ".agents" / "skills"
    _mk_skill(pool / "lark-base", "lark-base")
    hs = tmp_path / ".hermes" / "skills"
    hs.mkdir(parents=True)
    (hs / "lark-base").symlink_to(pool / "lark-base")     # 多儿软链进来的核心技能
    _mk_skill(hs / "dogfood", "dogfood")                  # 顶层真目录
    _mk_skill(hs / "feishu" / "card", "feishu-card")      # category/skill 两层

    names = {s["name"] for s in tf_profile.detect_skills(str(tmp_path), "hermes")["local"]}
    assert {"lark-base", "dogfood", "feishu-card"} <= names   # 软链也算 hermes 的


def test_claude_skips_borrowed_symlinks(tmp_path, monkeypatch):
    monkeypatch.setattr(tf_profile, "HOME", tmp_path)
    pool = tmp_path / ".agents" / "skills"
    _mk_skill(pool / "lark-base", "lark-base")
    cs = tmp_path / ".claude" / "skills"
    cs.mkdir(parents=True)
    (cs / "lark-base").symlink_to(pool / "lark-base")     # 借进 claude 目录
    _mk_skill(cs / "gstack", "gstack")                    # claude 自己装的真目录

    names = {s["name"] for s in tf_profile.detect_skills(str(tmp_path), "claude-code")["local"]}
    assert "gstack" in names and "lark-base" not in names  # 借来的软链不算


def test_codex_reads_own_model_not_claude(tmp_path, monkeypatch):
    """codex 卡的模型来自 ~/.codex/config.toml，不得借用同机 Claude 的 settings.json。"""
    monkeypatch.setattr(tf_profile, "HOME", tmp_path)
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text('model = "gpt-5-codex"\n', encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"model": "claude-opus-4-8"}', encoding="utf-8")
    cwd = tmp_path / "proj"; cwd.mkdir()
    cfg = tf_profile.detect_config(str(cwd), "codex")
    assert cfg and cfg.get("model") == "gpt-5-codex"   # 读自己的，不串 Claude 的


def test_codex_without_model_reports_none_not_borrowed(tmp_path, monkeypatch):
    """codex 没显式配 model（登录默认）时报 None —— 不谎报同机 Claude 的模型。"""
    monkeypatch.setattr(tf_profile, "HOME", tmp_path)
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text('approval_policy = "on-request"\n', encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"model": "claude-opus-4-8"}', encoding="utf-8")
    cwd = tmp_path / "proj"; cwd.mkdir()
    cfg = tf_profile.detect_config(str(cwd), "codex")
    assert cfg is None or "model" not in cfg   # 宁可不报，也不借 Claude 的
