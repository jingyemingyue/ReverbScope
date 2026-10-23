"""A failed CSV export must not truncate or mix curves already in the folder.

The exporter used to open each final path with ``"w"``. That truncates the
previous file before the new bytes are written, and a missing curve was
deleted as soon as that one file was reached. These tests lock the failure
behaviour: previous bytes and their SHA-256 stay, a file the export does not
own stays, and a restore that itself fails is reported as incomplete.
"""

from __future__ import annotations

import errno
import hashlib
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from reverbscope.errors import SessionError
from reverbscope.io.exporters import csv as csv_export
from reverbscope.models.result import AnalysisResult

_CURVE_HEADERS = {
    "decay_metrics.csv": "band,metric,seconds,validity_or_basis",
    "energy_metrics.csv": "band,metric,value,unit,validity",
    "decay_edc.csv": "band,time_s,edc_db",
    "frequency_response.csv": "frequency_hz,magnitude_db_raw,magnitude_db_smoothed",
    "interface_response.csv": "frequency_hz,magnitude_db",
    "noise_psd.csv": "frequency_hz,psd_db",
    "reflections.csv": "delay_ms,relative_db",
    "resonances.csv": (
        "frequency_hz,level_above_baseline_db,narrowband_decay_20db_s,"
        "decay_distinguishable,filter_ringing_20db_s,surroundings_decay_20db_s"
    ),
}


def _snapshot(folder: Path) -> dict[str, bytes]:
    """Bytes of every visible file. Hidden staging names are reported separately."""
    return {
        path.name: path.read_bytes()
        for path in folder.iterdir()
        if path.is_file() and not path.name.startswith(".")
    }


def _digests(files: dict[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


def _hidden(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir() if path.name.startswith("."))


def _assert_unchanged(folder: Path, before: dict[str, bytes]) -> None:
    after = _snapshot(folder)
    assert _digests(after) == _digests(before)
    assert after == before
    assert _hidden(folder) == []


def _prepare(folder: Path, result: AnalysisResult) -> dict[str, bytes]:
    written = csv_export.export_csv(result, folder)
    assert written
    assert "frequency_response.csv" in _snapshot(folder)
    (folder / "notes.txt").write_text("mine", encoding="utf-8")
    before = _snapshot(folder)
    assert before["notes.txt"] == b"mine"
    return before


def _fail_open(monkeypatch: pytest.MonkeyPatch, names: set[str], err: int) -> None:
    """Raise ``err`` once a named curve, or its hidden staging file, is opened for write."""
    real_open = Path.open

    def open_and_fail(self: Path, mode: str = "r", *args: object, **kwargs: object):
        stems = {Path(name).stem for name in names}
        staged = self.name.startswith(".") and any(
            self.name.startswith(f".{stem}.") for stem in stems
        )
        if "w" in mode and (self.name in names or staged):
            handle = real_open(self, mode, *args, **kwargs)  # type: ignore[arg-type]
            handle.close()
            raise OSError(err, os.strerror(err), str(self))
        return real_open(self, mode, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "open", open_and_fail)


def _fail_exclusive_create(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the ``O_EXCL`` create used for a hidden file beside the destination."""
    real_open = os.open

    def open_and_fail(path: int | str | bytes, flags: int, *args: object, **kwargs: object):
        text = os.fsdecode(path)
        if Path(text).name.startswith(".") and flags & os.O_EXCL:
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC), text)
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", open_and_fail)


def _replace_guard(
    monkeypatch: pytest.MonkeyPatch,
    decide: Callable[[str, str, dict[str, int]], OSError | None],
) -> dict[str, int]:
    real_replace = os.replace
    seen = {"energy": 0, "decay": 0}

    def guarded(src: str | bytes, dst: str | bytes, *args: object, **kwargs: object) -> None:
        src_name = Path(os.fsdecode(src)).name
        dst_name = Path(os.fsdecode(dst)).name
        if dst_name == "energy_metrics.csv" and src_name.startswith("."):
            seen["energy"] += 1
        if dst_name == "decay_metrics.csv" and src_name.startswith("."):
            seen["decay"] += 1
        failure = decide(src_name, dst_name, seen)
        if failure is not None:
            raise failure
        real_replace(src, dst, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "replace", guarded)
    return seen


def _relabelled(result: AnalysisResult) -> AnalysisResult:
    return replace(
        result,
        decay=replace(
            result.decay,
            broadband=replace(result.decay.broadband, band_label="CHANGED-LABEL"),
        ),
    )


def test_an_oserror_while_writing_a_curve_keeps_previous_csv_bytes(
    tmp_path: Path, analysed_result: AnalysisResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``open("w")`` truncated ``frequency_response.csv`` before the write failed."""
    before = _prepare(tmp_path, analysed_result)
    _fail_open(monkeypatch, {"frequency_response.csv"}, errno.EIO)
    with pytest.raises(SessionError, match="cannot write") as exc:
        csv_export.export_csv(analysed_result, tmp_path)
    assert "recovery is incomplete" not in str(exc.value)
    _assert_unchanged(tmp_path, before)


def test_a_full_disk_while_writing_a_curve_keeps_previous_csv_bytes(
    tmp_path: Path, analysed_result: AnalysisResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full disk raised after the same truncate, so one curve was left empty."""
    before = _prepare(tmp_path, analysed_result)
    _fail_open(monkeypatch, {"frequency_response.csv"}, errno.ENOSPC)
    with pytest.raises(SessionError, match="cannot write") as exc:
        csv_export.export_csv(analysed_result, tmp_path)
    assert "No space left" in str(exc.value)
    assert "recovery is incomplete" not in str(exc.value)
    _assert_unchanged(tmp_path, before)


def test_a_temporary_file_that_cannot_be_created_leaves_previous_csv_bytes(
    tmp_path: Path, analysed_result: AnalysisResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Creating the hidden staging file must fail before any final path is opened."""
    before = _prepare(tmp_path, analysed_result)
    _fail_exclusive_create(monkeypatch)
    with pytest.raises(SessionError, match="cannot write") as exc:
        csv_export.export_csv(analysed_result, tmp_path)
    assert "No space left" in str(exc.value)
    _assert_unchanged(tmp_path, before)


def test_a_failed_replace_restores_curves_already_published(
    tmp_path: Path, analysed_result: AnalysisResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first curve of a new export must not stay behind when the next replace fails."""
    before = _prepare(tmp_path, analysed_result)

    def fail_energy_publish(src_name: str, dst_name: str, seen: dict[str, int]) -> OSError | None:
        if dst_name == "energy_metrics.csv" and src_name.startswith(".") and seen["energy"] == 1:
            return OSError(errno.ENOSPC, os.strerror(errno.ENOSPC), str(tmp_path / dst_name))
        return None

    _replace_guard(monkeypatch, fail_energy_publish)
    with pytest.raises(SessionError, match="cannot write") as exc:
        csv_export.export_csv(_relabelled(analysed_result), tmp_path)
    assert "recovery is incomplete" not in str(exc.value)
    assert "fully restored" not in str(exc.value)
    _assert_unchanged(tmp_path, before)
    assert b"CHANGED-LABEL" not in (tmp_path / "decay_metrics.csv").read_bytes()


def test_a_failed_publish_removes_curves_this_call_created(
    tmp_path: Path, analysed_result: AnalysisResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A curve published into an empty folder is removed when a later replace fails."""
    (tmp_path / "notes.txt").write_text("mine", encoding="utf-8")
    before = _snapshot(tmp_path)

    def fail_energy_publish(src_name: str, dst_name: str, seen: dict[str, int]) -> OSError | None:
        if dst_name == "energy_metrics.csv" and src_name.startswith(".") and seen["energy"] == 1:
            return OSError(errno.EIO, os.strerror(errno.EIO), str(tmp_path / dst_name))
        return None

    _replace_guard(monkeypatch, fail_energy_publish)
    with pytest.raises(SessionError, match="cannot write") as exc:
        csv_export.export_csv(analysed_result, tmp_path)
    assert "recovery is incomplete" not in str(exc.value)
    _assert_unchanged(tmp_path, before)


def test_a_failed_export_keeps_a_curve_the_new_result_does_not_have(
    tmp_path: Path, analysed_result: AnalysisResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting a missing curve before the later files succeed dropped the previous one."""
    before = _prepare(tmp_path, analysed_result)
    slim = AnalysisResult.from_dict(analysed_result.to_dict(include_curves=False))
    _fail_open(monkeypatch, {"reflections.csv"}, errno.EIO)
    with pytest.raises(SessionError, match="cannot write"):
        csv_export.export_csv(slim, tmp_path)
    _assert_unchanged(tmp_path, before)
    assert "frequency_response.csv" in _snapshot(tmp_path)


def test_a_successful_export_drops_a_curve_the_result_does_not_have(
    tmp_path: Path, analysed_result: AnalysisResult
) -> None:
    """Once publish finishes, a curve this result lacks must not keep the previous file."""
    csv_export.export_csv(analysed_result, tmp_path)
    (tmp_path / "notes.txt").write_text("mine", encoding="utf-8")
    slim = AnalysisResult.from_dict(analysed_result.to_dict(include_curves=False))
    written = csv_export.export_csv(slim, tmp_path)
    names = {path.name for path in written}
    assert "frequency_response.csv" not in names
    left = {path.name for path in tmp_path.iterdir()}
    assert left == names | {"notes.txt"}
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "mine"
    assert _hidden(tmp_path) == []


def test_a_successful_export_keeps_paths_columns_precision_and_return_values(
    tmp_path: Path, analysed_result: AnalysisResult, short_sweep: object
) -> None:
    """Final paths, column names, CSV float text and the returned list stay compatible."""
    from dataclasses import replace as replace_result

    import numpy as np

    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.models.configuration import SweepSettings
    from reverbscope.models.result import LoopbackResult
    from tests.conftest import make_rir

    written = csv_export.export_csv(analysed_result, tmp_path)
    assert written == [tmp_path / path.name for path in written]
    present = [path.name for path in written]
    assert present == [name for name in _CURVE_HEADERS if name in set(present)]
    for path in written:
        header = path.read_text(encoding="utf-8").splitlines()[0]
        assert header == _CURVE_HEADERS[path.name]
    again = csv_export.export_csv(analysed_result, tmp_path / "copy")
    assert [path.name for path in again] == present

    sweep = short_sweep
    assert isinstance(sweep, SweepSettings)
    result = analyze(
        synthetic_recording(sweep, make_rir(sweep.sample_rate, rt60_s=0.35), noise_rms=1e-5),
        Reference.from_settings(sweep),
    )
    loopback = LoopbackResult(
        channel=1,
        compensation_applied=True,
        interface_response_hz=np.array([100.0, 1000.0, 10000.0]),
        interface_response_db=np.array([-0.5, 0.0, -1.0]),
    )
    with_loopback = replace_result(
        result,
        impulse_response=replace_result(result.impulse_response, loopback=loopback),
    )
    folder = tmp_path / "loopback"
    returned = csv_export.export_csv(with_loopback, folder)
    assert folder / "interface_response.csv" in returned
    lines = (folder / "interface_response.csv").read_text(encoding="utf-8").splitlines()
    assert lines == ["frequency_hz,magnitude_db", "100.0,-0.5", "1000.0,0.0", "10000.0,-1.0"]
    assert _hidden(folder) == []


def test_a_failed_restore_keeps_the_backup_and_reports_incomplete_recovery(
    tmp_path: Path, analysed_result: AnalysisResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the backup cannot be put back, the error must not claim a full recovery."""
    before = _prepare(tmp_path, analysed_result)
    original_decay = before["decay_metrics.csv"]

    def fail_publish_and_restore(
        src_name: str, dst_name: str, seen: dict[str, int]
    ) -> OSError | None:
        if dst_name == "energy_metrics.csv" and src_name.startswith(".") and seen["energy"] == 1:
            return OSError(errno.EIO, os.strerror(errno.EIO), str(tmp_path / dst_name))
        if dst_name == "decay_metrics.csv" and src_name.startswith(".") and seen["decay"] >= 2:
            return OSError(errno.EIO, os.strerror(errno.EIO), str(tmp_path / dst_name))
        return None

    _replace_guard(monkeypatch, fail_publish_and_restore)
    with pytest.raises(SessionError, match="recovery is incomplete") as exc:
        csv_export.export_csv(_relabelled(analysed_result), tmp_path)
    message = str(exc.value)
    assert "cannot write" in message
    assert "fully restored" not in message
    assert "完全恢复" not in message
    hidden = [tmp_path / name for name in _hidden(tmp_path)]
    backups = [path for path in hidden if path.name.startswith(".decay_metrics.")]
    assert len(backups) == 1
    assert backups[0].read_bytes() == original_decay
    assert str(backups[0]) in message
    assert (tmp_path / "notes.txt").read_bytes() == before["notes.txt"]
    assert (tmp_path / "energy_metrics.csv").read_bytes() == before["energy_metrics.csv"]
    assert b"CHANGED-LABEL" in (tmp_path / "decay_metrics.csv").read_bytes()
