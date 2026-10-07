"""Derived measurement health, without DSP, scores or persisted fields.

Only existing diagnostics and validity flags are interpreted here. No new
acceptance thresholds are applied to dBFS, SNR, confidence or decay fits.
In particular, a noise level alone says nothing about acoustic suitability.
The core's INSUFFICIENT_RANGE flag supplies the decay-range engineering gate
(evaluation range plus the core's noise margin), rather than another SNR
threshold in this layer. GOOD means the available checks found no problem;
it is neither a room rating nor evidence of hardware validation.

Diagnostics in schema v1 are English sentences, not codes. Recognition of
legacy/device diagnostics is centralised below and anchored to the existing
producers. Unrecognised warnings remain visible and cannot produce GOOD.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from reverbscope.i18n import _, list_join, localize
from reverbscope.interpretation.profiles import band_text, confidence_text
from reverbscope.labels import validity_word
from reverbscope.models.result import (
    EXCITATION_SOURCE_UNKNOWN,
    KIND_SAMPLE_RATE,
    KIND_TIME_STRETCH,
    AnalysisResult,
    BandDecay,
    Validity,
)


class HealthStatus(StrEnum):
    GOOD = "GOOD"
    WARNING = "WARNING"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


_PRIORITY = {
    HealthStatus.INVALID: 0,
    HealthStatus.WARNING: 1,
    HealthStatus.UNKNOWN: 2,
    HealthStatus.GOOD: 3,
}


@dataclass(frozen=True)
class HealthFinding:
    """An ephemeral explanation in the active UI language, with a stable code."""

    code: str
    severity: HealthStatus
    title: str
    explanation: str
    evidence: tuple[str, ...]
    next_step: str


@dataclass(frozen=True)
class MeasurementHealth:
    status: HealthStatus
    findings: tuple[HealthFinding, ...]


def health_status_text(status: HealthStatus) -> str:
    return {
        HealthStatus.GOOD: _("Good"),
        HealthStatus.WARNING: _("Warning"),
        HealthStatus.INVALID: _("Invalid"),
        HealthStatus.UNKNOWN: _("Unknown"),
    }[status]


def health_summary(status: HealthStatus) -> str:
    return {
        HealthStatus.GOOD: _(
            "No measurement problems found in the available checks. This is not a room score."
        ),
        HealthStatus.WARNING: _(
            "Some metrics or checks need attention. Follow the steps below before relying on them."
        ),
        HealthStatus.INVALID: _(
            "Do not use this take for reliable decay or energy conclusions. Fix the reported "
            "problems and measure again."
        ),
        HealthStatus.UNKNOWN: _(
            "Some checks lack evidence. Missing diagnostics do not mean a passed measurement."
        ),
    }[status]


def _unique(texts: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(text for text in texts if text))


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _diagnosis_kind(text: str) -> str | None:
    """Recognise existing producer sentences, not incidental keywords."""
    # Decay notes wrap the original diagnosis with its band label.
    text = re.sub(r"^decay analysis, [^:]+: ", "", text)
    if text.startswith("the separate loopback recording has device timing problems; "):
        # A refused reference was never applied to the microphone take.
        # Keep its failure visible without inventing a microphone clock fault.
        return "loopback_rejected"
    if text in {"input underflow", "input overflow", "output underflow", "output overflow"}:
        return "timing"
    if re.fullmatch(
        r"the audio device reported \d+ buffer problem\(s\) during the take "
        r"\([^)]+\); the recording may contain dropouts",
        text,
    ) or text.startswith(
        ("the audio device reported timing problems in this take, so its decay and energy ",)
    ):
        return "timing"
    if re.fullmatch(
        r"the audio stream reported [\d.eE+-]+ Hz instead of the requested [\d.eE+-]+ Hz; "
        r"the recording's time scale cannot be trusted",
        text,
    ):
        return "timing"
    if (
        re.match(r"^recording has \d+ flat-topped peaks \(\d+ samples\) at ", text)
        and "probable clipping" in text
    ) or text.startswith("the recording clips, so the measurement chain was not linear"):
        return "clipping"
    if text.startswith("the sweep in the recording runs at "):
        if "without sample-rate conversion" in text:
            return KIND_SAMPLE_RATE
        if "the DAW time-stretched it" in text:
            return KIND_TIME_STRETCH
    if text.startswith(
        (
            "direct-sound detection confidence is low (",
            "there is no content before the direct sound to check ",
        )
    ):
        return "low_confidence"
    if text.startswith("content before the direct sound is only "):
        if text.endswith("direct-sound detection confidence is low"):
            return "low_confidence"
        if text.endswith("direct-sound detection confidence is medium"):
            return "medium_confidence"
    if text.startswith("Insufficient decay range:"):
        return "insufficient_range"
    if text.startswith("the impulse response ends where the next sweep pass starts ("):
        return "short_tail"
    if re.match(r"^only [\d.]+ s of decay were recorded after the sweep; ", text):
        return "short_tail"
    return None


def _band_metrics(band: BandDecay) -> tuple[tuple[str, Validity, str | None], ...]:
    return tuple(
        (metric.name, metric.validity, metric.reason)
        for metric in (band.edt, band.t20, band.t30, band.c50, band.c80, band.d50, band.centre_time)
    )


def _range_evidence(bands: Iterable[BandDecay]) -> tuple[str, ...]:
    return tuple(
        _("{band}: peak-to-noise {range:.1f} dB").format(
            band=band_text(band.band_label), range=band.peak_to_noise_db
        )
        for band in bands
        if _finite(band.peak_to_noise_db)
    )


def derive_measurement_health(result: AnalysisResult | None) -> MeasurementHealth:
    """Read an existing result without modifying its metrics, arrays or schema.

    Aggregate precedence: INVALID > WARNING > UNKNOWN > GOOD. Optional
    loopback absence is normal; a supplied but rejected loopback is a warning.
    Clipping/noise checks absent from older or imported results are UNKNOWN,
    not false/zero. A high direct-sound confidence never overrides a fault.
    """
    if result is None:
        finding = HealthFinding(
            "measurement.missing",
            HealthStatus.UNKNOWN,
            _("No measurement available"),
            _("There is no analysis result to check."),
            (_("Analysis result is missing."),),
            _("Run a measurement or open an existing result to see its diagnostics."),
        )
        return MeasurementHealth(HealthStatus.UNKNOWN, (finding,))

    findings: list[HealthFinding] = []
    handled: set[str] = set()
    ir = result.impulse_response
    bands = (result.decay.broadband, *result.decay.bands)
    diagnostics = _unique(
        (
            *result.warnings,
            *ir.notes,
            *result.decay.notes,
            *(warning for band in bands for warning in band.warnings),
            *(
                reason
                for band in bands
                for _name, _validity, reason in _band_metrics(band)
                if reason
            ),
        )
    )
    groups: dict[str, tuple[str, ...]] = {}
    for text in diagnostics:
        kind = _diagnosis_kind(text)
        if kind:
            groups[kind] = (*groups.get(kind, ()), text)

    def add(
        code: str,
        severity: HealthStatus,
        title: str,
        explanation: str,
        evidence: Iterable[str],
        next_step: str,
        *kinds: str,
    ) -> None:
        findings.append(
            HealthFinding(code, severity, title, explanation, _unique(evidence), next_step)
        )
        handled.update(kinds)

    clipping = result.clipping
    if (clipping is not None and clipping.clipped) or groups.get("clipping"):
        evidence = tuple(localize(text) for text in groups.get("clipping", ()))
        if clipping is not None:
            evidence = (
                _("Flat-topped peaks: {runs}; samples: {samples}; peak: {peak:.1f} dBFS").format(
                    runs=clipping.runs, samples=clipping.samples, peak=clipping.peak_dbfs
                ),
                *evidence,
            )
        add(
            "recording.clipping",
            HealthStatus.INVALID,
            _("Clipping / suspected clipping"),
            _(
                "Flat-topped peaks indicate a nonlinear measurement chain. Decay and energy results may be unreliable, even if the export was later attenuated."
            ),
            evidence,
            _(
                "Lower preamp gain / playback level, remove limiting or saturation from the measurement path, and measure again."
            ),
            "clipping",
        )
    elif clipping is None:
        add(
            "recording.clipping_unchecked",
            HealthStatus.UNKNOWN,
            _("Clipping was not checked"),
            _(
                "This result contains no recording clipping check; it is not evidence of a clean recording."
            ),
            (_("No clipping diagnostic is available."),),
            _(
                "For a full check, analyze the original microphone recording with its reference sweep."
            ),
        )

    confidence = ir.direct_sound_confidence
    if groups.get("low_confidence"):
        confidence = "low"
    elif confidence == "high" and groups.get("medium_confidence"):
        confidence = "medium"
    direct_evidence = (
        _("Direct-sound confidence: {confidence}").format(confidence=confidence_text(confidence)),
        _("Pre-peak margin: {margin:.1f} dB").format(margin=ir.pre_peak_margin_db)
        if _finite(ir.pre_peak_margin_db)
        else _("Pre-peak margin is not checkable."),
    )
    if confidence in {"low", "medium"}:
        low = confidence == "low"
        add(
            f"direct_sound.{confidence}_confidence",
            HealthStatus.INVALID if low else HealthStatus.WARNING,
            _("Low direct-sound confidence") if low else _("Uncertain direct-sound detection"),
            _(
                "The direct sound is uncertain. EDT, T20, T30, C50, C80 and D50, as well as reflection delays and levels, may be unreliable."
            )
            if low
            else _(
                "Direct-sound identification has some uncertainty. Check placement and the reference before relying on timing-sensitive results."
            ),
            direct_evidence,
            _(
                "Reposition the microphone and loudspeaker for a clearer direct path, reduce background noise to improve SNR, verify the reference sweep and input channel, and measure again."
            ),
            "low_confidence",
            "medium_confidence",
        )
    elif confidence != "high":
        add(
            "direct_sound.unknown_confidence",
            HealthStatus.UNKNOWN,
            _("Direct-sound confidence is unknown"),
            _("The stored confidence is not a recognised measurement diagnostic."),
            direct_evidence,
            _("Analyze the original recording again with the correct reference sweep."),
        )

    speed = ir.playback_speed
    speed_kind = speed.kind if speed is not None else None
    if speed_kind is None:
        speed_kind = next(
            (kind for kind in (KIND_SAMPLE_RATE, KIND_TIME_STRETCH) if groups.get(kind)), None
        )
    if speed_kind is not None:
        evidence = tuple(localize(text) for text in groups.get(speed_kind, ()))
        if speed is not None:
            evidence = (
                _("Playback speed: {percent:.1f} %; generated rate: {rate} Hz").format(
                    percent=speed.speed_ratio * 100.0, rate=speed.generated_rate_hz
                ),
                *evidence,
            )
            if speed.played_rate_hz is not None:
                evidence += (
                    _("Diagnosed playback rate: {rate} Hz").format(rate=speed.played_rate_hz),
                )
        sample_rate = speed_kind == KIND_SAMPLE_RATE
        known_kind = speed_kind in {KIND_SAMPLE_RATE, KIND_TIME_STRETCH}
        add(
            f"playback.{speed_kind}" if known_kind else "playback.unknown_diagnosis",
            HealthStatus.INVALID if known_kind else HealthStatus.UNKNOWN,
            _("Sample-rate / playback speed mismatch")
            if sample_rate
            else _("Time stretch / playback speed mismatch")
            if known_kind
            else _("Unrecognised playback-speed diagnosis"),
            _(
                "The sweep did not play at its generated speed. The deconvolved response cannot support reliable decay or energy conclusions."
            )
            if known_kind
            else _(
                "The stored speed diagnosis is not recognised. Its cause cannot be inferred from this result."
            ),
            evidence or (_("An existing playback-speed diagnostic reported a mismatch."),),
            _(
                "Check the DAW project sample rate, import conversion, interface rate and playback conversion. Generate at the project rate or use proper sample-rate conversion on import, then measure again."
            )
            if sample_rate
            else _(
                "Disable Warp, Flex, Follow Tempo, Musical Mode and clip stretch for the sweep clip. Replay it at its original speed and measure again."
            )
            if known_kind
            else _(
                "Check the original sweep, DAW rate and stretch settings, then analyze the recording again."
            ),
            speed_kind,
        )

    if groups.get("timing"):
        add(
            "device.timing",
            HealthStatus.INVALID,
            _("Device timing fault"),
            _(
                "Underflow, overflow, a reported sample-rate mismatch or another timing fault can change the recording's time scale or lose samples. This take may not support reliable decay or energy judgments."
            ),
            (localize(text) for text in groups["timing"]),
            _(
                "Increase the audio buffer / latency, close other audio programs, match the requested and interface sample rates, check the device clock and routing, and measure again."
            ),
            "timing",
        )

    for validity, code, title, explanation, next_step in (
        (
            Validity.INSUFFICIENT_RANGE,
            "decay.insufficient_range",
            _("Insufficient decay range"),
            _(
                "This does not mean RT60 = 0. The recording lacks enough usable dynamic range to support the affected decay or energy metrics; missing values must not be treated as zero."
            ),
            _(
                "Lower environmental noise, increase the separation between the sweep and background noise, adjust playback level within the chain's headroom, improve microphone placement, and measure again."
            ),
        ),
        (
            Validity.UNRELIABLE,
            "decay.unreliable",
            _("Unreliable decay / energy metrics"),
            _(
                "The analysis already marked these metrics unreliable. A displayed number does not make them valid."
            ),
            _(
                "Read the metric reasons below, check the direct path, noise and recording duration, correct the measurement setup, and measure again."
            ),
        ),
        (
            Validity.OUTSIDE_EXCITATION,
            "excitation.outside_range",
            _("Bands outside the excitation range"),
            _(
                "These bands were not fully excited. Their missing metrics do not describe the room's decay."
            ),
            _(
                "Use a sweep covering the required bands and a suitable sample rate, or limit conclusions to the actually excited range."
            ),
        ),
        (
            Validity.NOT_COMPUTED,
            "decay.not_computed",
            _("Metrics were not computed"),
            _(
                "No validity judgment is available for these metrics. Missing results are not measured zeros."
            ),
            _(
                "Analyze the original measurement again, or limit conclusions to metrics that were computed and marked valid."
            ),
        ),
    ):
        affected = tuple(
            band for band in bands if any(v is validity for _n, v, _r in _band_metrics(band))
        )
        if not affected:
            continue
        evidence = tuple(
            _("{band}: {metrics} ({validity})").format(
                band=band_text(band.band_label),
                metrics=list_join(name for name, v, _r in _band_metrics(band) if v is validity),
                validity=validity_word(validity),
            )
            for band in affected
        ) + _unique(
            localize(reason)
            for band in affected
            for _n, v, reason in _band_metrics(band)
            if v is validity and reason
        )
        severity = (
            HealthStatus.UNKNOWN if validity is Validity.NOT_COMPUTED else HealthStatus.WARNING
        )
        add(
            code,
            severity,
            title,
            explanation,
            evidence + _range_evidence(affected),
            next_step,
            *(("insufficient_range",) if validity is Validity.INSUFFICIENT_RANGE else ()),
        )

    limited = tuple(
        band
        for band in bands
        if any(v is Validity.INSUFFICIENT_RANGE for _n, v, _r in _band_metrics(band))
        and _finite(band.peak_to_noise_db)
    )
    noise = result.noise
    noise_evidence = (
        (
            _("Quiet-segment noise: {level:.1f} dBFS RMS (uncalibrated)").format(
                level=noise.rms_dbfs
            ),
        )
        if _finite(noise.rms_dbfs)
        else ()
    )
    if limited:
        add(
            "noise.limited_range",
            HealthStatus.WARNING,
            _("Noise / decay range needs attention"),
            _(
                "The existing decay validity flags and peak-to-noise data show limited usable range. Noise, recording length or placement may contribute; dBFS alone is not an acoustic noise rating."
            ),
            (*_range_evidence(limited), *noise_evidence),
            _(
                "Reduce fans, traffic and other background noise, keep a quiet pre-sweep segment, improve placement, and adjust playback level without clipping before measuring again."
            ),
        )
    if not noise_evidence or not _finite(result.decay.broadband.peak_to_noise_db):
        add(
            "noise.unavailable",
            HealthStatus.UNKNOWN,
            _("Noise / SNR evidence is incomplete"),
            _(
                "A missing quiet-segment noise level or peak-to-noise value does not mean silence or good SNR. No noise pass/fail threshold is inferred."
            ),
            (
                *noise_evidence,
                *(localize(note) for note in noise.notes),
                _("Quiet-segment noise or broadband peak-to-noise data is unavailable."),
            ),
            _(
                "Record a quiet segment before the sweep and a complete decay tail. Verify the microphone track, disable gates or noise reduction, and analyze the recording again."
            ),
        )

    reflections = result.reflections
    if reflections.window_truncated:
        evidence = (
            _("Requested reflection window: {start:.1f}–{end:.1f} ms").format(
                start=reflections.window_ms[0], end=reflections.window_ms[1]
            ),
        )
        if reflections.analysed_window_ms is not None:
            evidence += (
                _("Available reflection window: {start:.1f}–{end:.1f} ms").format(
                    start=reflections.analysed_window_ms[0], end=reflections.analysed_window_ms[1]
                ),
            )
        add(
            "reflection.truncated_window",
            HealthStatus.WARNING,
            _("Reflection window was truncated"),
            _(
                "The recording ended too early or the response window is incomplete. Later reflections were not examined; no detected reflection does not mean a clean full window."
            ),
            evidence,
            _(
                "Record a longer post-sweep tail, leave more space before another sweep, and keep the complete response when importing or exporting."
            ),
        )
    if groups.get("short_tail"):
        add(
            "recording.short_tail",
            HealthStatus.WARNING,
            _("Recorded decay tail is too short"),
            _(
                "The analysis reports a short response or a response cut off by another sweep. Long decay times may not be measurable."
            ),
            (localize(text) for text in groups["short_tail"]),
            _(
                "Record a longer post-sweep tail, leave more space before another sweep, and keep the complete response when importing or exporting."
            ),
            "short_tail",
        )

    loopback = ir.loopback
    if (loopback is not None and not loopback.compensation_applied) or groups.get(
        "loopback_rejected"
    ):
        add(
            "loopback.rejected",
            HealthStatus.WARNING,
            _("Loopback reference was rejected"),
            _(
                "A loopback channel was supplied, but the analysis refused interface compensation. The result must not be presented as a compensated measurement."
            ),
            (
                *(localize(text) for text in groups.get("loopback_rejected", ())),
                localize(loopback.reason)
                if loopback is not None and loopback.reason
                else _("Loopback compensation was not applied."),
            ),
            _(
                "Check loopback channel routing, reference level, clipping and clock alignment. Correct the electrical reference and measure again, or explicitly proceed without compensation."
            ),
            "loopback_rejected",
        )
    if ir.excitation_band is None or ir.excitation_band.source == EXCITATION_SOURCE_UNKNOWN:
        add(
            "excitation.unknown",
            HealthStatus.UNKNOWN,
            _("Excitation range is unknown"),
            _(
                "The actually excited frequency range is unavailable, so band coverage cannot be confirmed."
            ),
            (_("No known excitation range is stored in this result."),),
            _(
                "Use the matching reference sweep, or supply the known excitation range for an imported impulse response."
            ),
        )

    remaining = _unique(
        localize(text) for text in result.warnings if _diagnosis_kind(text) not in handled
    )
    if remaining:
        add(
            "analysis.warning",
            HealthStatus.WARNING,
            _("Additional analysis warnings"),
            _(
                "The analyzer reported additional limitations. They remain warnings even when no specific health diagnosis recognises them."
            ),
            remaining,
            _(
                "Review the reported evidence, correct the indicated setup or analysis settings, and repeat the measurement when the warning concerns the take."
            ),
        )

    findings.sort(key=lambda finding: _PRIORITY[finding.severity])
    status = findings[0].severity if findings else HealthStatus.GOOD
    return MeasurementHealth(status, tuple(findings))
