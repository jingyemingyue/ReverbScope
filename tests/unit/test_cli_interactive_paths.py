"""The menu's file, folder and project questions say what is wrong.

A folder passed for a recording was accepted and reported as a missing file one
step later, a default with a backslash could not be taken with Enter, and a
folder that is not a project ended with ``no project.json`` and no way on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.menus import CTRL_C, drive

pytestmark = pytest.mark.usefixtures("_work_in_a_folder")


@pytest.fixture
def _work_in_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))


# --- Files and folders ----------------------------------------------------------------------


def test_a_folder_is_refused_for_a_recording_in_words(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    visit = drive(["3", "demo", CTRL_C, "q"])
    assert "demo is a folder, not a file; try again, or leave empty to go back." in visit.text
    assert visit.runs == []


def test_a_default_with_a_backslash_is_taken_as_it_is(tmp_path: Path) -> None:
    """Enter at ``[bs\\dir/sweep.wav]`` went through the cleaning of a pasted path,
    which removes backslashes: the file it offered did not exist."""
    folder = tmp_path / "bs\\dir"
    folder.mkdir()
    (folder / "take.wav").write_bytes(b"RIFF")
    (folder / "sweep.wav").write_bytes(b"RIFF")
    recording = str(folder / "take.wav").replace("\\", "\\\\")
    visit = drive(["3", recording, "", "", "q"])
    assert visit.runs, visit.text
    assert visit.runs[0][-2:] == ["--sweep", str(folder / "sweep.wav")]
    assert "does not exist" not in visit.text


def test_a_folder_that_is_not_a_project_says_how_to_make_one(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    (tmp_path / "room").mkdir()
    (tmp_path / "room" / "project.json").write_text("{}")
    visit = drive(["7", "plain", "room", "q"])
    assert "has no project.json; make a project first with reverbscope project init" in visit.text
    assert visit.runs == [["project", "overview", "room"]]
    zh = drive(["7", "plain", CTRL_C, "q"], lang="zh_CN")
    assert "里没有 project.json；请先用 reverbscope project init --out <文件夹> 建立项目" in zh.text
