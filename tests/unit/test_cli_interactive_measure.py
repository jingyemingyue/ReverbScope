"""Measuring from the menu: nothing is played until a yes, once, and only if it can be.

The take is the one item that makes a sound. Without an input and an output
device it stops before asking anything and points to ``reverbscope doctor``;
the note about the monitors is shown once, before the question; Enter, Ctrl+C,
Ctrl+D and anything but a typed yes play nothing; a level above -12 dBFS needs
a yes of its own and adds ``--acknowledge-level``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from reverbscope.audio.backend import DeviceInfo
from reverbscope.cli.interactive import audio_problems, level_dbfs, output_base
from reverbscope.cli.main import main
from reverbscope.cli.render import SAFETY_NOTE_SHOWN
from reverbscope.errors import AudioBackendUnavailableError
from reverbscope.settings import UserSettings, save_settings
from tests.menus import CTRL_C, CTRL_D, drive

FAKE = ["--backend", "fake"]
NOTE = "Start with your monitor/interface output at a low level"


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


# --- Nothing plays without a yes -------------------------------------------------------------


@pytest.mark.parametrize("answer", ["", "n", "N", "no", "ok", "yy", "yes please", "好", "是吗"])
def test_nothing_is_played_without_an_explicit_y(answer: str) -> None:
    visit = drive(["4", "", "", answer, "q"], prefix=FAKE)
    assert visit.code == 0 and visit.runs == []
    assert visit.text.count("Nothing was played.") == 1


@pytest.mark.parametrize("answer", ["y", "Y", "yes", "ｙ", " y "])
def test_a_typed_yes_plays(answer: str) -> None:
    visit = drive(["4", "take-1", "", answer, "q"], prefix=FAKE)
    assert visit.runs == [[*FAKE, "measure", "--out", "take-1"]]


@pytest.mark.parametrize("key", [CTRL_C, CTRL_D], ids=["ctrl-c", "ctrl-d"])
def test_a_key_at_the_question_plays_nothing(key: BaseException) -> None:
    visit = drive(["4", "take-1", "", key, "q"], prefix=FAKE)
    assert visit.runs == []
    if key is CTRL_C:
        assert visit.code == 0 and "Back to the menu." in visit.text
    else:
        assert visit.code == 0
        assert len(visit.prompts) == 4  # the end of input left the menu: no 'q' was read


@pytest.mark.parametrize("key", [CTRL_C, CTRL_D], ids=["ctrl-c", "ctrl-d"])
def test_a_key_at_the_loud_level_question_plays_nothing(key: BaseException) -> None:
    visit = drive(["4", "take-1", "-6", key, "q"], prefix=FAKE)
    assert visit.runs == []


# --- The level ------------------------------------------------------------------------------


def test_the_level_asked_is_the_one_the_command_uses_and_the_default_is_left_out() -> None:
    visit = drive(
        ["4", "a", "", "y", "4", "b", "-30", "y", "4", "c", "－３０．５", "y", "q"], prefix=FAKE
    )
    assert visit.runs == [
        [*FAKE, "measure", "--out", "a"],
        [*FAKE, "measure", "--out", "b", "--level", "-30"],
        [*FAKE, "measure", "--out", "c", "--level", "-30.5"],
    ]
    assert visit.prompts[2] == "Level of the sweep in dBFS [-20]: "
    assert "at -20 dBFS" in visit.text and "at -30 dBFS" in visit.text


@pytest.mark.parametrize(
    "typed", ["loud", "5", "1", "-81", "-1000", "nan", "inf", "1e3", "-6.5.1", "--6"]
)
def test_a_level_that_is_not_one_is_refused_in_words(typed: str) -> None:
    visit = drive(["4", "a", typed, "", "n", "q"], prefix=FAKE)
    assert visit.text.count("Type a level from -80 to 0 dBFS.") == 1
    assert visit.runs == []


@pytest.mark.parametrize(
    ("typed", "value"),
    [("-20", -20.0), ("0", 0.0), ("-80", -80.0), ("-6.5", -6.5), ("－６", -6.0), ("−6", -6.0),
     ("-81", None), ("+1", None), ("", None), ("x", None), ("nan", None), ("1" * 5000, None)],
)  # fmt: skip
def test_level_dbfs(typed: str, value: float | None) -> None:
    assert level_dbfs(typed) == value


def test_a_level_above_minus_12_needs_a_yes_of_its_own_and_adds_the_acknowledgement() -> None:
    # No to "is the monitor turned down?": the level is asked again.
    visit = drive(["4", "a", "-6", "n", "", "y", "q"], prefix=FAKE)
    assert visit.runs == [[*FAKE, "measure", "--out", "a"]]
    assert (
        visit.text.count("-6 dBFS is above -12 dBFS. Is the monitor level already turned down?")
        == 1
    )
    # Yes: the command is given the acknowledgement it would refuse without.
    visit = drive(["4", "a", "-6", "y", "y", "q"], prefix=FAKE)
    assert visit.runs == [[*FAKE, "measure", "--out", "a", "--level", "-6", "--acknowledge-level"]]
    # The acknowledgement is not the answer to "play now?": that is asked after it.
    visit = drive(["4", "a", "0", "y", "", "q"], prefix=FAKE)
    assert visit.runs == []
    assert visit.text.count("Nothing was played.") == 1
    # At -12 and below there is nothing to confirm.
    visit = drive(["4", "a", "-12", "y", "q"], prefix=FAKE)
    assert visit.runs == [[*FAKE, "measure", "--out", "a", "--level", "-12"]]


def test_a_loud_level_in_the_command_is_refused_without_the_acknowledgement(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([*FAKE, "measure", "--out", "x", "--level", "-6"]) == 2
    assert "--acknowledge-level" in capsys.readouterr().err


# --- The note about the monitors, once ------------------------------------------------------


def test_the_note_about_the_monitors_is_shown_once_in_the_menu_flow(
    capsys: pytest.CaptureFixture[str],
) -> None:
    visit = drive(["4", "take-1", "", "y", "q"], prefix=FAKE, run=main, out=sys.stdout)
    out = capsys.readouterr().out
    assert visit.code == 0
    assert out.count(NOTE) == 1
    # It comes before the question, and the take after it.
    assert out.index(NOTE) < out.index("The same from the command line:")
    assert "Recorded" in out and (Path("take-1") / "session.json").is_file()
    assert SAFETY_NOTE_SHOWN.get() is False  # the menu put it back


def test_a_measure_typed_by_hand_still_shows_the_note(capsys: pytest.CaptureFixture[str]) -> None:
    drive(["4", "take-1", "", "y", "q"], prefix=FAKE, run=main, out=sys.stdout)
    capsys.readouterr()
    assert main([*FAKE, "measure", "--out", "by-hand", "--duration", "1"]) == 0
    assert capsys.readouterr().out.count(NOTE) == 1


def test_the_note_is_in_the_menu_before_the_question_even_when_nothing_is_played() -> None:
    visit = drive(["4", "take-1", "", "n", "q"], prefix=FAKE)
    assert visit.text.count(NOTE) == 1
    assert visit.text.index(NOTE) < visit.text.index("Nothing was played.")
    assert "at -20 dBFS" in visit.text and "-12 dBFS" not in visit.text


# --- Where new sessions start ---------------------------------------------------------------


def test_new_sessions_start_in_the_output_folder_of_the_settings(tmp_path: Path) -> None:
    assert output_base() == Path()
    folder = tmp_path / "My Takes 录音"
    folder.mkdir()
    save_settings(UserSettings(output_dir=str(folder)))
    assert output_base() == folder
    visit = drive(["4", "", "", "n", "q"], prefix=FAKE)
    # The folder is a default that does not fit beside the question: the hint stays whole.
    assert "Folder for the new session" in visit.lines
    assert visit.prompts[1].startswith(f"[{folder}{os.sep}session-")
    # An output folder that is gone is not a place to start.
    folder.rmdir()
    assert output_base() == Path()
