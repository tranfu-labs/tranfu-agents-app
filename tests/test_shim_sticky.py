"""shim_version sticky 语义契约测试 —— 对应 openspec/changes/fix-shim-version-reporting。

核心场景:活跃 agent 心跳大多数事件不会重传 shim_version(协议允许只有 SessionStart
等少数事件带这个字段),服务端必须按 agent 身份独立保留最近一次非空上报值,
不被 profile 全量替换或后续无字段心跳清掉。
"""
from conftest import ev


def _card(client, *, operator="alice", agent_or_runtime="codex"):
    """从 /api/state 取指定身份的卡片(operator + (agent or runtime))。"""
    state = client.get("/api/state").json()
    for c in state["sessions"]:
        if c["operator"] != operator:
            continue
        ak = c.get("agent") or c["runtime"]
        if ak == agent_or_runtime:
            return c
    return None


def test_shim_version_top_level_field_is_recorded(client):
    assert ev(client, shim_version="abc12345").status_code == 200
    c = _card(client)
    assert c is not None and c.get("shim_version") == "abc12345"


def test_shim_version_is_sticky_across_heartbeats_without_field(client):
    """这是修复的核心契约:第一次带 → 后续心跳不带 → 服务端必须仍把它呈现在卡片上。
    旧实现把 shim_version 放进 profile 走全量替换,导致心跳一不带就丢字段、
    前端误判为「旧 shim」。"""
    ev(client, shim_version="abc12345", current_step="session start")
    ev(client, current_step="tool: Bash")          # no shim_version field
    ev(client, current_step="tool: Read")           # no shim_version field
    c = _card(client)
    assert c is not None
    assert c.get("shim_version") == "abc12345"


def test_shim_version_updates_to_new_non_empty_value(client):
    ev(client, shim_version="aaa", current_step="step a")
    ev(client, shim_version="bbb", current_step="step b")
    c = _card(client)
    assert c.get("shim_version") == "bbb"


def test_empty_string_shim_version_does_not_clear_sticky(client):
    """空串不算上报。如果客户端 manifest 一时读不到,不能让看板回退到 unknown。"""
    ev(client, shim_version="abc12345", current_step="s1")
    ev(client, shim_version="", current_step="s2")
    ev(client, shim_version="   ", current_step="s3")
    c = _card(client)
    assert c.get("shim_version") == "abc12345"


def test_missing_shim_version_shows_as_null_for_new_agents(client):
    """从未上报过 shim_version 的 agent,/api/state 必须返回 None/null,
    让前端走 unknown 灰态,而不是误判为「旧 shim」。"""
    ev(client, current_step="hello")
    c = _card(client)
    assert c is not None
    assert c.get("shim_version") in (None, "")


def test_profile_full_replace_does_not_erase_shim_version(client):
    """profile 中其它字段全量替换时,sticky 表里的 shim_version 不能被牵连清掉。"""
    ev(client, shim_version="abc12345",
       mcp=["chrome-devtools", "pencil"], skills={"local": [{"name": "s1"}]})
    # 后续 profile 全量替换:不带 shim_version,且 mcp/skills 内容也变了
    ev(client, mcp=["only-one"], skills={"local": []})
    c = _card(client)
    assert c.get("shim_version") == "abc12345"
    assert c.get("mcp") == ["only-one"]


def test_sticky_per_agent_identity(client):
    """同 operator 下,两个 agent 各自独立 sticky;一个升级了不影响另一个的 unknown。"""
    ev(client, agent="meiyangyang", shim_version="newshim")
    ev(client, agent="feiyangyang")  # 从未上报
    a = _card(client, agent_or_runtime="meiyangyang")
    b = _card(client, agent_or_runtime="feiyangyang")
    assert a.get("shim_version") == "newshim"
    assert b.get("shim_version") in (None, "")
