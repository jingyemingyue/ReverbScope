"""Edge paths of :mod:`reverbscope.models.result_load`."""

from __future__ import annotations

import pytest

from reverbscope.errors import SessionError
from reverbscope.models.result_load import (
    _pair,
    _str_tuple,
    _validity,
    clipping_from_dict,
    dropouts_from_dict,
    excitation_band_from_dict,
    placement_from_dict,
    playback_speed_from_dict,
)


def test_pair_and_str_tuple_and_validity_edges() -> None:
    assert _pair(None) is None
    with pytest.raises(SessionError, match="pair of numbers"):
        _pair([1.0])
    assert _str_tuple(None) == ()
    with pytest.raises(TypeError, match="list of text"):
        _str_tuple("notes")
    with pytest.raises(TypeError, match="list of text"):
        _str_tuple(["ok", 1])
    with pytest.raises(SessionError, match="unknown validity"):
        _validity("not-a-validity")


def test_optional_loaders_return_none_for_missing_blocks() -> None:
    assert excitation_band_from_dict(None) is None
    assert clipping_from_dict(None) is None
    assert dropouts_from_dict(None) is None
    assert playback_speed_from_dict(None) is None
    assert placement_from_dict(None) is None


def test_dropouts_from_dict_rejects_bad_searched_window_or_run_list() -> None:
    with pytest.raises(TypeError, match="searched_s"):
        dropouts_from_dict({"searched_s": None, "dropouts": []})
    with pytest.raises(TypeError, match="must be a list"):
        dropouts_from_dict({"searched_s": [0.0, 1.0], "dropouts": "nope"})
    loaded = dropouts_from_dict(
        {
            "searched_s": [0.1, 0.9],
            "min_duration_ms": 2.0,
            "dropouts": [{"start_s": 0.2, "duration_ms": 3.0, "sweep_hz": 1000.0}],
        }
    )
    assert loaded is not None
    assert loaded.searched_s == (0.1, 0.9)
    assert loaded.dropouts[0].duration_ms == 3.0
