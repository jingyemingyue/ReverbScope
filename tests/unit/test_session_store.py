from __future__ import annotations

import json
import stat
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

from reverbscope.core.compare import compare
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.errors import SessionError
from reverbscope.io.session_store import (
    COMPARISON_FILE,
    IR_FILE,
    RESULT_FILE,
    SESSION_FILE,
    list_sessions,
    load_comparison,
    load_measurement,
    load_session,
    save_comparison,
    save_measurement,
)
from reverbscope.io.wav import read_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir


def test_save_and_load_measurement(tmp_path: Path, short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    session = MeasurementSession(
        room_name="Booth", sweep_settings=short_sweep, recording_path=str(tmp_path / "rec.wav")
    )
    out = tmp_path / "session"
    session_path = save_measurement(out, session, result, include_curves=False)
    assert session_path == out / SESSION_FILE
    assert (out / RESULT_FILE).is_file() and (out / IR_FILE).is_file()

    loaded = load_session(out)
    assert loaded.room_name == "Booth"
    assert loaded.impulse_response_path == IR_FILE
    assert loaded.result_path == RESULT_FILE
    assert loaded.recording_path == str(tmp_path / "rec.wav")
    assert loaded.analysis_summary["broadband_rt60_estimate_s"] is not None
    assert loaded.analysis_summary["bands"]["1 kHz"]["t30_s"] is not None

    stored_ir = read_wav(out / IR_FILE)
    assert np.allclose(stored_ir.samples, result.impulse_response.samples, atol=1e-6)
    payload = json.loads((out / RESULT_FILE).read_text())
    assert payload["schema_version"] == 1
    assert "edc_db" not in payload["decay"]["broadband"]

    measurement = load_measurement(out)
    assert measurement.session.room_name == "Booth"
    assert np.allclose(
        measurement.result.impulse_response.samples,
        result.impulse_response.samples,
        atol=1e-6,
    )
    assert measurement.result.decay.broadband.rt60_estimate_s == (
        result.decay.broadband.rt60_estimate_s
    )
    from_file = load_measurement(out / SESSION_FILE)
    assert from_file.directory == measurement.directory


def test_load_measurement_requires_ir_when_result_has_no_samples(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    out = tmp_path / "session"
    save_measurement(out, MeasurementSession(room_name="Booth"), result, include_curves=False)
    (out / IR_FILE).unlink()
    with pytest.raises(SessionError, match=r"impulse_response\.wav"):
        load_measurement(out)


def test_load_measurement_requires_result_json(tmp_path: Path, short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    out = tmp_path / "session"
    save_measurement(out, MeasurementSession(room_name="Booth"), result, include_curves=False)
    (out / RESULT_FILE).unlink()
    with pytest.raises(SessionError, match=r"result\.json"):
        load_measurement(out)


def test_list_sessions_skips_broken_and_orders_newest(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    first = tmp_path / "older"
    second = tmp_path / "nested" / "newer"
    save_measurement(
        first,
        MeasurementSession(room_name="Older", created_at="2020-01-01T00:00:00+00:00"),
        result,
        include_curves=False,
    )
    save_measurement(
        second,
        MeasurementSession(room_name="Newer", created_at="2024-01-01T00:00:00+00:00"),
        result,
        include_curves=False,
    )
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / SESSION_FILE).write_text("not json", encoding="utf-8")
    hidden = tmp_path / ".hidden" / "secret"
    save_measurement(hidden, MeasurementSession(room_name="Hidden"), result, include_curves=False)

    listings = list_sessions(tmp_path)
    names = [item.session.room_name for item in listings]
    assert names == ["Newer", "Older"]
    assert "Newer" in listings[0].label
    assert "RT60" in listings[0].label


def test_save_and_load_comparison_does_not_store_findings(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    comparison = compare(result, result)
    written = save_comparison(tmp_path / "out", comparison)
    assert written == tmp_path / "out" / COMPARISON_FILE
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert "findings" not in payload
    loaded = load_comparison(tmp_path / "out")
    assert loaded.comparable is comparison.comparable
    assert loaded.schema_version == comparison.schema_version
    again = load_comparison(written)
    assert again.common_band == comparison.common_band


@pytest.fixture
def analysed(short_sweep: SweepSettings):  # type: ignore[no-untyped-def]
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    return rec, analyze(rec, Reference.from_settings(short_sweep))


def test_saving_one_session_twice_keeps_the_recording(
    tmp_path: Path, short_sweep: SweepSettings, analysed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The GUI saves state.session again (a second folder, or an opened
    session elsewhere). save_measurement rewrote the caller's paths relative
    to the first folder, so the second save looked for recording.wav in the
    working directory and stored a path that does not exist."""
    from reverbscope.io.wav import write_wav

    recording, result = analysed
    take = write_wav(tmp_path / "in" / "take.wav", recording.samples, 48000, subtype="FLOAT")
    monkeypatch.chdir(tmp_path)  # neither session folder
    session = MeasurementSession(sweep_settings=short_sweep, recording_path=str(take))
    save_measurement(tmp_path / "A", session, result, copy_recording=True)
    save_measurement(tmp_path / "B", session, result, copy_recording=True)
    assert session.recording_path == str(take)
    loaded = load_measurement(tmp_path / "A")
    save_measurement(tmp_path / "C", loaded.session, loaded.result, copy_recording=True)
    for name in ("A", "B", "C"):
        stored = json.loads((tmp_path / name / SESSION_FILE).read_text(encoding="utf-8"))
        assert stored["recording_path"] == "recording.wav", name
        assert (tmp_path / name / "recording.wav").read_bytes() == take.read_bytes(), name


def test_list_sessions_skips_refused_and_mistyped_sessions(tmp_path: Path, analysed) -> None:
    _recording, result = analysed
    good = tmp_path / "good"
    save_measurement(good, MeasurementSession(room_name="Good"), result, include_curves=False)
    for name, change in (
        ("rate", {"sweep_settings": {"sample_rate": 12345}}),  # ConfigurationError
        ("created", {"created_at": None}),  # would break the sort
        ("summary", {"analysis_summary": []}),  # would break the label
    ):
        folder = tmp_path / name
        save_measurement(folder, MeasurementSession(), result, include_curves=False)
        data = json.loads((folder / SESSION_FILE).read_text(encoding="utf-8"))
        data.update(change)
        (folder / SESSION_FILE).write_text(json.dumps(data), encoding="utf-8")
    listings = list_sessions(tmp_path)
    assert [item.session.room_name for item in listings] == ["Good"]
    assert listings[0].label


def test_bundle_the_folder_you_are_in(
    tmp_path: Path, analysed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``reverbscope session bundle .`` failed: Path('.') has no name."""
    from reverbscope.io.session_store import bundle_session

    _recording, result = analysed
    folder = tmp_path / "booth"
    save_measurement(folder, MeasurementSession(), result, include_curves=False)
    monkeypatch.chdir(folder)
    assert bundle_session(".") == tmp_path / "booth.zip"
    (tmp_path / "out").mkdir()
    assert bundle_session(SESSION_FILE, tmp_path / "out") == tmp_path / "out" / "booth.zip"


@pytest.mark.parametrize("failure", ["json", "recording"])
def test_a_failed_save_keeps_the_previous_take_whole(
    tmp_path: Path,
    short_sweep: SweepSettings,
    analysed,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    """A full disk half-way through a save into an existing session folder
    left impulse_response.wav (and recording.wav) of the new take beside the
    JSON of the old one, or a cut-off WAV that no longer opened."""
    import os
    import shutil

    from reverbscope.io import session_store
    from reverbscope.io.session_store import RECORDING_FILE
    from reverbscope.io.wav import write_wav

    first_rec, first = analysed
    second_rec = synthetic_recording(
        short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.8), noise_rms=1e-5
    )
    second = analyze(second_rec, Reference.from_settings(short_sweep))
    rate = short_sweep.sample_rate
    takes = tmp_path / "takes"
    one = write_wav(takes / "one.wav", first_rec.samples, rate, subtype="FLOAT")
    two = write_wav(takes / "two.wav", second_rec.samples, rate, subtype="FLOAT")
    folder = tmp_path / "s"
    save_measurement(
        folder,
        MeasurementSession(room_name="First", recording_path=str(one)),
        first,
        include_curves=False,
        copy_recording=True,
    )
    members = (SESSION_FILE, RESULT_FILE, IR_FILE, RECORDING_FILE)
    before = {name: (folder / name).read_bytes() for name in members}

    def disk_full(*_args: object, **_kwargs: object) -> None:
        raise OSError(28, "No space left on device")

    def cut_off_copy(src: str, dst: str, **_kwargs: object) -> None:
        Path(dst).write_bytes(Path(src).read_bytes()[:1000])
        disk_full()

    if failure == "json":
        monkeypatch.setattr(os, "fsync", disk_full)
    else:
        monkeypatch.setattr(session_store.shutil, "copy2", cut_off_copy)
    with pytest.raises(SessionError, match="No space left"):
        save_measurement(
            folder,
            MeasurementSession(room_name="Second", recording_path=str(two)),
            second,
            include_curves=False,
            copy_recording=True,
        )
    monkeypatch.setattr(os, "fsync", os.fsync)
    monkeypatch.setattr(session_store.shutil, "copy2", shutil.copy2)
    assert {name: (folder / name).read_bytes() for name in members} == before
    assert load_measurement(folder).session.room_name == "First"
    assert not [path.name for path in folder.iterdir() if path.name.startswith(".")]


@pytest.mark.skipif(sys.platform == "win32", reason="symbolic links need a privilege")
def test_saving_into_a_received_folder_does_not_follow_planted_links(
    tmp_path: Path, analysed
) -> None:
    """Every member was staged under a fixed name (``.session.saving.json``)
    and opened without O_EXCL: a link under that name in a session folder
    from someone else made the save overwrite the file it pointed at."""
    _recording, result = analysed
    folder = tmp_path / "received"
    save_measurement(folder, MeasurementSession(room_name="Theirs"), result, include_curves=False)
    victims = []
    for planted in (".session.saving.json", ".result.saving.json", ".impulse_response.saving.wav"):
        victim = tmp_path / f"victim-{planted.strip('.')}"
        victim.write_bytes(b"keep me")
        (folder / planted).symlink_to(victim)
        victims.append(victim)
    save_measurement(folder, MeasurementSession(room_name="Mine"), result, include_curves=False)
    assert [victim.read_bytes() for victim in victims] == [b"keep me"] * len(victims)
    for name in (SESSION_FILE, RESULT_FILE, IR_FILE):
        assert not (folder / name).is_symlink(), name
    assert load_measurement(folder).session.room_name == "Mine"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_saving_again_keeps_the_permissions_of_the_session_files(tmp_path: Path, analysed) -> None:
    _recording, result = analysed
    folder = tmp_path / "private"
    save_measurement(folder, MeasurementSession(), result, include_curves=False)
    (folder / SESSION_FILE).chmod(0o600)
    save_measurement(folder, MeasurementSession(room_name="Again"), result, include_curves=False)
    assert stat.S_IMODE((folder / SESSION_FILE).stat().st_mode) == 0o600


def _received_session(tmp_path: Path, result: AnalysisResult, change: dict[str, str]) -> Path:
    """A session folder as it arrives from someone else, two levels below tmp_path."""
    received = tmp_path / "inbox" / "received"
    save_measurement(received, MeasurementSession(), result, copy_recording=False)
    data = json.loads((received / SESSION_FILE).read_text(encoding="utf-8"))
    data.update(change)
    (received / SESSION_FILE).write_text(json.dumps(data), encoding="utf-8")
    return received


@pytest.mark.parametrize("variant", ["relative sweep", "relative recording", "linked sidecar"])
def test_an_opened_session_cannot_copy_outside_files_into_a_new_session(
    tmp_path: Path, analysed, variant: str
) -> None:
    """A received session named ``../../config.json`` or an absolute path as
    its sweep or recording. Saving it again (the GUI's Save button after
    Open) copied that file into the new folder as the sweep sidecar or
    recording.wav, and ``session bundle`` then put it into the zip."""
    from reverbscope.io.session_store import bundle_session

    _recording, result = analysed
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"token": "s3cret"}), encoding="utf-8")
    key = tmp_path / "id_key"
    key.write_bytes(b"PRIVATE KEY")
    if variant == "relative sweep":
        change = {"sweep_path": "../../config.json", "recording_path": str(key)}
    elif variant == "relative recording":
        change = {"sweep_path": str(config), "recording_path": "../../id_key"}
    else:
        change = {"sweep_path": "sweep.wav", "recording_path": str(key)}
    received = _received_session(tmp_path, result, change)
    if variant == "linked sidecar":
        try:
            (received / "sweep.reverbscope-sweep.json").symlink_to(config)
        except OSError as exc:  # Windows without the symlink privilege
            pytest.skip(f"this system cannot create symbolic links: {exc}")

    loaded = load_measurement(received)
    resaved = tmp_path / "resaved"
    save_measurement(resaved, loaded.session, loaded.result, copy_recording=True)
    for path in resaved.iterdir():
        content = path.read_bytes()
        assert b"s3cret" not in content and b"PRIVATE KEY" not in content, path.name
    stored = json.loads((resaved / SESSION_FILE).read_text(encoding="utf-8"))
    assert str(tmp_path) not in json.dumps(
        {key: stored[key] for key in ("sweep_path", "recording_path")}
    )
    with zipfile.ZipFile(bundle_session(resaved, tmp_path / "out.zip")) as archive:
        for name in archive.namelist():
            content = archive.read(name)
            assert b"s3cret" not in content and b"PRIVATE KEY" not in content, name


@pytest.mark.parametrize("field", ["sweep_path", "recording_path", "result_path"])
def test_a_nul_byte_in_a_stored_path_is_a_reverbscope_error(
    tmp_path: Path, analysed, field: str
) -> None:
    """Resolving a path with a NUL byte raises ValueError, which escaped the
    loader as a bug in ReverbScope."""
    _recording, result = analysed
    received = _received_session(tmp_path, result, {field: "a\u0000b.json"})
    if field == "result_path":
        with pytest.raises(SessionError):
            load_measurement(received)
    else:
        assert getattr(load_measurement(received).session, field) is None


def test_an_opened_session_still_copies_its_own_recording(tmp_path: Path, analysed) -> None:
    from reverbscope.io.session_store import RECORDING_FILE
    from reverbscope.io.wav import write_wav

    recording, result = analysed
    take = write_wav(tmp_path / "take.wav", recording.samples, 48000, subtype="FLOAT")
    received = tmp_path / "received"
    save_measurement(
        received, MeasurementSession(recording_path=str(take)), result, copy_recording=True
    )
    take.unlink()
    loaded = load_measurement(received)
    assert loaded.session.recording_path == str((received / RECORDING_FILE).resolve())
    save_measurement(tmp_path / "again", loaded.session, loaded.result, copy_recording=True)
    assert (tmp_path / "again" / RECORDING_FILE).read_bytes() == (
        received / RECORDING_FILE
    ).read_bytes()


def test_resaving_an_opened_session_keeps_its_sweep_sidecar(
    tmp_path: Path, short_sweep: SweepSettings, analysed
) -> None:
    """Only the sidecar next to the working sweep WAV was copied: once that
    WAV was moved or deleted (or the session came from someone else), saving
    the opened session elsewhere dropped the folder's own sidecar."""
    import shutil

    from reverbscope.io.session_store import SWEEP_SIDECAR_NAME
    from reverbscope.io.wav import write_sweep_file

    _recording, result = analysed
    sweep, _sidecar = write_sweep_file(short_sweep, tmp_path / "work" / "sweep.wav")
    save_measurement(
        tmp_path / "A", MeasurementSession(sweep_path=str(sweep)), result, copy_recording=False
    )
    assert (tmp_path / "A" / SWEEP_SIDECAR_NAME).is_file()
    shutil.rmtree(tmp_path / "work")
    loaded = load_measurement(tmp_path / "A")
    save_measurement(tmp_path / "B", loaded.session, loaded.result, copy_recording=False)
    assert (tmp_path / "B" / SWEEP_SIDECAR_NAME).read_bytes() == (
        tmp_path / "A" / SWEEP_SIDECAR_NAME
    ).read_bytes()


def test_bundle_of_a_session_at_a_volume_root_fails_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A session saved at E:\\ has no folder name: ``with_name('.zip')``
    raised ValueError, reported as a bug in ReverbScope."""
    import os

    from reverbscope.io import session_store

    root = Path(os.path.abspath(os.sep))
    monkeypatch.setattr(session_store, "_session_file", lambda _path: root / SESSION_FILE)
    with pytest.raises(SessionError, match="outside the session folder"):
        session_store.bundle_session(root)


def test_a_listing_with_a_huge_rt60_in_its_summary_still_has_a_label(
    tmp_path: Path, analysed
) -> None:
    """``{seconds:.2f}`` of a 401-digit integer raised OverflowError in
    ``show --list`` and in the GUI's session browser."""
    _recording, result = analysed
    folder = tmp_path / "s"
    save_measurement(folder, MeasurementSession(room_name="Big"), result, include_curves=False)
    data = json.loads((folder / SESSION_FILE).read_text(encoding="utf-8"))
    data["analysis_summary"]["broadband_rt60_estimate_s"] = 10**400
    (folder / SESSION_FILE).write_text(json.dumps(data), encoding="utf-8")
    (listing,) = list_sessions(tmp_path)
    assert "RT60" in listing.label and "Big" in listing.label


def test_a_192k_six_second_result_reopens(tmp_path: Path, analysed) -> None:
    """At 192 kHz an impulse response longer than about 5.5 s stores 2**20
    frequency-response bins: result.json is about 40 MB, over the 32 MiB cap,
    so ReverbScope refused to reopen a session it had just saved."""
    from dataclasses import replace

    from reverbscope.io.jsonutil import MAX_JSON_BYTES

    _recording, result = analysed
    bins = 2**20
    freqs = np.arange(1, bins + 1) * 192000 / 2**21
    level = np.linspace(-90.0, 0.0, bins)
    big = replace(
        result,
        frequency_response=replace(
            result.frequency_response,
            frequencies_hz=freqs,
            magnitude_db_raw=level,
            magnitude_db_smoothed=level + 0.123456789,
        ),
    )
    folder = tmp_path / "s192"
    save_measurement(folder, MeasurementSession(), big)
    assert (folder / RESULT_FILE).stat().st_size > MAX_JSON_BYTES
    reopened = load_measurement(folder)
    assert reopened.result.frequency_response.frequencies_hz.shape == (bins,)


@pytest.mark.parametrize(
    ("name", "subtype", "stored"),
    [
        ("take.aiff", "PCM_24", "PCM_24"),
        ("take.flac", "PCM_24", "PCM_24"),
        ("take.caf", "FLOAT", "FLOAT"),
        ("take.flac", "PCM_S8", "FLOAT"),  # WAV has no signed 8-bit samples
    ],
)
def test_a_copied_aiff_caf_or_flac_take_is_a_real_wav(
    tmp_path: Path, analysed, name: str, subtype: str, stored: str
) -> None:
    """The copy was the source's bytes under the name recording.wav: an AIFF
    ('FORM'), FLAC ('fLaC') or CAF ('caff') file that programs going by the
    name call a corrupt WAV."""
    import soundfile as sf

    recording, result = analysed
    samples = recording.samples / np.max(np.abs(recording.samples)) * 0.5
    source = tmp_path / name
    sf.write(str(source), samples, recording.sample_rate, subtype=subtype)
    folder = tmp_path / "session"
    save_measurement(
        folder,
        MeasurementSession(recording_path=str(source)),
        result,
        include_curves=False,
        copy_recording=True,
    )
    copied = folder / "recording.wav"
    assert copied.read_bytes()[:4] == b"RIFF"
    info = sf.info(str(copied))
    assert (info.format, info.subtype) == ("WAV", stored)
    np.testing.assert_array_equal(read_wav(copied).samples, read_wav(source).samples)
    assert load_session(folder).recording_path == "recording.wav"


def test_a_file_dated_before_1980_is_bundled(tmp_path: Path, analysed) -> None:
    """zipfile refuses dates before 1980 (a recorder whose clock was never
    set): the bundle failed as "unexpected ValueError … a bug in ReverbScope"."""
    import os

    from reverbscope.io.session_store import bundle_session

    _recording, result = analysed
    folder = tmp_path / "old-clock"
    save_measurement(folder, MeasurementSession(), result, include_curves=False)
    os.utime(folder / IR_FILE, (0, 0))
    target = bundle_session(folder, tmp_path / "out")
    with zipfile.ZipFile(target) as archive:
        assert archive.getinfo(IR_FILE).date_time[0] == 1980
        assert archive.read(IR_FILE) == (folder / IR_FILE).read_bytes()


def test_a_failed_bundle_keeps_the_earlier_one(
    tmp_path: Path, analysed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The zip was opened on its final name: a failure half-way left a cut-off
    (or empty, 22-byte) zip in place of a good bundle from an earlier run."""
    from reverbscope.io.session_store import bundle_session

    _recording, result = analysed
    folder = tmp_path / "booth"
    save_measurement(folder, MeasurementSession(), result, include_curves=False)
    target = bundle_session(folder, tmp_path / "out")
    good = target.read_bytes()
    written: list[str] = []
    real_write = zipfile.ZipFile.write

    def disk_full(self: zipfile.ZipFile, filename: object, arcname: str | None = None) -> None:
        if written:
            raise OSError(28, "No space left on device")
        written.append(str(arcname))
        real_write(self, filename, arcname)  # type: ignore[arg-type]

    monkeypatch.setattr(zipfile.ZipFile, "write", disk_full)
    with pytest.raises(SessionError, match="No space left"):
        bundle_session(folder, tmp_path / "out")
    assert target.read_bytes() == good
    assert sorted(path.name for path in target.parent.iterdir()) == [target.name]


@pytest.mark.parametrize("locked", ["renamed or replaced", "replaced"])
def test_a_failed_rename_puts_back_the_members_already_replaced(
    tmp_path: Path,
    short_sweep: SweepSettings,
    analysed,
    monkeypatch: pytest.MonkeyPatch,
    locked: str,
) -> None:
    """Windows refuses to replace a file another program holds open (a DAW
    with impulse_response.wav loaded). recording.wav had already been
    replaced: the folder held take B's recording beside take A's analysis."""
    import os

    from reverbscope.io.session_store import RECORDING_FILE
    from reverbscope.models.audio import AudioSignal

    _recording, result = analysed
    folder = tmp_path / "s"
    take_a = AudioSignal(np.full(4800, 0.1), short_sweep.sample_rate)
    take_b = AudioSignal(np.full(4800, -0.2), short_sweep.sample_rate)
    save_measurement(folder, MeasurementSession(room_name="A"), result, recording=take_a)
    members = (RECORDING_FILE, IR_FILE, RESULT_FILE, SESSION_FILE, "sweep.reverbscope-sweep.json")
    before = {name: (folder / name).read_bytes() for name in members if (folder / name).exists()}
    real_replace = os.replace
    held = str(folder / IR_FILE)

    def windows_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        if str(dst) == held or (locked != "replaced" and str(src) == held):
            raise PermissionError(13, "The process cannot access the file", str(dst))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", windows_replace)
    with pytest.raises(SessionError, match="cannot write"):
        save_measurement(folder, MeasurementSession(room_name="B"), result, recording=take_b)
    monkeypatch.setattr(os, "replace", real_replace)
    assert {name: (folder / name).read_bytes() for name in before} == before
    assert load_measurement(folder).session.room_name == "A"
    assert not [path.name for path in folder.iterdir() if path.name.startswith(".")]


def _windows_read_only_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    """What Windows does with a read-only file: it can be neither the target
    of a rename nor deleted (WinError 5)."""
    import os

    def read_only(path: object) -> bool:
        return os.path.exists(path) and not os.stat(path).st_mode & stat.S_IWUSR  # type: ignore[arg-type]

    real_replace, real_unlink = os.replace, Path.unlink

    def replace(src: str, dst: str) -> None:
        if read_only(dst):
            raise PermissionError(13, "Access is denied", str(dst))
        real_replace(src, dst)

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if read_only(self):
            raise PermissionError(13, "Access is denied", str(self))
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(Path, "unlink", unlink)


@pytest.mark.skipif(sys.platform == "win32", reason="emulates Windows on POSIX permissions")
def test_saving_over_a_write_protected_session_fails_cleanly(
    tmp_path: Path, analysed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A temporary took the read-only mode of the file it was to replace; the
    cleanup could not delete it on Windows and raised a bare PermissionError
    (the desktop app's "bug in ReverbScope" box) that hid the "cannot write"
    error, and left hidden temporaries that a bundle then zipped."""
    _recording, result = analysed
    folder = tmp_path / "protected"
    save_measurement(folder, MeasurementSession(room_name="Kept"), result, include_curves=False)
    before = {path.name: path.read_bytes() for path in folder.iterdir()}
    for path in folder.iterdir():
        path.chmod(0o444)
    _windows_read_only_rules(monkeypatch)
    loaded = load_measurement(folder)
    with pytest.raises(SessionError, match=r"cannot write .*Access is denied"):
        save_measurement(folder, loaded.session, loaded.result, include_curves=False)
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == before


def _take_with_copies(tmp_path: Path, short_sweep: SweepSettings, analysed) -> Path:  # type: ignore[no-untyped-def]
    """A session folder holding a copied recording.wav and sweep sidecar."""
    from reverbscope.io.wav import write_sweep_file, write_wav

    recording, result = analysed
    sweep, _sidecar = write_sweep_file(short_sweep, tmp_path / "in" / "sweep.wav")
    take = write_wav(tmp_path / "in" / "take.wav", recording.samples, 48000, subtype="FLOAT")
    folder = tmp_path / "s"
    save_measurement(
        folder,
        MeasurementSession(room_name="A", sweep_path=str(sweep), recording_path=str(take)),
        result,
        include_curves=False,
        copy_recording=True,
    )
    assert (folder / "recording.wav").is_file() and (
        folder / "sweep.reverbscope-sweep.json"
    ).is_file()
    return folder


def test_a_new_take_does_not_keep_the_previous_takes_recording_or_sidecar(
    tmp_path: Path, short_sweep: SweepSettings, analysed
) -> None:
    """An impulse-response take saved over a sweep take (no sidecar, recording
    not copied) left the old recording.wav and sweep sidecar in the folder:
    the reopened session claimed the old sweep, and a bundle shipped the old
    recording as this session's."""
    _recording, result = analysed
    folder = _take_with_copies(tmp_path, short_sweep, analysed)
    save_measurement(
        folder,
        MeasurementSession(room_name="B", recording_path=str(tmp_path / "in" / "ir.wav")),
        result,
        include_curves=False,
        copy_recording=False,
    )
    assert sorted(path.name for path in folder.iterdir()) == [IR_FILE, RESULT_FILE, SESSION_FILE]
    assert load_measurement(folder).session.sweep_path is None


def test_resaving_without_copying_keeps_the_folders_own_recording(
    tmp_path: Path, short_sweep: SweepSettings, analysed
) -> None:
    folder = _take_with_copies(tmp_path, short_sweep, analysed)
    before = (folder / "recording.wav").read_bytes()
    loaded = load_measurement(folder)
    save_measurement(folder, loaded.session, loaded.result, copy_recording=False)
    assert (folder / "recording.wav").read_bytes() == before
    assert (folder / "sweep.reverbscope-sweep.json").is_file()
    assert load_session(folder).recording_path == "recording.wav"


def test_a_failed_removal_puts_the_previous_take_back(
    tmp_path: Path, short_sweep: SweepSettings, analysed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing the old recording is part of the save: when Windows refuses it
    (a player has it open), the members already replaced are put back."""
    _recording, result = analysed
    folder = _take_with_copies(tmp_path, short_sweep, analysed)
    before = {path.name: path.read_bytes() for path in folder.iterdir()}
    real_unlink = Path.unlink

    def held_open(self: Path, missing_ok: bool = False) -> None:
        if self == folder / "recording.wav":
            raise PermissionError(13, "The process cannot access the file", str(self))
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", held_open)
    with pytest.raises(SessionError, match=r"recording\.wav"):
        save_measurement(folder, MeasurementSession(room_name="B"), result, copy_recording=False)
    monkeypatch.setattr(Path, "unlink", real_unlink)
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == before
