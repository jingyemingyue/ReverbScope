"""``reverbscope common-slope`` over WAVs, sessions and a project folder."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from reverbscope.cli.main import main
from reverbscope.io.wav import write_wav
from reverbscope.schemas import load_schema
from tests.unit.test_common_slope import room


@pytest.fixture(scope="module")
def wavs(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    folder = tmp_path_factory.mktemp("common-slope-wavs")
    paths = []
    for item in room((0.4, 1.6), 4, seed=11):
        path = folder / f"{item.position}.wav"
        peak = float(np.max(np.abs(item.samples)))
        write_wav(path, item.samples / (2.0 * peak), item.sample_rate, subtype="FLOAT")
        paths.append(path)
    return paths


def test_wavs_report_and_files(
    wavs: list[Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "common"
    code = main(["common-slope", *map(str, wavs), "--band", "20", "7000", "--out", str(out)])
    text = capsys.readouterr().out
    assert code == 0
    assert "Common decay times" in text
    assert "4 positions" in text
    names = sorted(p.name for p in out.iterdir())
    assert names == ["common-slope-bands.csv", "common-slope-positions.csv", "common-slope.json"]
    payload = json.loads((out / "common-slope.json").read_text(encoding="utf-8"))
    Draft202012Validator(load_schema("common-slope")).validate(payload)
    assert payload["positions"] == ["P1", "P2", "P3", "P4"]
    one_k = next(b for b in payload["bands"] if b["band_label"] == "1 kHz")
    assert one_k["selected_slopes"] == 2
    assert one_k["decay_times_s"] == pytest.approx([0.4, 1.6], rel=0.08)


def test_json_output_and_options(wavs: list[Path], capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "--format",
            "json",
            "common-slope",
            *map(str, wavs[:2]),
            "--band",
            "20",
            "7000",
            "--max-slopes",
            "1",
            "--amplitudes",
            "edc",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["amplitude_method"] == "edc"
    assert payload["max_slopes"] == 1
    assert all(b["selected_slopes"] in (1, None) for b in payload["bands"])


def test_wav_without_band_is_refused(wavs: list[Path], capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["common-slope", str(wavs[0])])
    assert code != 0
    assert "--band" in capsys.readouterr().err


def test_same_file_twice_gets_two_labels(
    wavs: list[Path], capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["--format", "json", "common-slope", str(wavs[0]), str(wavs[0]), "--band", "20", "7000"]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["positions"] == ["P1", "P1 (2)"]


def test_project_folder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The demo sessions listed in a project: one position per take."""
    demo = tmp_path / "demo"
    assert main(["demo", "--out", str(demo)]) == 0
    project = tmp_path / "project"
    assert main(["project", "init", "--out", str(project)]) == 0
    assert main(["project", "add", str(project), str(demo / "position-a"), "--position", "A"]) == 0
    assert main(["project", "add", str(project), str(demo / "position-b"), "--position", "B"]) == 0
    capsys.readouterr()
    assert main(["--format", "json", "common-slope", str(project)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["positions"] == ["A", "B"]
    assert any(b["selected_slopes"] for b in payload["bands"])
    # Session folders work as inputs too.
    assert main(["--format", "json", "common-slope", str(demo / "position-a")]) == 0
    assert json.loads(capsys.readouterr().out)["positions"]
