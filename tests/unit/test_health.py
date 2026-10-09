"""Measurement health: the checks, their statuses and what they tell the user to do."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import resample_poly

from reverbscope.core.pipeline import (
    Reference,
    analyze,
    analyze_impulse_response,
    synthetic_recording,
)
from reverbscope.errors import InvalidAudioError, ReverbScopeError
from reverbscope.health import (
    DROPOUTS_INVALID_MS,
    HealthStatus,
    assess,
    failure_guidance,
    metric_group_text,
    status_word,
)
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import KIND_SAMPLE_RATE, AnalysisResult, PlaybackSpeed
from tests.conftest import make_rir


def _room(short_sweep: SweepSettings):  # type: ignore[no-untyped-def]
    return make_rir(short_sweep.sample_rate, rt60_s=0.4, reflections=[(0.012, 0.4)])


def _clean(short_sweep: SweepSettings) -> AudioSignal:
    return synthetic_recording(short_sweep, _room(short_sweep), noise_rms=1e-5)


def _analysed(short_sweep: SweepSettings, recording: AudioSignal) -> AnalysisResult:
    return analyze(recording, Reference.from_settings(short_sweep))


def _by_id(result: AnalysisResult) -> dict[str, object]:
    return {check.id: check for check in assess(result).checks}


def test_a_clean_take_is_good_on_every_check(short_sweep: SweepSettings) -> None:
    report = assess(_analysed(short_sweep, _clean(short_sweep)))
    assert report.overall is HealthStatus.GOOD
    assert [check.id for check in report.checks] == [
        "reference",
        "sweep",
        "playback_speed",
        "direct_sound",
        "level",
        "distortion",
        "dropouts",
        "decay_range",
        "noise",
        "length",
    ]
    assert report.problems == ()
    assert report.unavailable == () and report.affected == ()
    for check in report.checks:
        assert check.title and check.reason
    payload = report.to_dict()
    assert payload["overall"] == "good" and payload["locale"] == "en"
    assert json.dumps(payload)  # JSON-ready, no NumPy numbers


def test_a_clipped_take_is_invalid_and_names_the_metrics_it_spoils(
    short_sweep: SweepSettings,
) -> None:
    clean = _clean(short_sweep)
    clipped = AudioSignal(
        samples=np.clip(clean.samples * 4.0, -0.3, 0.3), sample_rate=clean.sample_rate, source="daw"
    )
    report = assess(_analysed(short_sweep, clipped))
    assert json.dumps(report.to_dict())
    assert report.overall is HealthStatus.INVALID
    level = next(check for check in report.checks if check.id == "level")
    assert level.status is HealthStatus.INVALID
    assert "flat-topped" in level.reason and "-10." in level.reason
    assert "decay" in level.affects and "energy" in level.affects
    assert level.fix and "Lower" in level.fix[0]
    # The result withholds every decay number, and the report says so.
    assert "decay" in report.unavailable and "energy" in report.unavailable
    assert "decay" in report.affected


def test_dropouts_in_the_sweep_are_found_and_placed(short_sweep: SweepSettings) -> None:
    clean = _clean(short_sweep)
    rate = clean.sample_rate
    samples = clean.samples.copy()
    gap = int(2.0 * rate)
    samples[gap : gap + int(0.010 * rate)] = 0.0  # a lost buffer written as zeros
    held = int(2.4 * rate)
    samples[held : held + int(0.003 * rate)] = samples[held]  # a frozen sample
    result = _analysed(short_sweep, AudioSignal(samples=samples, sample_rate=rate, source="daw"))
    assert result.dropouts is not None
    assert len(result.dropouts.dropouts) == 2
    first, second = result.dropouts.dropouts
    assert first.start_s == pytest.approx(2.0, abs=0.001)
    assert first.duration_ms == pytest.approx(10.0, abs=0.1)
    assert first.sweep_hz is not None and 100.0 < first.sweep_hz < 5000.0
    assert second.duration_ms == pytest.approx(3.0, abs=0.1)
    assert any("dropout" in warning for warning in result.warnings)
    check = _by_id(result)["dropouts"]
    assert json.dumps(assess(result).to_dict())  # evidence holds plain numbers only
    assert check.status is HealthStatus.WARNING  # 13 ms in all: below the invalid limit
    assert "2 dropout" in check.reason and "frequency_response" in check.affects
    assert check.evidence["count"] == 2
    samples[gap : gap + int(DROPOUTS_INVALID_MS / 1000.0 * rate) + 10] = 0.0
    worse = _analysed(short_sweep, AudioSignal(samples=samples, sample_rate=rate, source="daw"))
    assert _by_id(worse)["dropouts"].status is HealthStatus.INVALID


def test_a_dropout_record_round_trips_through_result_json(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    from jsonschema import Draft202012Validator

    from reverbscope.io.session_store import load_measurement, save_measurement
    from reverbscope.models.session import MeasurementSession
    from reverbscope.schemas import load_schema

    clean = _clean(short_sweep)
    samples = clean.samples.copy()
    gap = int(2.0 * clean.sample_rate)
    samples[gap : gap + 200] = 0.0
    result = _analysed(
        short_sweep, AudioSignal(samples=samples, sample_rate=clean.sample_rate, source="daw")
    )
    Draft202012Validator(load_schema("result")).validate(result.to_dict())
    folder = tmp_path / "session"
    save_measurement(folder, MeasurementSession(), result, copy_recording=False)
    loaded = load_measurement(folder).result
    assert loaded.dropouts is not None
    assert loaded.dropouts.to_dict() == result.dropouts.to_dict()  # type: ignore[union-attr]
    # A result.json from before the check existed has no dropouts record and no check.
    data = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    del data["dropouts"]
    older = AnalysisResult.from_dict(data)
    assert older.dropouts is None
    assert "dropouts" not in _by_id(older)


def test_a_sweep_played_slow_is_invalid_with_the_daw_steps(short_sweep: SweepSettings) -> None:
    """A 48 kHz sweep played in a 44.1 kHz project runs 8.8 % slow: the check
    names the rate to generate at and where each DAW sets it."""
    clean = _clean(short_sweep)
    slow = AudioSignal(
        samples=np.asarray(resample_poly(clean.samples, 160, 147)),
        sample_rate=clean.sample_rate,
        source="daw",
    )
    try:
        result = _analysed(short_sweep, slow)
    except InvalidAudioError as exc:
        steps = failure_guidance(exc)
        assert steps and "44100" in steps[0]
        assert any(line.startswith("Logic Pro: ") for line in steps)
        return
    check = _by_id(result)["playback_speed"]
    assert check.status is HealthStatus.INVALID
    assert check.evidence["kind"] == KIND_SAMPLE_RATE
    assert "44100" in check.fix[0] and "Step 1" in check.fix[0]
    assert any(line.startswith("Pro Tools: ") for line in check.details)
    assert any("Project ▸ Project Setup" in line for line in check.details)
    assert assess(result).overall is HealthStatus.INVALID
    direct = _by_id(result)["direct_sound"]
    assert direct.status is HealthStatus.INVALID and direct.fix == ()


def test_failure_guidance_follows_the_speed_the_pipeline_attached() -> None:
    exc = InvalidAudioError("the sweep in the recording runs at 92.0 % of the speed")
    assert failure_guidance(exc) == ()
    exc.playback_speed = PlaybackSpeed(
        speed_ratio=0.92, kind="time_stretch", generated_rate_hz=48000, played_rate_hz=None
    )
    steps = failure_guidance(exc)
    assert "time-stretching off" in steps[0]
    assert any(line.startswith("Ableton Live: ") and "Warp off" in line for line in steps)
    assert failure_guidance(ReverbScopeError("x")) == () and failure_guidance(ValueError()) == ()


def test_a_noisy_take_warns_about_the_decay_range(short_sweep: SweepSettings) -> None:
    noisy = synthetic_recording(short_sweep, _room(short_sweep), noise_rms=0.02)
    result = _analysed(short_sweep, noisy)
    check = _by_id(result)["decay_range"]
    assert check.status is HealthStatus.WARNING
    assert "T20" in check.reason and "T30" in check.reason
    assert check.evidence["needed_t30_db"] == pytest.approx(45.0)
    assert check.evidence["needed_t20_db"] == pytest.approx(35.0)
    assert "3 dB per doubling" in check.fix[0]
    assert assess(result).overall is HealthStatus.WARNING


def test_exact_digital_silence_is_invalid(short_sweep: SweepSettings) -> None:
    """A gate, or the test-signal track exported instead of the microphone's."""
    silent = synthetic_recording(short_sweep, _room(short_sweep), noise_rms=0.0)
    result = _analysed(short_sweep, silent)
    assert result.noise.rms_dbfs is None
    check = _by_id(result)["noise"]
    assert check.status is HealthStatus.INVALID
    assert "digital silence" in check.reason
    assert "noise" in assess(result).unavailable


def test_an_imported_impulse_response_is_unknown_where_it_cannot_be_checked(
    short_sweep: SweepSettings,
) -> None:
    rate = short_sweep.sample_rate
    # A pre-roll with a little noise before the direct sound, as a file from
    # another tool has: the detection can then be checked (confidence high).
    samples = make_rir(rate, rt60_s=0.4, length_s=2.0, start_delay_s=0.05)
    samples = samples + np.random.default_rng(3).normal(0.0, 1e-6, samples.shape[0])
    ir = AudioSignal(samples=samples, sample_rate=rate, source="file")
    result = analyze_impulse_response(ir, excitation_band=(50.0, 10000.0))
    report = assess(result)
    checks = {check.id: check for check in report.checks}
    for name in ("reference", "sweep", "level"):
        assert checks[name].status is HealthStatus.UNKNOWN, name
        assert "imported" in checks[name].reason
    for name in ("playback_speed", "distortion", "noise", "dropouts"):
        assert name not in checks, name
    assert checks["length"].status is HealthStatus.GOOD
    assert report.overall is HealthStatus.UNKNOWN


def test_a_reference_wav_without_a_definition_is_a_warning(short_sweep: SweepSettings) -> None:
    from reverbscope.core.sweep import measurement_signal

    clean = _clean(short_sweep)
    reference = Reference.from_signal(measurement_signal(short_sweep), short_sweep.sample_rate)
    result = analyze(clean, reference)
    checks = _by_id(result)
    assert checks["reference"].status is HealthStatus.WARNING
    assert (
        "sidecar" in checks["reference"].reason
        or ".reverbscope-sweep.json" in checks["reference"].fix[0]
    )
    assert checks["playback_speed"].status is HealthStatus.UNKNOWN
    assert checks["distortion"].status is HealthStatus.UNKNOWN


def test_two_passes_and_a_short_tail_are_warnings(short_sweep: SweepSettings) -> None:
    clean = _clean(short_sweep)
    rate = clean.sample_rate
    twice = AudioSignal(
        samples=np.concatenate([clean.samples, clean.samples]), sample_rate=rate, source="daw"
    )
    sweep = _by_id(_analysed(short_sweep, twice))["sweep"]
    assert sweep.status is HealthStatus.WARNING and "2 sweep passes" in sweep.reason
    end = int((short_sweep.pre_silence_s + short_sweep.duration_s + 0.4) * rate)
    short = AudioSignal(samples=clean.samples[:end], sample_rate=rate, source="daw")
    length = _by_id(_analysed(short_sweep, short))["length"]
    assert length.status is HealthStatus.WARNING and "decay" in length.affects


def test_words_are_translated_with_the_report(short_sweep: SweepSettings) -> None:
    from reverbscope.i18n import activate

    result = _analysed(short_sweep, _clean(short_sweep))
    english = assess(result)
    activate("zh_CN")
    try:
        chinese = assess(result)
        assert chinese.locale == "zh_CN"
        assert status_word(HealthStatus.GOOD) != "good"
        assert metric_group_text("decay") != "reverberation"
        assert [check.id for check in chinese.checks] == [check.id for check in english.checks]
        assert all(
            check.title != other.title
            for check, other in zip(chinese.checks, english.checks, strict=True)
        )
    finally:
        activate("en")


def test_the_cli_reports_health_in_text_and_json(
    tmp_path: Path, short_sweep: SweepSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    from reverbscope.cli.main import main
    from reverbscope.io.wav import write_sweep_file, write_wav

    clean = _clean(short_sweep)
    sweep, _sidecar = write_sweep_file(short_sweep, tmp_path / "sweep.wav")
    recording = write_wav(tmp_path / "take.wav", clean.samples, clean.sample_rate, subtype="FLOAT")
    assert main(["analyze", "--recording", str(recording), "--sweep", str(sweep)]) == 0
    text = capsys.readouterr().out
    assert "Measurement health" in text and "10 of 10 checks good" in text
    assert (
        main(["--format", "json", "analyze", "--recording", str(recording), "--sweep", str(sweep)])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["health"]["overall"] == "good"
    assert [check["id"] for check in payload["health"]["checks"]][:2] == ["reference", "sweep"]
    assert payload["dropouts"]["count"] == 0


#: The menu paths and setting names the module's DAW steps rely on. Each must
#: appear in the module's text and in the DAW guide, so the two stay in step.
_DAW_ANCHORS = (
    "Session Setup",
    "File ▸ Import ▸ Audio",
    "Apply SRC",
    "File ▸ Project Settings ▸ Audio ▸ Sample Rate",
    "Project ▸ Project Setup",
    "Session ▸ Session Setup",
    "Song ▸ Song Setup",
    "Live ▸ Settings on macOS) ▸ Audio ▸ In/Out Sample Rate",
    "File ▸ Project Settings ▸ tick Project sample rate",
    "Preferences ▸ Audio ▸ Device tick Request sample rate",
    "Options ▸ Audio settings (F10) ▸ Sample Rate",
    "Dashboard ▸ Settings ▸ Audio",
    "Quality section of Audio Setup ▸ Audio Settings",
    "Disable Elastic Audio",
    "File ▸ Project Settings ▸ Smart Tempo",
    "Set Imported Files To",
    "Flex & Follow",
    "Follow Tempo and Pitch",
    "Enable Flex",
    "Musical Mode",
    "Don't Follow",
    "Auto-Warp Long Samples",
    "Item Properties (F2)",
    "Playback rate",
    "Read sample tempo information",
    "Stretch ▸ Mode",
    "Don't Time Scale",
)


def test_the_daw_steps_name_what_the_daw_guide_names() -> None:
    from reverbscope.health import DAW_SAMPLE_RATE_SETTINGS, DAW_STRETCH_SETTINGS

    module_text = "\n".join(
        text for _daw, text in (*DAW_SAMPLE_RATE_SETTINGS, *DAW_STRETCH_SETTINGS)
    )
    # The guide wraps its lines and marks interface words in italics.
    guide = " ".join(
        Path("docs/user-guide/daw-setup.md").read_text(encoding="utf-8").replace("*", "").split()
    )
    for anchor in _DAW_ANCHORS:
        assert anchor in module_text, anchor
        assert anchor in guide, anchor
    names = {daw for daw, _text in (*DAW_SAMPLE_RATE_SETTINGS, *DAW_STRETCH_SETTINGS)}
    for daw in names:
        assert daw.split(" / ")[0] in guide, daw


# --- Cases taken over from the independent health implementation (PR #46) ----------


DEVICE_WARNINGS = (
    "the audio device reported 2 buffer problem(s) during the take (input overflow, output "
    "underflow); the recording may contain dropouts",
    "the audio stream reported 44100 Hz instead of the requested 48000 Hz; the recording's "
    "time scale cannot be trusted",
    "the audio device reported timing problems in this take, so its decay and energy metrics "
    "are unreliable. Check the stream settings and repeat the measurement",
    "input underflow",
    "input overflow",
    "output underflow",
    "output overflow",
)


@pytest.mark.parametrize("warning", DEVICE_WARNINGS)
def test_every_device_warning_is_invalid_even_with_a_high_confidence_direct_sound(
    short_sweep: SweepSettings, warning: str
) -> None:
    """The stream's own flags (older results), the buffer and timing sentences
    and a stream that ran at another rate than requested all invalidate the
    take; the direct sound's confidence does not outrank a wrong time base."""
    from dataclasses import replace

    result = replace(_analysed(short_sweep, _clean(short_sweep)), warnings=(warning, warning))
    report = assess(result)
    device = _by_id(result)["device"]
    assert report.overall is HealthStatus.INVALID
    assert device.status is HealthStatus.INVALID  # type: ignore[attr-defined]
    assert "buffer" in " ".join(device.fix)  # type: ignore[attr-defined]


def test_incidental_timing_words_do_not_invent_a_device_fault(short_sweep: SweepSettings) -> None:
    from dataclasses import replace

    result = replace(
        _analysed(short_sweep, _clean(short_sweep)),
        warnings=("No underflow or overflow was detected; check another limitation.",),
    )
    assert "device" not in _by_id(result)
    assert assess(result).overall is HealthStatus.GOOD


def test_a_refused_separate_loopback_does_not_invalidate_the_microphone_take(
    short_sweep: SweepSettings,
) -> None:
    """The loopback's own device problems refuse the compensation (a warning on
    the loopback check); they are not a fault of the microphone take."""
    from dataclasses import replace

    from reverbscope.models.result import LoopbackResult

    reason = (
        "the separate loopback recording has device timing problems; loopback compensation "
        "was not applied"
    )
    result = _analysed(short_sweep, _clean(short_sweep))
    result = replace(
        result,
        warnings=(reason,),
        impulse_response=replace(
            result.impulse_response, loopback=LoopbackResult(2, False, reason)
        ),
    )
    checks = _by_id(result)
    assert "device" not in checks
    assert checks["loopback"].status is HealthStatus.WARNING  # type: ignore[attr-defined]
    assert assess(result).overall is HealthStatus.WARNING


def test_an_unknown_playback_diagnosis_is_unknown_not_a_time_stretch(
    short_sweep: SweepSettings,
) -> None:
    from dataclasses import replace

    result = _analysed(short_sweep, _clean(short_sweep))
    result = replace(
        result,
        impulse_response=replace(
            result.impulse_response, playback_speed=PlaybackSpeed(0.92, "future_diagnosis", 48000)
        ),
    )
    check = _by_id(result)["playback_speed"]
    # The speed error itself is evidence: the take is invalid. Its cause is
    # not claimed: no DAW stretch steps are given for a diagnosis this
    # version does not know.
    assert check.status is HealthStatus.INVALID  # type: ignore[attr-defined]
    assert "not recognised" in " ".join(check.fix)  # type: ignore[attr-defined]
    assert check.details == ()  # type: ignore[attr-defined]
    assert not any("Warp" in line for line in check.fix)  # type: ignore[attr-defined]


def test_assessing_a_result_changes_nothing_in_it(short_sweep: SweepSettings) -> None:
    result = _analysed(short_sweep, _clean(short_sweep))
    before = json.dumps(result.to_dict(), sort_keys=True)
    assess(result)
    assert json.dumps(result.to_dict(), sort_keys=True) == before
