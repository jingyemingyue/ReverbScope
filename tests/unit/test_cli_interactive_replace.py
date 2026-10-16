"""The menu replaces nothing that is there before a yes.

A take, a test signal or an analysis written to a name that is taken replaced
what was in it without a word, a second take inside one minute got the same
folder as the first (and replaced it), and a test signal without an audio
extension ended in libsndfile's English.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from reverbscope.cli.interactive import new_session_folder
from reverbscope.io.wav import has_audio_extension
from tests.menus import CTRL_C, drive

pytestmark = pytest.mark.usefixtures("_work_in_a_folder")


@pytest.fixture
def _work_in_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))


# --- A second take does not replace the first ----------------------------------------------


def test_a_second_default_folder_inside_the_minute_is_a_new_one(tmp_path: Path) -> None:
    moment = datetime(2026, 10, 9, 18, 50)
    first = new_session_folder(tmp_path, moment)
    assert first == tmp_path / "session-20261009-1850"
    first.mkdir()
    assert new_session_folder(tmp_path, moment) == tmp_path / "session-20261009-1850-2"
    (tmp_path / "session-20261009-1850-2").mkdir()
    assert new_session_folder(tmp_path, moment) == tmp_path / "session-20261009-1850-3"


def test_two_takes_in_a_row_are_offered_two_folders(tmp_path: Path) -> None:
    """Both prompts offered the same folder, and the second take replaced the first."""
    taken: list[list[str]] = []

    def run(argv: list[str]) -> int:
        taken.append(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True)
        (out / "session.json").write_text("{}")
        return 0

    visit = drive(["4", "", "", "y", "4", "", "", "y", "q"], prefix=["--backend", "fake"], run=run)
    assert visit.code == 0 and len(taken) == 2
    folders = [argv[argv.index("--out") + 1] for argv in taken]
    assert folders[0] != folders[1]
    assert len(list(tmp_path.glob("session-*"))) == 2


def test_a_folder_that_holds_a_session_is_replaced_only_after_a_yes(tmp_path: Path) -> None:
    held = tmp_path / "take"
    held.mkdir()
    (held / "session.json").write_text("{}")
    visit = drive(
        ["4", str(held), "n", str(tmp_path / "other"), "", "y", "q"], prefix=["--backend", "fake"]
    )
    assert "already holds a saved session. Replace it?" in " ".join(visit.prompts)
    assert [argv[argv.index("--out") + 1] for argv in visit.runs] == [str(tmp_path / "other")]
    # A yes replaces it, as the command line does.
    again = drive(["4", str(held), "y", "", "y", "q"], prefix=["--backend", "fake"])
    assert [argv[argv.index("--out") + 1] for argv in again.runs] == [str(held)]


def test_an_analysis_is_saved_over_a_session_only_after_a_yes(tmp_path: Path) -> None:
    for name in ("take.wav", "sweep.wav"):
        (tmp_path / name).write_bytes(b"RIFF")
    held = tmp_path / "saved"
    held.mkdir()
    (held / "session.json").write_text("{}")
    visit = drive(["3", "take.wav", "", str(held), "", "", "q"])
    # The sweep beside the recording is the default; the folder holds a session,
    # a plain Enter is no, and an empty answer then shows only.
    assert "already holds a saved session. Replace it? [y/N]: " in " ".join(visit.prompts)
    assert visit.runs == [["analyze", "--recording", "take.wav", "--sweep", "sweep.wav"]]
    saved = drive(["3", "take.wav", "", str(held), "y", "q"])
    assert saved.runs == [
        ["analyze", "--recording", "take.wav", "--sweep", "sweep.wav", "--out", str(held)]
    ]


# --- The test signal ------------------------------------------------------------------------


def test_a_test_signal_name_without_an_audio_extension_gets_wav(tmp_path: Path) -> None:
    visit = drive(["2", "测试信号", "", "q"])
    assert visit.runs[0][:3] == ["sweep", "--out", "测试信号.wav"]
    named = drive(["2", "my.flac", "", "q"])
    assert named.runs[0][:3] == ["sweep", "--out", "my.flac"]  # libsndfile knows .flac
    assert has_audio_extension("a/b.WAV") and has_audio_extension("x.aiff")
    assert not has_audio_extension("测试信号") and not has_audio_extension("take.2")


def test_a_file_that_exists_is_replaced_only_after_a_yes(tmp_path: Path) -> None:
    recording = tmp_path / "my-recording.wav"
    recording.write_bytes(b"precious")
    visit = drive(["2", "my-recording.wav", "n", "new.wav", "", "q"])
    assert "my-recording.wav already exists. Replace it? [y/N]: " in visit.prompts
    assert visit.runs[0][:3] == ["sweep", "--out", "new.wav"]
    assert recording.read_bytes() == b"precious"
    # Enter at the default name of a sweep that is there asks as well.
    (tmp_path / "sweep.wav").write_bytes(b"x")
    asked = drive(["2", "", "", "q"])
    assert "sweep.wav already exists. Replace it? [y/N]: " in asked.prompts
    assert asked.runs == []  # Enter at the question is no: nothing was written


def test_a_folder_is_not_a_test_signal(tmp_path: Path) -> None:
    (tmp_path / "recordings").mkdir()
    visit = drive(["2", "recordings", CTRL_C, "q"])
    example = Path("recordings") / "sweep.wav"  # the separator of the platform
    assert f"recordings is a folder; type a file name, for example {example}." in visit.text
    assert visit.runs == []
