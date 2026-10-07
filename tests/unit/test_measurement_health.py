"""Health is derived from existing evidence, never a score or a validity repair."""

from dataclasses import replace

import pytest

from reverbscope.i18n import activate, diag
from reverbscope.measurement_health import HealthStatus, derive_measurement_health
from reverbscope.models.result import (
    KIND_SAMPLE_RATE,
    KIND_TIME_STRETCH,
    ClippingCheck,
    LoopbackResult,
    PlaybackSpeed,
    Validity,
)
from tests.health_fixtures import healthy_result


def test_good_means_no_known_measurement_problem_not_a_room_score() -> None:
    health = derive_measurement_health(healthy_result())
    assert health.status is HealthStatus.GOOD
    assert health.findings == ()
    assert not hasattr(health, "score")


def test_missing_result_is_unknown() -> None:
    health = derive_measurement_health(None)
    assert health.status is HealthStatus.UNKNOWN
    assert health.findings[0].next_step


@pytest.mark.parametrize("peak", [0.0, -12.0])
def test_clipping_including_attenuated_exports_has_gain_advice(peak: float) -> None:
    result = replace(healthy_result(), clipping=ClippingCheck(peak, 3, 12, True))
    health = derive_measurement_health(result)
    finding = next(f for f in health.findings if f.code == "recording.clipping")
    assert health.status is HealthStatus.INVALID
    assert finding.severity is HealthStatus.INVALID
    assert "suspected clipping" in finding.title.lower()
    assert "preamp gain" in finding.next_step and "playback level" in finding.next_step
    assert finding.evidence and str(peak) in " ".join(finding.evidence)


@pytest.mark.parametrize(
    "confidence, status", [("medium", HealthStatus.WARNING), ("low", HealthStatus.INVALID)]
)
def test_direct_sound_uncertainty_is_not_promoted(confidence: str, status: HealthStatus) -> None:
    result = healthy_result()
    result = replace(
        result,
        impulse_response=replace(
            result.impulse_response, direct_sound_confidence=confidence, pre_peak_margin_db=8.0
        ),
    )
    before = result.to_dict()
    health = derive_measurement_health(result)
    finding = next(f for f in health.findings if f.code == f"direct_sound.{confidence}_confidence")
    assert health.status is status
    assert "8.0" in " ".join(finding.evidence)
    assert "microphone" in finding.next_step
    if confidence == "low":
        for metric in ("EDT", "T20", "T30", "C50", "C80", "D50"):
            assert metric in finding.explanation
    assert result.to_dict() == before


def test_insufficient_range_explains_missing_rt60_without_inventing_zero() -> None:
    result = healthy_result()
    band = replace(
        result.decay.broadband,
        t30=replace(result.decay.broadband.t30, seconds=None, validity=Validity.INSUFFICIENT_RANGE),
        peak_to_noise_db=28.0,
    )
    health = derive_measurement_health(replace(result, decay=replace(result.decay, broadband=band)))
    finding = next(f for f in health.findings if f.code == "decay.insufficient_range")
    assert "RT60 = 0" in finding.explanation
    assert "dynamic range" in finding.explanation
    assert "T30" in " ".join(finding.evidence)
    for word in ("noise", "sweep", "playback level", "microphone"):
        assert word in finding.next_step
    noise = next(f for f in health.findings if f.code == "noise.limited_range")
    assert "28.0" in " ".join(noise.evidence)


@pytest.mark.parametrize("kind", [KIND_SAMPLE_RATE, KIND_TIME_STRETCH])
def test_speed_diagnosis_has_specific_daw_steps(kind: str) -> None:
    result = healthy_result()
    speed = PlaybackSpeed(44100 / 48000, kind, 48000, 44100 if kind == KIND_SAMPLE_RATE else None)
    health = derive_measurement_health(
        replace(result, impulse_response=replace(result.impulse_response, playback_speed=speed))
    )
    finding = next(f for f in health.findings if f.code == f"playback.{kind}")
    assert health.status is HealthStatus.INVALID
    if kind == KIND_SAMPLE_RATE:
        for phrase in ("DAW project", "import", "interface", "playback conversion"):
            assert phrase in finding.next_step
    else:
        for phrase in ("Warp", "Flex", "Follow Tempo", "Musical Mode", "clip stretch"):
            assert phrase in finding.next_step


DEVICE_WARNINGS = (
    diag(
        "the audio device reported {count} buffer problem(s) during the take ({flags}); the recording may contain dropouts",
        count=2,
        flags="input overflow, output underflow",
    ),
    diag(
        "the audio stream reported {actual:g} Hz instead of the requested {requested:g} Hz; the recording's time scale cannot be trusted",
        actual=44100,
        requested=48000,
    ),
    diag(
        "the audio device reported timing problems in this take, so its decay and energy metrics are unreliable. Check the stream settings and repeat the measurement"
    ),
    "input underflow",
    "input overflow",
    "output underflow",
    "output overflow",
)


@pytest.mark.parametrize("warning", DEVICE_WARNINGS)
def test_device_timing_warnings_are_invalid_even_with_high_confidence(warning: str) -> None:
    result = replace(healthy_result(), warnings=(warning, warning))
    health = derive_measurement_health(result)
    finding = next(f for f in health.findings if f.code == "device.timing")
    assert health.status is HealthStatus.INVALID
    assert len([f for f in health.findings if f.code == "device.timing"]) == 1
    assert "decay" in finding.explanation and "energy" in finding.explanation
    assert "buffer" in finding.next_step and "again" in finding.next_step


def test_truncated_reflection_window_is_not_clean() -> None:
    result = healthy_result()
    result = replace(
        result,
        reflections=replace(
            result.reflections, window_truncated=True, analysed_window_ms=(0.5, 30.0)
        ),
    )
    health = derive_measurement_health(result)
    finding = next(f for f in health.findings if f.code == "reflection.truncated_window")
    assert health.status is HealthStatus.WARNING
    assert "ended too early" in finding.explanation
    assert "longer" in finding.next_step
    assert "30.0" in " ".join(finding.evidence)


def test_missing_noise_or_clipping_evidence_cannot_be_good() -> None:
    result = healthy_result()
    result = replace(
        result,
        clipping=None,
        noise=replace(result.noise, rms_dbfs=None, notes=("no quiet segment",)),
    )
    health = derive_measurement_health(result)
    assert health.status is HealthStatus.UNKNOWN
    assert {f.code for f in health.findings} >= {
        "recording.clipping_unchecked",
        "noise.unavailable",
    }


def test_noise_level_alone_is_not_an_arbitrary_acceptance_threshold() -> None:
    result = healthy_result()
    health = derive_measurement_health(replace(result, noise=replace(result.noise, rms_dbfs=-12.0)))
    assert health.status is HealthStatus.GOOD


def test_rejected_loopback_explains_routing() -> None:
    result = healthy_result()
    result = replace(
        result,
        impulse_response=replace(
            result.impulse_response,
            loopback=LoopbackResult(2, False, "reference channel could not be used"),
        ),
    )
    health = derive_measurement_health(result)
    finding = next(f for f in health.findings if f.code == "loopback.rejected")
    assert health.status is HealthStatus.WARNING
    assert "routing" in finding.next_step


def test_unrecognised_analysis_warning_is_kept_and_never_good() -> None:
    warning = "a future analyzer raised a new diagnostic"
    health = derive_measurement_health(replace(healthy_result(), warnings=(warning, warning)))
    finding = next(f for f in health.findings if f.code == "analysis.warning")
    assert health.status is HealthStatus.WARNING
    assert finding.evidence == (warning,)


def test_all_findings_have_required_fields_and_severity_order() -> None:
    result = healthy_result()
    result = replace(
        result,
        clipping=ClippingCheck(0.0, 2, 10, True),
        warnings=("a diagnostic",),
        impulse_response=replace(result.impulse_response, direct_sound_confidence="medium"),
        noise=replace(result.noise, rms_dbfs=None),
    )
    health = derive_measurement_health(result)
    ranks = {
        HealthStatus.INVALID: 0,
        HealthStatus.WARNING: 1,
        HealthStatus.UNKNOWN: 2,
        HealthStatus.GOOD: 3,
    }
    assert [ranks[f.severity] for f in health.findings] == sorted(
        ranks[f.severity] for f in health.findings
    )
    for f in health.findings:
        assert f.code and f.title and f.explanation and f.evidence and f.next_step


def test_chinese_has_the_same_stable_codes_and_translated_directions() -> None:
    result = replace(
        healthy_result(), clipping=ClippingCheck(0.0, 2, 10, True), warnings=DEVICE_WARNINGS[:1]
    )
    english = derive_measurement_health(result)
    activate("zh_CN")
    chinese = derive_measurement_health(result)
    assert chinese.status == english.status
    assert [f.code for f in chinese.findings] == [f.code for f in english.findings]
    for f in chinese.findings:
        for text in (f.title, f.explanation, f.next_step):
            assert any("一" <= ch <= "鿿" for ch in text), text


def test_derivation_does_not_change_metrics_curves_or_result_json() -> None:
    result = healthy_result()
    before = result.to_dict()
    ir_bytes = result.impulse_response.samples.tobytes()
    decay_bytes = result.decay.broadband.edc_db.tobytes()
    derive_measurement_health(result)
    assert result.to_dict() == before
    assert result.impulse_response.samples.tobytes() == ir_bytes
    assert result.decay.broadband.edc_db.tobytes() == decay_bytes


def test_unknown_playback_kind_does_not_invent_a_time_stretch_diagnosis() -> None:
    result = healthy_result()
    result = replace(
        result,
        impulse_response=replace(
            result.impulse_response, playback_speed=PlaybackSpeed(0.92, "future_diagnosis", 48000)
        ),
    )
    health = derive_measurement_health(result)
    assert health.status is HealthStatus.UNKNOWN
    finding = next(f for f in health.findings if f.code == "playback.unknown_diagnosis")
    assert "Time stretch" not in finding.title
    assert "92.0" in " ".join(finding.evidence)


def test_clipping_only_in_legacy_diagnostics_is_still_invalid() -> None:
    warning = diag(
        "recording has {runs} flat-topped peaks ({samples} samples) at {peak_dbfs:.1f} dBFS, its highest level: probable clipping; lower the playback or input level and measure again",
        runs=2,
        samples=8,
        peak_dbfs=0.0,
    )
    health = derive_measurement_health(
        replace(healthy_result(), clipping=None, warnings=(warning,))
    )
    assert health.status is HealthStatus.INVALID
    assert [f.code for f in health.findings] == ["recording.clipping"]


def test_incidental_timing_words_do_not_invent_a_device_fault() -> None:
    warning = "No underflow or overflow was detected; check another limitation."
    health = derive_measurement_health(replace(healthy_result(), warnings=(warning,)))
    assert [f.code for f in health.findings] == ["analysis.warning"]


@pytest.mark.parametrize("level", [None, float("nan"), float("inf")])
def test_missing_or_nonfinite_noise_evidence_is_unknown(level: float | None) -> None:
    result = healthy_result()
    result = replace(result, noise=replace(result.noise, rms_dbfs=level))
    health = derive_measurement_health(result)
    assert health.status is HealthStatus.UNKNOWN
    assert any(f.code == "noise.unavailable" for f in health.findings)


def test_unreliable_metrics_stay_warning_and_keep_the_original_reasons() -> None:
    result = healthy_result()
    reason = "Evaluation range covers fewer than 3 samples"
    band = replace(
        result.decay.broadband,
        t30=replace(result.decay.broadband.t30, validity=Validity.UNRELIABLE, reason=reason),
    )
    result = replace(result, decay=replace(result.decay, broadband=band))
    before = result.to_dict()
    health = derive_measurement_health(result)
    finding = next(f for f in health.findings if f.code == "decay.unreliable")
    assert health.status is HealthStatus.WARNING
    assert reason in finding.evidence
    assert result.to_dict() == before


def test_missing_band_metrics_and_outside_excitation_are_explicit() -> None:
    result = healthy_result()
    outside = replace(
        result.decay.broadband,
        band_label="31.5 Hz",
        t30=replace(result.decay.broadband.t30, seconds=None, validity=Validity.OUTSIDE_EXCITATION),
    )
    missing = replace(
        result.decay.broadband,
        band_label="63 Hz",
        t30=replace(result.decay.broadband.t30, seconds=None, validity=Validity.NOT_COMPUTED),
    )
    health = derive_measurement_health(
        replace(result, decay=replace(result.decay, bands=(outside, missing)))
    )
    assert health.status is HealthStatus.WARNING
    assert {f.code for f in health.findings} >= {"excitation.outside_range", "decay.not_computed"}


def test_timing_fault_stored_only_in_metric_reason_is_not_hidden() -> None:
    result = healthy_result()
    band = replace(
        result.decay.broadband,
        t30=replace(
            result.decay.broadband.t30, validity=Validity.UNRELIABLE, reason=DEVICE_WARNINGS[2]
        ),
    )
    health = derive_measurement_health(replace(result, decay=replace(result.decay, broadband=band)))
    assert health.status is HealthStatus.INVALID
    assert any(f.code == "device.timing" for f in health.findings)


def test_rejected_faulty_loopback_does_not_invalidate_the_uncompensated_microphone_take() -> None:
    result = healthy_result()
    reason = "the separate loopback recording has device timing problems; interface compensation was refused"
    loopback = LoopbackResult(2, False, reason)
    health = derive_measurement_health(
        replace(
            result,
            warnings=(reason,),
            impulse_response=replace(result.impulse_response, loopback=loopback),
        )
    )
    assert health.status is HealthStatus.WARNING
    assert any(f.code == "loopback.rejected" for f in health.findings)
