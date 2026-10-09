"""Measuring from the menu: only where a take can be made.

The take is the one item that makes a sound. Without an input and an output
device the menu stops before asking anything and points to ``reverbscope
doctor``; the questions of a take that cannot be made are not asked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reverbscope.audio.backend import DeviceInfo
from reverbscope.cli.interactive import audio_problems
from reverbscope.errors import AudioBackendUnavailableError
from tests.menus import drive


@pytest.fixture(autouse=True)
def _work_in_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _device(index: int, *, inputs: int, outputs: int) -> DeviceInfo:
    return DeviceInfo(
        index=index,
        name=f"Device {index}",
        max_input_channels=inputs,
        max_output_channels=outputs,
        default_sample_rate=48000.0,
        host_api="ALSA",
        is_default_input=inputs > 0,
        is_default_output=outputs > 0,
    )


class _Devices:
    """A backend that lists the devices it is given and plays nothing."""

    name = "portaudio"

    def __init__(self, *devices: DeviceInfo) -> None:
        self.devices = list(devices)

    def list_devices(self) -> list[DeviceInfo]:
        return self.devices


# --- No device ------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
@pytest.mark.parametrize(
    ("devices", "said"),
    [
        ((), ["no audio input device found", "no audio output device found"]),
        ((_device(0, inputs=2, outputs=0),), ["no audio output device found"]),
        ((_device(0, inputs=0, outputs=2),), ["no audio input device found"]),
    ],
    ids=["none", "input-only", "output-only"],
)
def test_a_take_without_the_devices_to_make_it_stops_before_the_questions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    lang: str,
    devices: tuple[DeviceInfo, ...],
    said: list[str],
) -> None:
    """With nothing to choose from the menu asked for the folder, then the
    safety question, ran the take and failed with PortAudio's words."""
    monkeypatch.setattr(
        "reverbscope.audio.backend.get_backend", lambda name=None: _Devices(*devices)
    )
    visit = drive(["4", "", "q"], lang=lang)
    assert visit.code == 0 and visit.runs == []
    # Only the menu's own questions: the choice, then the choice again.
    assert len(visit.prompts) == 3 and not any("session" in p for p in visit.prompts[1:2])
    assert visit.prompts[1] == visit.prompts[0]
    from reverbscope.i18n import activate

    activate(lang)
    try:
        from reverbscope.i18n import _

        for sentence in said:
            assert _(sentence) in visit.text.replace("│", " ")
        assert _("Nothing was played.") in visit.text
    finally:
        activate("en")
    assert "reverbscope doctor" in visit.text
    assert not list(tmp_path.glob("session-*"))
    if lang == "zh_CN":
        assert "Nothing was played" not in visit.text


def test_a_backend_that_cannot_load_is_said_in_words_and_points_to_doctor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def get_backend(name: str | None = None) -> _Devices:
        raise AudioBackendUnavailableError("the PortAudio library was not found")

    monkeypatch.setattr("reverbscope.audio.backend.get_backend", get_backend)
    visit = drive(["4", "q"])
    assert visit.runs == [] and visit.code == 0
    assert "the PortAudio library was not found" in visit.text
    assert "reverbscope doctor" in visit.text and "Nothing was played." in visit.text
    assert audio_problems(None) == ["the PortAudio library was not found"]


def test_the_simulated_interface_can_always_measure() -> None:
    assert audio_problems("fake") == []
