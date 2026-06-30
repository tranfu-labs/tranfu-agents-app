from server.profile import reuse_map


def test_reuse_map_accepts_legacy_list_skill_profiles():
    profiles = {
        "alice\x00agent": {"skills": [{"name": "shared"}, "solo"]},
        "bob\x00agent": {"skills": ["shared"]},
    }

    assert reuse_map(profiles) == {
        "alice\x00agent": 0.5,
        "bob\x00agent": 1.0,
    }
