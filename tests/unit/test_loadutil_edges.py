"""Edge paths of :mod:`reverbscope.models.loadutil`."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from reverbscope.errors import ConfigurationError, SessionError
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.loadutil import (
    _typed,
    build_record,
    build_settings,
    settings_payload,
)


def test_settings_payload_rejects_non_objects() -> None:
    with pytest.raises(ConfigurationError, match="JSON object"):
        settings_payload([], set(), kind="sweep settings")  # type: ignore[arg-type]


def test_build_settings_reraises_configuration_errors() -> None:
    with pytest.raises(ConfigurationError, match="not supported"):
        build_settings(SweepSettings, {"sample_rate": 32_000}, kind="sweep settings")


def test_typed_returns_payload_for_non_dataclasses_and_converts_ints() -> None:
    assert _typed(dict, {"a": 1}) == {"a": 1}

    @dataclass(frozen=True)
    class Sample:
        count: int
        label: str | None = None

    assert _typed(Sample, {"count": 3, "label": None}) == {"count": 3, "label": None}


def test_build_record_reraises_session_errors() -> None:
    @dataclass(frozen=True)
    class Sample:
        count: int

        def __post_init__(self) -> None:
            raise SessionError("nested session problem")

    with pytest.raises(SessionError, match="nested session problem"):
        build_record(Sample, {"count": 1}, kind="project")
