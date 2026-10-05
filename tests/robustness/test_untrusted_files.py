"""Untrusted session, sidecar and WAV files raise RoomScopeError only."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.errors import InvalidAudioError, RoomScopeError, SessionError
from roomscope.io.jsonutil import MAX_JSON_BYTES, MAX_JSON_DEPTH, read_json_object
from roomscope.io.project_store import load_project
from roomscope.io.session_store import load_comparison, load_measurement, load_session
from roomscope.io.wav import read_sweep_sidecar, read_wav
from roomscope.models.audio import AudioSignal
from roomscope.models.configuration import SweepSettings
from tests.conftest import make_rir


def test_malformed_session_json_is_roomscope_error(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionError):
        load_session(path)


def test_oversized_session_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_bytes(b"{" + b" " * (MAX_JSON_BYTES + 1) + b"}")
    with pytest.raises(SessionError, match="refused"):
        load_session(path)


def test_session_json_array_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(SessionError, match="not a JSON object"):
        load_session(path)


def test_truncated_wav_is_invalid_audio(tmp_path: Path) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    with pytest.raises(InvalidAudioError):
        read_wav(path)


def test_nan_audio_is_invalid() -> None:
    with pytest.raises(InvalidAudioError, match="NaN"):
        AudioSignal(samples=np.array([0.0, np.nan]), sample_rate=48000)


def test_sidecar_must_be_an_object(tmp_path: Path) -> None:
    path = tmp_path / "sweep.roomscope-sweep.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(RoomScopeError):
        read_sweep_sidecar(path)


def test_missing_result_json_is_session_error(tmp_path: Path) -> None:
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"schema_version": 1, "room_name": "X"}), encoding="utf-8")
    with pytest.raises(SessionError):
        load_measurement(tmp_path)


def test_deeply_nested_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    depth = MAX_JSON_DEPTH + 8
    path.write_text("{" * depth + "}" * depth, encoding="utf-8")
    with pytest.raises(SessionError, match="deeper"):
        read_json_object(path, kind="session")


def test_deeply_nested_project_is_session_error(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    depth = MAX_JSON_DEPTH + 2
    path.write_text("{" * depth + "}" * depth, encoding="utf-8")
    with pytest.raises(SessionError, match="deeper"):
        load_project(tmp_path)


def test_infinite_audio_is_invalid() -> None:
    with pytest.raises(InvalidAudioError, match="infinite"):
        AudioSignal(samples=np.array([0.0, np.inf]), sample_rate=48000)


def test_garbage_wav_is_invalid_audio(tmp_path: Path) -> None:
    path = tmp_path / "garbage.wav"
    path.write_bytes(b"this is not a RIFF wave file at all")
    with pytest.raises(InvalidAudioError):
        read_wav(path)


def test_oversized_sidecar_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "sweep.roomscope-sweep.json"
    path.write_bytes(b"{" + b" " * 1_000_001 + b"}")
    with pytest.raises(RoomScopeError):
        read_sweep_sidecar(path)


def test_malformed_project_json_is_session_error(tmp_path: Path) -> None:
    (tmp_path / "project.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionError):
        load_project(tmp_path)


def test_malformed_result_json_is_session_error(tmp_path: Path) -> None:
    (tmp_path / "session.json").write_text(
        json.dumps({"schema_version": 1, "room_name": "X"}), encoding="utf-8"
    )
    (tmp_path / "result.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionError):
        load_measurement(tmp_path)


def test_malformed_comparison_json_is_session_error(tmp_path: Path) -> None:
    path = tmp_path / "comparison.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionError):
        load_comparison(path)


def test_comparison_json_array_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "comparison.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(SessionError, match="not a JSON object"):
        load_comparison(path)


def test_oversized_comparison_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "comparison.json"
    path.write_bytes(b"{" + b" " * (MAX_JSON_BYTES + 1) + b"}")
    with pytest.raises(SessionError, match="refused"):
        load_comparison(path)


def test_deeply_nested_comparison_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "comparison.json"
    depth = MAX_JSON_DEPTH + 4
    path.write_text("{" * depth + "}" * depth, encoding="utf-8")
    with pytest.raises(SessionError, match="deeper"):
        load_comparison(path)


def test_loopback_that_is_a_microphone_does_not_raise(
    short_sweep: SweepSettings,
) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.4, reflections=[(0.018, 0.35)])
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep), loopback=rec)
    assert result.impulse_response.loopback is not None
    assert result.impulse_response.loopback.compensation_applied is False
    assert result.impulse_response.loopback.reason is not None


def test_src_does_not_use_pickle_eval_or_shell() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_src_safety", Path("scripts") / "check_src_safety.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.check(Path("src")) == []


# ------------------------------------------------------------------ #11


@pytest.fixture(scope="module")
def saved_session(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real session folder written by ``save_measurement``."""
    from roomscope.io.session_store import save_measurement
    from roomscope.models.session import MeasurementSession

    sweep = SweepSettings(sample_rate=48000, duration_s=2.0, post_silence_s=1.5)
    result = analyze(
        synthetic_recording(sweep, make_rir(48000, rt60_s=0.3), noise_rms=1e-5),
        Reference.from_settings(sweep),
    )
    folder = tmp_path_factory.mktemp("session")
    save_measurement(folder, MeasurementSession(sweep_settings=sweep), result, copy_recording=False)
    return folder


def _copy_with_members(saved: Path, tmp_path: Path, **members: str) -> Path:
    import shutil

    folder = tmp_path / "received"
    shutil.copytree(saved, folder)
    session_file = folder / "session.json"
    data = json.loads(session_file.read_text(encoding="utf-8"))
    data.update(members)
    session_file.write_text(json.dumps(data), encoding="utf-8")
    return folder


def test_saved_session_members_are_relative_and_load(saved_session: Path) -> None:
    data = json.loads((saved_session / "session.json").read_text(encoding="utf-8"))
    assert data["result_path"] == "result.json"
    assert data["impulse_response_path"] == "impulse_response.wav"
    assert load_measurement(saved_session).result.impulse_response.samples.size > 0


@pytest.mark.parametrize(
    "member", ["result_path", "impulse_response_path"], ids=["result", "impulse_response"]
)
@pytest.mark.parametrize(
    "stored",
    ["../../../../../../etc/passwd", "../outside.json", "sub/../../outside.json"],
    ids=["etc-passwd", "parent", "sub-parent"],
)
def test_session_member_outside_the_folder_is_refused(
    saved_session: Path, tmp_path: Path, member: str, stored: str
) -> None:
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    folder = _copy_with_members(saved_session, tmp_path, **{member: stored})
    with pytest.raises(SessionError, match="outside the session folder"):
        load_measurement(folder)


@pytest.mark.parametrize("member", ["result_path", "impulse_response_path"])
def test_absolute_session_member_is_refused(
    saved_session: Path, tmp_path: Path, member: str
) -> None:
    target = tmp_path / "elsewhere.json"
    target.write_text("{}", encoding="utf-8")
    folder = _copy_with_members(saved_session, tmp_path, **{member: str(target.resolve())})
    with pytest.raises(SessionError, match="absolute path"):
        load_measurement(folder)


def test_symlinked_member_leading_outside_is_refused(saved_session: Path, tmp_path: Path) -> None:
    import os

    folder = _copy_with_members(saved_session, tmp_path, result_path="link.json")
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        os.symlink(outside, folder / "link.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    with pytest.raises(SessionError, match="outside the session folder"):
        load_measurement(folder)


def test_member_in_a_subfolder_still_loads(saved_session: Path, tmp_path: Path) -> None:
    folder = _copy_with_members(saved_session, tmp_path, result_path="data/result.json")
    (folder / "data").mkdir()
    (folder / "result.json").rename(folder / "data" / "result.json")
    assert load_measurement(folder).result.sample_rate == 48000


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"decay": [{"validity": "valid"}]}, "metric delta"),
        ({"decay": ["not an object"]}, "metric delta must be a JSON object"),
        ({"reflections": [{"baseline_delay_ms": 3.0}]}, "reflection match"),
        ({"resonances": [{"baseline_hz": 50.0}]}, "resonance match"),
        ({"frequency_response": {"band_mad_db": [["1 kHz"]]}}, "frequency-response delta"),
        ({"common_band": [20.0]}, "invalid comparison in file"),
    ],
    ids=["delta-missing-name", "delta-not-object", "reflection", "resonance", "fr", "band"],
)
def test_incomplete_comparison_records_are_session_errors(
    tmp_path: Path, payload: dict, match: str
) -> None:
    path = tmp_path / "comparison.json"
    path.write_text(json.dumps({"comparable": True, **payload}), encoding="utf-8")
    with pytest.raises(SessionError, match=match):
        load_comparison(path)


_DELTA = {"name": "broadband.t30", "baseline": 1.0, "candidate": 1.1, "validity": "valid"}


@pytest.mark.parametrize(
    "payload",
    [
        {"frequency_response": {"smoothing_fraction": float("inf")}},
        {"frequency_response": {"band_mad_db": [["1 kHz", 10**400]]}},
        {"frequency_response": {"frequencies_hz": [10**400]}},
        {"common_band": [10**400, 2.0]},
        {"frequency_response": {"frequencies_hz": 5, "difference_db": 5}},
        {"decay": [{**_DELTA, "name": 5}]},
        {"decay": [{**_DELTA, "name": None}]},
        {"noise": [{**_DELTA, "validity": "not_comparable", "reason": 5}]},
        {"resonances": [{"status": 5}]},
        {"reflections": [{"status": None}]},
        {"reflections": [{"status": "matched", "baseline_delay_ms": 3.0}]},
        {"comparable": "false"},
    ],
    ids=[
        "smoothing-inf",
        "band-mad-huge",
        "frequency-huge",
        "common-band-huge",
        "curves-scalar",
        "name-number",
        "name-null",
        "reason-number",
        "status-number",
        "status-null",
        "matched-without-candidate",
        "comparable-text",
    ],
)
def test_wrongly_typed_comparison_values_are_session_errors(tmp_path: Path, payload: dict) -> None:
    """Each of these escaped as OverflowError, or loaded and then crashed
    ``roomscope show`` as "a bug in RoomScope"; "false" read as comparable."""
    path = tmp_path / "comparison.json"
    path.write_text(
        json.dumps({"comparable": True, "common_band": None, **payload}), encoding="utf-8"
    )
    with pytest.raises(SessionError):
        load_comparison(path)


def test_one_sided_reflection_matches_load(tmp_path: Path) -> None:
    path = tmp_path / "comparison.json"
    reflections = [
        {"status": "appeared", "candidate_delay_ms": 3.0, "candidate_relative_db": -6.0},
        {"status": "disappeared", "baseline_delay_ms": 4.0, "baseline_relative_db": -9.0},
    ]
    path.write_text(json.dumps({"comparable": False, "reflections": reflections}), encoding="utf-8")
    loaded = load_comparison(path)
    assert [m.status for m in loaded.reflections] == ["appeared", "disappeared"]
    assert loaded.comparable is False


@pytest.mark.parametrize(
    ("file", "text", "expected"),
    [
        ("session.json", '{"created_at": 5}', "文件中的会话无效：created_at 的类型不正确"),
        ("project.json", '{"positions": "abc"}', "文件中的项目无效：positions 必须是列表"),
        (
            "session.json",
            '{"analysis_settings": {"octave_bands_hz": 5}}',
            "octave_bands_hz 必须是数字列表",
        ),
        ("comparison.json", '{"comparable": true, "settings": [1, 2]}', "文件中的对比无效："),
        (
            "comparison.json",
            '{"comparable": true, "decay": [{"name": "x", "validity": "bogus"}]}',
            "未知的有效性 'bogus'",
        ),
        (
            "comparison.json",
            '{"comparable": true, "frequency_response": {"band_mad_db": [["a"]]}}',
            "文件中的频率响应差值无效：",
        ),
        (
            "comparison.json",
            '{"resonances": [{"status": "matched", "baseline_decay_distinguishable": 1}]}',
            "baseline_decay_distinguishable 必须是 true 或 false",
        ),
    ],
    ids=["session", "project", "bands", "comparison", "validity", "fr-delta", "flag"],
)
def test_load_errors_are_translated(tmp_path: Path, file: str, text: str, expected: str) -> None:
    """RoomScope's own words in a load error were English in a Chinese message."""
    from roomscope.i18n import activate

    (tmp_path / file).write_text(text, encoding="utf-8")
    load = {
        "session.json": lambda: load_session(tmp_path / file),
        "project.json": lambda: load_project(tmp_path),
        "comparison.json": lambda: load_comparison(tmp_path / file),
    }[file]
    activate("zh_CN")
    try:
        with pytest.raises(RoomScopeError) as info:
            load()
    finally:
        activate("en")
    assert expected in str(info.value)


@pytest.mark.parametrize("kind", ["session", "project", "comparison"])
def test_a_record_that_is_not_an_object_is_refused_in_chinese(kind: str) -> None:
    from roomscope.i18n import activate
    from roomscope.models.comparison import ComparisonResult
    from roomscope.models.project import Project
    from roomscope.models.session import MeasurementSession

    cls = {"session": MeasurementSession, "project": Project, "comparison": ComparisonResult}
    activate("zh_CN")
    try:
        with pytest.raises(SessionError, match="必须是 JSON 对象"):
            cls[kind].from_dict([])  # type: ignore[arg-type]
    finally:
        activate("en")


def test_invalid_compare_settings_and_calibration_are_session_errors() -> None:
    from roomscope.models.calibration import CalibrationRecord
    from roomscope.models.comparison import CompareSettings

    with pytest.raises(SessionError, match="compare settings"):
        CompareSettings.from_dict({"min_common_band_octaves": -1.0})
    with pytest.raises(SessionError, match="calibration"):
        CalibrationRecord.from_dict({"reference_dbfs": -20.0})
    with pytest.raises(SessionError, match="calibration must be a JSON object"):
        CalibrationRecord.from_dict([])  # type: ignore[arg-type]
    record = CalibrationRecord.from_dict({"reference_dbfs": -20.0, "reference_db_spl": 94.0})
    assert record.reference_db_spl == 94.0


def _edited(saved: Path, tmp_path: Path, file: str, edit) -> Path:  # type: ignore[no-untyped-def]
    import shutil

    folder = tmp_path / "edited"
    shutil.copytree(saved, folder)
    path = folder / file
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data)
    path.write_text(json.dumps(data), encoding="utf-8")
    return folder


def _set(path: tuple[str, ...], value: object):  # type: ignore[no-untyped-def]
    def edit(data: dict) -> None:
        for key in path[:-1]:
            data = data[key]
        data[path[-1]] = value

    return edit


@pytest.mark.parametrize(
    ("file", "path", "value"),
    [
        ("session.json", ("sweep_settings", "duration_s"), "10"),
        ("session.json", ("sweep_settings", "start_hz"), None),
        ("session.json", ("analysis_settings", "channel"), "0"),
        ("session.json", ("analysis_settings", "octave_bands_hz"), 5),
        ("session.json", ("analysis_settings", "octave_bands_hz"), "125"),
        ("session.json", ("analysis_settings", "octave_bands_hz"), [10**400]),
        ("session.json", ("result_path",), 5),
        ("session.json", ("created_at",), None),
        ("session.json", ("analysis_summary",), []),
        ("result.json", ("decay", "broadband", "t30", "evaluation_range_db"), [-5]),
        ("result.json", ("noise", "band_levels_dbfs"), [[63]]),
        ("result.json", ("reflections", "window_ms"), [0.8]),
        ("result.json", ("decay", "broadband", "rt60_estimate_s"), "slow"),
        ("result.json", ("noise", "rms_dbfs"), [1]),
        ("result.json", ("impulse_response", "sample_rate"), 1e400),
        ("result.json", ("sample_rate",), 10**400),
        ("result.json", ("sample_rate",), 0),
        ("result.json", ("impulse_response", "direct_sound_index"), 10**400),
        ("result.json", ("decay", "broadband", "edc_db"), 5),
        ("result.json", ("frequency_response", "frequencies_hz"), 5),
        ("result.json", ("clipping", "clipped"), "false"),
        ("result.json", ("frequency_response", "gated"), "false"),
    ],
    ids=lambda value: repr(value)[:50],
)
def test_wrong_types_in_a_session_are_roomscope_errors(
    saved_session: Path, tmp_path: Path, file: str, path: tuple[str, ...], value: object
) -> None:
    """Each of these used to escape as TypeError, IndexError or OverflowError,
    or to load and fail later in a listing, a comparison, a report or
    ``show --format json`` (#11); "false" was read as true."""
    folder = _edited(saved_session, tmp_path, file, _set(path, value))
    with pytest.raises(RoomScopeError):
        load_measurement(folder)


def test_a_number_written_as_text_loads_as_a_number(saved_session: Path, tmp_path: Path) -> None:
    folder = _edited(
        saved_session,
        tmp_path,
        "result.json",
        _set(("decay", "broadband", "rt60_estimate_s"), "0.42"),
    )
    assert load_measurement(folder).result.decay.broadband.rt60_estimate_s == 0.42


@pytest.mark.parametrize(
    "text",
    ['{"schema_version": Infinity}', '{"schema_version": -Infinity}', '{"x": ' + "9" * 5000 + "}"],
    ids=["inf", "-inf", "5000-digits"],
)
@pytest.mark.parametrize("loader", ["session", "project", "comparison"])
def test_numbers_json_accepts_but_python_cannot_convert_are_refused(
    tmp_path: Path, text: str, loader: str
) -> None:
    path = tmp_path / f"{loader}.json"
    path.write_text(text, encoding="utf-8")
    load = {"session": load_session, "project": load_project, "comparison": load_comparison}
    with pytest.raises(SessionError):
        load[loader](path)


@pytest.mark.parametrize("value", [5, "abc"], ids=["number", "text"])
@pytest.mark.parametrize("key", ["positions", "session_dirs"])
def test_project_lists_must_be_lists(tmp_path: Path, key: str, value: object) -> None:
    """``"session_dirs": "abc"`` was read as the three folders a, b and c."""
    payload: dict = {"positions": [{"label": "desk", "session_dirs": ["a"]}]}
    if key == "positions":
        payload["positions"] = value
    else:
        payload["positions"][0]["session_dirs"] = value
    (tmp_path / "project.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SessionError, match=f"{key} must be a list"):
        load_project(tmp_path)


def test_symlinked_default_member_leading_outside_is_refused(
    saved_session: Path, tmp_path: Path
) -> None:
    """Without a stored result_path the default result.json was read unchecked."""
    import os

    folder = _copy_with_members(saved_session, tmp_path, result_path=None)
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")
    (folder / "result.json").unlink()
    try:
        os.symlink(outside, folder / "result.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    with pytest.raises(SessionError, match="outside the session folder"):
        load_measurement(folder)


def test_a_newer_sweep_sidecar_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "sweep.roomscope-sweep.json"
    path.write_text(
        json.dumps({"schema_version": 99, "roomscope_sweep": SweepSettings().to_dict()}),
        encoding="utf-8",
    )
    with pytest.raises(RoomScopeError, match="schema version 99"):
        read_sweep_sidecar(path)
    path.write_text(json.dumps({"roomscope_sweep": {"duration_s": "10"}}), encoding="utf-8")
    with pytest.raises(RoomScopeError, match="invalid sweep settings"):
        read_sweep_sidecar(path)
