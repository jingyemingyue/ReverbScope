"""What each recording profile wants, in words, before a measurement."""

from __future__ import annotations

import json

from reverbscope.i18n import activate
from reverbscope.interpretation import available_profiles
from reverbscope.interpretation.explain import (
    explain_all,
    explain_profile,
    profile_description,
)
from reverbscope.interpretation.profiles import get_profile


def test_every_profile_is_explained_from_its_own_thresholds() -> None:
    explained = {item.name: item for item in explain_all()}
    assert set(explained) == set(available_profiles())
    for name, item in explained.items():
        profile = get_profile(name)
        joined = " ".join(item.wants)
        assert f"{profile.long_decay_s:.1f} s" in joined
        assert f"{profile.strong_reflection_db:.0f} dB" in joined
        assert item.description and item.title
        assert item.thresholds["long_decay_s"] == profile.long_decay_s
        assert json.dumps(item.to_dict())


def test_the_drums_profile_says_what_it_does_not_judge() -> None:
    drums = explain_profile("drums")
    assert any("Clarity" in line and "not judged" in line for line in drums.skips)
    assert any("noise floor" in line for line in drums.skips)
    assert not any("Clarity" in line for line in drums.wants)
    assert not any("Noise" in line for line in drums.wants)
    room = explain_profile("room_mic")
    assert any("too dry" in line for line in room.wants)
    assert room.skips == ()
    vocal = explain_profile("vocal")
    assert any("C50 below +2 dB" in line for line in vocal.wants)


def test_explanations_are_translated() -> None:
    activate("zh_CN")
    try:
        item = explain_profile("vocal")
        texts = [item.title, item.description, *item.wants, *item.skips]
    finally:
        activate("en")
    assert item.locale == "zh_CN"
    assert all(any("一" <= ch <= "鿿" for ch in text) for text in texts), texts
    assert profile_description("generic") == (
        "General observations, not tied to a specific instrument or voice."
    )
    assert profile_description("no-such-profile") == ""
