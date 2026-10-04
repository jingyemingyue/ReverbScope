from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.io.project_store import add_session, is_project, list_project_sessions, save_project
from roomscope.io.session_store import (
    RECORDING_FILE,
    SWEEP_SIDECAR_NAME,
    bundle_session,
    save_measurement,
)
from roomscope.io.wav import write_sweep_file, write_wav
from roomscope.models.configuration import SweepSettings
from roomscope.models.project import Project
from roomscope.models.session import MeasurementSession
from tests.conftest import make_rir


def test_save_copies_sidecar_and_optional_recording(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    sweep, sidecar = write_sweep_file(short_sweep, tmp_path / "src" / "sweep.wav")
    recording = write_wav(
        tmp_path / "src" / "take.wav", rec.samples, rec.sample_rate, subtype="FLOAT"
    )
    out = tmp_path / "session"
    save_measurement(
        out,
        MeasurementSession(room_name="Booth", sweep_path=str(sweep), recording_path=str(recording)),
        result,
        include_curves=False,
        copy_recording=True,
    )
    assert (out / SWEEP_SIDECAR_NAME).is_file()
    assert (out / RECORDING_FILE).is_file()
    assert sidecar.read_text(encoding="utf-8") == (out / SWEEP_SIDECAR_NAME).read_text(
        encoding="utf-8"
    )
    skipped = tmp_path / "session-no-audio-copy"
    save_measurement(
        skipped,
        MeasurementSession(room_name="Booth", sweep_path=str(sweep), recording_path=str(recording)),
        result,
        include_curves=False,
        copy_recording=False,
    )
    assert (skipped / SWEEP_SIDECAR_NAME).is_file()
    assert not (skipped / RECORDING_FILE).is_file()


def test_bundle_excludes_wav_when_requested(tmp_path: Path, short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    out = tmp_path / "session"
    save_measurement(out, MeasurementSession(room_name="Booth"), result, include_curves=False)
    zipped = bundle_session(out, tmp_path / "full.zip", include_audio=True)
    quiet = bundle_session(out, tmp_path / "quiet.zip", include_audio=False)
    with zipfile.ZipFile(zipped) as archive:
        names = archive.namelist()
        assert "session.json" in names
        assert any(name.endswith(".wav") for name in names)
    with zipfile.ZipFile(quiet) as archive:
        names = archive.namelist()
        assert "session.json" in names
        assert not any(name.endswith(".wav") for name in names)


def test_bundle_leaves_out_links_that_leave_the_session(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    """A session from someone else may contain a link to one of your files;
    a bug-report bundle must not carry that file into a public issue."""
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    out = tmp_path / "session"
    save_measurement(out, MeasurementSession(room_name="Booth"), result, include_curves=False)
    private = tmp_path / "private" / "id_ed25519"
    private.parent.mkdir()
    private.write_text("secret", encoding="utf-8")
    (out / "notes").mkdir()
    (out / "notes" / "inside.txt").write_text("kept", encoding="utf-8")
    try:
        (out / "key.txt").symlink_to(private)
        (out / "linked-dir").symlink_to(private.parent, target_is_directory=True)
        (out / "notes-link.txt").symlink_to(out / "notes" / "inside.txt")
    except OSError as exc:  # Windows without the symlink privilege
        pytest.skip(f"this system cannot create symbolic links: {exc}")
    with zipfile.ZipFile(bundle_session(out, tmp_path / "report.zip")) as archive:
        names = archive.namelist()
        contents = b"".join(archive.read(name) for name in names)
    assert "key.txt" not in names and not any(n.startswith("linked-dir") for n in names)
    assert b"secret" not in contents
    # Links that stay inside the session folder are ordinary content.
    assert "notes/inside.txt" in names and "notes-link.txt" in names


def test_project_index_and_positions(tmp_path: Path, short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    project_dir = tmp_path / "room"
    save_project(project_dir, Project(name="Booth"))
    assert is_project(project_dir)
    first = project_dir / "sessions" / "pos-a"
    save_measurement(first, MeasurementSession(room_name="Booth"), result, include_curves=False)
    add_session(project_dir, first, position="desk")
    items = list_project_sessions(project_dir)
    assert items[0][0] == "desk"
    assert items[0][1].resolve() == first.resolve()


def test_one_session_is_listed_once_however_it_was_added(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    """``dir`` and ``dir/session.json`` were stored as two entries, and the
    session was counted twice by ``project average``; a stale
    ``.../session.json`` entry was still listed."""
    import json

    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    result = analyze(
        synthetic_recording(short_sweep, ir, noise_rms=1e-5), Reference.from_settings(short_sweep)
    )
    project = tmp_path / "room"
    save_project(project, Project(name="room"))
    session = project / "sessions" / "a"
    save_measurement(session, MeasurementSession(), result, include_curves=False)
    add_session(project, session, position="desk")
    add_session(project, session / "session.json", position="desk")
    stored = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert stored["positions"] == [{"label": "desk", "session_dirs": ["sessions/a"]}]
    assert list_project_sessions(project) == [("desk", session)]

    stored["positions"][0]["session_dirs"] += ["sessions/a/session.json", "gone/session.json"]
    (project / "project.json").write_text(json.dumps(stored), encoding="utf-8")
    assert list_project_sessions(project) == [("desk", session)]


def test_bundle_out_without_zip_suffix_is_a_folder(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    """``--out bundles/`` (a folder that does not exist yet) wrote a zip
    file called ``bundles`` with no extension."""
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    booth = tmp_path / "booth"
    save_measurement(booth, MeasurementSession(), result, include_curves=False)
    written = bundle_session(booth, tmp_path / "bundles", include_audio=False)
    assert written == tmp_path / "bundles" / "booth.zip"
    assert zipfile.is_zipfile(written)
    assert bundle_session(booth, tmp_path / "named.ZIP") == tmp_path / "named.ZIP"


def test_project_add_refuses_a_folder_without_a_session(tmp_path: Path) -> None:
    """A typo was stored, reported as success, and silently skipped later:
    ``project average`` then failed with 'no sessions in ...'."""
    from roomscope.errors import SessionError

    room = tmp_path / "room"
    save_project(room, Project(name="room"))
    with pytest.raises(SessionError, match="session file not found"):
        add_session(room, tmp_path / "sesion1", position="desk")
    assert list_project_sessions(room) == []


def test_a_session_cannot_be_listed_under_a_second_position(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    """The second label was stored and reported, but the listing kept only
    the first one, so the correction had no effect."""
    import json

    from roomscope.errors import SessionError

    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    result = analyze(
        synthetic_recording(short_sweep, ir, noise_rms=1e-5), Reference.from_settings(short_sweep)
    )
    project = tmp_path / "room"
    save_project(project, Project(name="room"))
    session = project / "sessions" / "a"
    save_measurement(session, MeasurementSession(), result, include_curves=False)
    add_session(project, session, position="sofa")
    with pytest.raises(SessionError, match="sofa"):
        add_session(project, session / "session.json", position="desk")
    add_session(project, session, position="sofa")
    stored = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert stored["positions"] == [{"label": "sofa", "session_dirs": ["sessions/a"]}]
    assert [label for label, _folder in list_project_sessions(project)] == ["sofa"]
