"""The regression corpus: every file under files/ does what manifest.json says.

See README.md in this folder for what belongs here and how a community
report becomes an entry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reverbscope import errors
from reverbscope.cli.render import REPORT_CONSOLE, render_analysis
from reverbscope.health import assess
from reverbscope.interpretation import interpret
from reverbscope.io.project_store import load_project
from reverbscope.io.session_store import load_comparison, load_measurement, load_session
from reverbscope.io.wav import read_sweep_sidecar, read_wav

CORPUS = Path(__file__).resolve().parent
FILES = CORPUS / "files"
MANIFEST: dict[str, Any] = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
ENTRIES: list[dict[str, Any]] = MANIFEST["entries"]


def _load(entry: dict[str, Any]) -> dict[str, Any]:
    """Read the entry's file the way ReverbScope does; return what to check."""
    path = FILES / entry["path"]
    loader = entry["loader"]
    if loader == "wav":
        signal = read_wav(path)
        return {
            "n_samples": signal.n_samples,
            "n_channels": signal.n_channels,
            "sample_rate": signal.sample_rate,
        }
    if loader == "sidecar":
        settings = read_sweep_sidecar(path)
        assert settings is not None
        return {"sample_rate": settings.sample_rate}
    if loader == "session":
        loaded = load_measurement(path)
        load_session(path)
        report = assess(loaded.result)
        # A file that loads must also render: the report and the findings
        # are what a user opening the session sees.
        render_analysis(REPORT_CONSOLE, loaded.result, interpret(loaded.result), "generic")
        return {"sample_rate": loaded.result.sample_rate, "health_overall": str(report.overall)}
    if loader == "project":
        return {"name": load_project(path).name}
    if loader == "comparison":
        return {"comparable": load_comparison(path).comparable}
    raise AssertionError(f"unknown loader {loader!r} in the manifest")


@pytest.mark.parametrize("entry", ENTRIES, ids=[entry["path"] for entry in ENTRIES])
def test_corpus_entry(entry: dict[str, Any]) -> None:
    assert entry["reason"].strip(), entry["path"]
    if entry["expect"] == "loads":
        found = _load(entry)
        for key, value in entry.get("checks", {}).items():
            assert found[key] == value, (entry["path"], key, found[key])
        return
    assert entry["expect"] == "refused", entry["path"]
    error = getattr(errors, entry["error"])
    with pytest.raises(error, match=entry.get("match") or None):
        _load(entry)


def test_every_corpus_file_has_an_entry() -> None:
    """A fixture nobody can explain is dead weight: every file is listed."""
    listed = {entry["path"] for entry in ENTRIES}
    folders = {path for path in listed if (FILES / path).is_dir()}
    unlisted = []
    for file in sorted(FILES.rglob("*")):
        if not file.is_file():
            continue
        relative = file.relative_to(FILES).as_posix()
        if relative in listed or any(relative.startswith(folder + "/") for folder in folders):
            continue
        unlisted.append(relative)
    assert unlisted == []


def test_every_entry_exists_and_is_small() -> None:
    """A corpus file is a minimal sample: no entry is larger than 64 KB."""
    for entry in ENTRIES:
        path = FILES / entry["path"]
        assert path.exists(), entry["path"]
        files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
        for file in files:
            assert file.stat().st_size <= 64 * 1024, file
