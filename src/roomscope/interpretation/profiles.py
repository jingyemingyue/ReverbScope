"""Recording profiles.

A profile converts measurements into advice for a kind of recording. The
interface is fixed in v0.1 so that vocal / voice-over / acoustic guitar /
drums / room-mic / choir profiles can be added without touching the DSP.

The DSP layer never writes advice; a profile only reads an
:class:`AnalysisResult` and returns :class:`Finding` objects with the
measured values in ``evidence``. Thresholds are coarse engineering choices,
documented in MEASUREMENT_METHODOLOGY.md §8, and are stated in each finding's
evidence.
"""

from __future__ import annotations

import math
from typing import Protocol, runtime_checkable

from roomscope.i18n import _, current_locale, diag, localize, pgettext
from roomscope.interpretation.interpreter import Finding, Severity, finding
from roomscope.models.comparison import (
    REFUSAL_NOTE_PREFIXES,
    T_JND_PERCENT,
    ComparisonResult,
    MetricDelta,
    ReflectionMatch,
)
from roomscope.models.result import (
    KIND_SAMPLE_RATE,
    KIND_TIME_STRETCH,
    AnalysisResult,
    Reflection,
    ResonanceCandidate,
    Validity,
)


def decay_length_text(label: str) -> str:
    """Translated word for a decay label (``"short"``, ``"noticeable"``, ``"long"``).

    Findings keep the English label in ``params``; only the sentence shows the
    translated word.
    """
    words = {
        "short": pgettext("decay length", "short"),
        "noticeable": pgettext("decay length", "noticeable"),
        "long": pgettext("decay length", "long"),
    }
    return words.get(label, label)


def confidence_text(confidence: str) -> str:
    """Translated direct-sound confidence (``"high"``, ``"medium"``, ``"low"``)."""
    words = {"high": _("high"), "medium": _("medium"), "low": _("low")}
    return words.get(confidence, confidence)


def band_text(label: str) -> str:
    """Translated band label: the broadband row has a name, octave bands are numbers."""
    return _("Broadband") if label == "broadband" else label


def profile_title(name: str) -> str:
    """Translated display name of a profile.

    Files, JSON and the command line keep the profile id (``--profile room_mic``).
    """
    titles = {
        "generic": _("General"),
        "vocal": _("Vocals"),
        "voiceover": _("Voice-over"),
        "acoustic_guitar": _("Acoustic guitar"),
        "drums": _("Drums"),
        "room_mic": _("Room microphone"),
        "choir": _("Choir / ensemble"),
    }
    return titles.get(name, name)


def change_direction_text(direction: str) -> str:
    """Translated word for the direction of an RT60 change (``"shorter"`` / ``"longer"``)."""
    words = {
        "shorter": pgettext("RT60 change", "shorter"),
        "longer": pgettext("RT60 change", "longer"),
    }
    return words.get(direction, direction)


def noise_segment_text(source: str | None) -> str:
    """Translated name of the quiet segment the noise was measured in."""
    words = {
        "pre-sweep": pgettext("noise segment", "pre-sweep"),
        "tail": pgettext("noise segment", "tail"),
        "quiet": pgettext("noise segment", "quiet"),
    }
    return words.get(source or "quiet", source or "quiet")


def _db_or_floor(value: float | None) -> float:
    """A level for ranking; ``or -99.0`` would rank a 0.0 dB reflection last."""
    return value if value is not None else -99.0


def _complete(match: ReflectionMatch) -> bool:
    """Both delays and both levels of a pair (a lenient load can lack one)."""
    return None not in (
        match.baseline_delay_ms,
        match.candidate_delay_ms,
        match.baseline_relative_db,
        match.candidate_relative_db,
    )


def _refusal_note(notes: tuple[str, ...]) -> str:
    """The note that says why a pair cannot be compared.

    A comparison saved by 0.5.0b1 or earlier lists the reason after the sweep
    and ISO notes, so it is looked up rather than taken as the first note.
    """
    reason = next((note for note in notes if note.startswith(REFUSAL_NOTE_PREFIXES)), None)
    if reason is not None:
        return reason
    return notes[0] if notes else diag("no common excitation band")


def _direct_level_dbfs(result: AnalysisResult, peak_db: float) -> float | None:
    """Level of the direct sound in the recording (dBFS, like the noise floor).

    The analysis stores it from the response before any loopback compensation
    (a compensated IR peak also carries the inverse of the return gain). A
    file without it (0.5.0b1 and earlier) falls back to the IR peak, which is
    the chain gain alone, plus the level the sweep was played at; that level
    is unknown for an analysis against a reference WAV.
    """
    stored = result.impulse_response.direct_level_dbfs
    if stored is not None and math.isfinite(stored):
        return stored
    level = result.sweep_settings.get("level_dbfs")
    # Only a level a sweep accepts: float() of a 400-digit integer in a
    # crafted file raises OverflowError.
    if isinstance(level, int | float) and not isinstance(level, bool) and -80.0 <= level <= 0.0:
        return peak_db + float(level)
    return None


@runtime_checkable
class RecordingProfile(Protocol):
    name: str
    description: str

    def interpret(self, result: AnalysisResult) -> list[Finding]: ...

    def interpret_comparison(self, comparison: ComparisonResult) -> list[Finding]: ...


class ProfileBase:
    """Shared interpretation machinery.

    Measurement-integrity checks (direct-sound confidence, clipping,
    insufficient decay range) are identical for every profile and live here.
    The profile sections — reflections, decay, clarity, noise, resonances — use
    class-level thresholds plus per-profile message methods, so each profile
    keeps its own wording while sharing the surrounding logic.
    """

    name: str
    description: str

    #: Strongest reflection level (dB re direct sound) that counts as strong.
    strong_reflection_db = -10.0
    #: Reflections at or below this delay (ms) are the ones that colour a close-miked source.
    strong_reflection_window_ms = 30.0
    #: RT60 above which the decay is called "noticeable" for this kind of recording.
    long_decay_s = 0.6
    #: RT60 above which the decay is called "long" (a warning).
    very_long_decay_s = 1.0
    #: Dynamic range below the direct sound at which noise starts to matter.
    quiet_noise_margin_db = 60.0
    #: Low bands decaying more than this many times slower than mid bands is an imbalance.
    slow_low_ratio = 1.5
    #: Bands at or below this centre frequency count as "low".
    low_band_max_hz = 250.0
    #: Bands between these centre frequencies count as "mid".
    mid_band_min_hz = 500.0
    mid_band_max_hz = 2000.0
    #: Early/late ratio this profile comments on (``"c50"`` for speech, ``"c80"``
    #: for music). ``None`` means the profile does not judge clarity.
    clarity_metric: str | None = "c50"
    #: Notice when that ratio (dB) is below this. ``None`` does not flag a low ratio.
    clarity_low_db: float | None = 0.0
    #: Notice when that ratio (dB) is above this (the room is too dry for the use).
    clarity_high_db: float | None = None

    def interpret(self, result: AnalysisResult) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._data_quality(result))
        findings.extend(self._reflections(result))
        findings.extend(self._decay(result))
        findings.extend(self._clarity(result))
        findings.extend(self._noise(result))
        findings.extend(self._resonances(result))
        return findings

    def interpret_comparison(self, comparison: ComparisonResult) -> list[Finding]:
        """Judge a comparison with this profile's own thresholds.

        Invalid deltas are never quoted as numbers. A change is never called
        significant; the ISO 3382-1 JND for T is quoted as context only.
        """
        findings: list[Finding] = []
        if not comparison.comparable:
            notes = _refusal_note(comparison.notes)
            findings.append(
                finding(
                    "comparison",
                    Severity.WARNING,
                    "comparison.not_comparable",
                    "These two sessions cannot be compared: {notes}",
                    evidence={"notes": list(comparison.notes)},
                    display={"notes": localize(notes)},
                    notes=notes,
                )
            )
            return findings
        findings.extend(self._comparison_decay(comparison))
        findings.extend(self._comparison_reflections(comparison))
        findings.extend(self._comparison_noise(comparison))
        return findings

    def _comparison_decay(self, comparison: ComparisonResult) -> list[Finding]:
        by_name = {item.name: item for item in comparison.decay}
        findings: list[Finding] = []
        rt = by_name.get("broadband.rt60_estimate")
        if (
            rt is not None
            and rt.validity is Validity.VALID
            and rt.baseline is not None
            and rt.candidate is not None
        ):
            percent = rt.delta_percent if rt.delta_percent is not None else 0.0
            direction = "shorter" if rt.candidate < rt.baseline else "longer"
            findings.append(
                finding(
                    "reverberation",
                    Severity.NOTICE if abs(percent) >= T_JND_PERCENT else Severity.INFO,
                    "comparison.decay_rt60",
                    "Broadband estimated RT60 went from {baseline_s:.2f} s to "
                    "{candidate_s:.2f} s ({delta_percent:+.1f} % of the baseline, {direction}). "
                    "ISO 3382-1 quotes a just-noticeable difference for T of about "
                    "{jnd_percent:g} %; a single pair of positions is not enough to call "
                    "the change significant.",
                    evidence={
                        "baseline_s": rt.baseline,
                        "candidate_s": rt.candidate,
                        "delta_percent": percent,
                        "jnd_percent": T_JND_PERCENT,
                    },
                    display={"direction": change_direction_text(direction)},
                    baseline_s=rt.baseline,
                    candidate_s=rt.candidate,
                    delta_percent=round(percent, 1) + 0.0,  # never "-0.0 %"
                    direction=direction,
                    jnd_percent=T_JND_PERCENT,
                )
            )
            crossed = self._decay_threshold_crossing(rt)
            if crossed:
                findings.append(crossed)
        return findings

    def _decay_threshold_crossing(self, rt: MetricDelta) -> Finding | None:
        if rt.baseline is None or rt.candidate is None:
            return None
        before = self._decay_label(rt.baseline)
        after = self._decay_label(rt.candidate)
        if before == after:
            return None
        return finding(
            "reverberation",
            Severity.NOTICE,
            "comparison.decay_threshold",
            "Against this profile's decay thresholds the broadband RT60 moved from "
            "'{before}' ({baseline_s:.2f} s) to '{after}' ({candidate_s:.2f} s).",
            evidence={
                "baseline_s": rt.baseline,
                "candidate_s": rt.candidate,
                "long_decay_s": self.long_decay_s,
                "very_long_decay_s": self.very_long_decay_s,
            },
            display={"before": decay_length_text(before), "after": decay_length_text(after)},
            before=before,
            after=after,
            baseline_s=rt.baseline,
            candidate_s=rt.candidate,
        )

    def _decay_label(self, rt: float) -> str:
        if rt >= self.very_long_decay_s:
            return "long"
        if rt >= self.long_decay_s:
            return "noticeable"
        return "short"

    def _comparison_reflections(self, comparison: ComparisonResult) -> list[Finding]:
        # The strongest reflection inside the window on each side, matched or
        # not: moving the microphone often shifts a reflection by more than the
        # match tolerance, so a dominant one that disappeared (or a strong new
        # one) must not hide behind a weaker matched pair.
        window = self.strong_reflection_window_ms
        usable = [m for m in comparison.reflections if m.status != "matched" or _complete(m)]
        before = [
            m
            for m in usable
            if m.status in ("matched", "disappeared")
            and m.baseline_delay_ms is not None
            and m.baseline_delay_ms <= window
            and m.baseline_relative_db is not None
        ]
        after = [
            m
            for m in usable
            if m.status in ("matched", "appeared")
            and m.candidate_delay_ms is not None
            and m.candidate_delay_ms <= window
            and m.candidate_relative_db is not None
        ]
        baseline = max(before, key=lambda m: _db_or_floor(m.baseline_relative_db), default=None)
        candidate = max(after, key=lambda m: _db_or_floor(m.candidate_relative_db), default=None)
        if baseline is not None and candidate is not None:
            return [
                finding(
                    "early_reflections",
                    Severity.NOTICE,
                    "comparison.reflection_change",
                    "The strongest reflection within {window_ms:g} ms "
                    "went from {baseline_relative_db:.1f} dB at "
                    "{baseline_delay_ms:.1f} ms to "
                    "{candidate_relative_db:.1f} dB at "
                    "{candidate_delay_ms:.1f} ms "
                    "(threshold {threshold_db:.1f} dB for this profile).",
                    evidence={
                        "baseline_delay_ms": baseline.baseline_delay_ms,
                        "candidate_delay_ms": candidate.candidate_delay_ms,
                        "baseline_relative_db": baseline.baseline_relative_db,
                        "candidate_relative_db": candidate.candidate_relative_db,
                        "threshold_db": self.strong_reflection_db,
                        "window_ms": window,
                    },
                    window_ms=window,
                    baseline_relative_db=baseline.baseline_relative_db,
                    baseline_delay_ms=baseline.baseline_delay_ms,
                    candidate_relative_db=candidate.candidate_relative_db,
                    candidate_delay_ms=candidate.candidate_delay_ms,
                    threshold_db=self.strong_reflection_db,
                )
            ]
        if (
            candidate is not None
            and candidate.candidate_relative_db is not None
            and candidate.candidate_relative_db >= self.strong_reflection_db
        ):
            return [
                finding(
                    "early_reflections",
                    Severity.NOTICE,
                    "comparison.reflection_appeared",
                    "A reflection appeared at {delay_ms:.1f} ms "
                    "({relative_db:.1f} dB) inside this profile's "
                    "{window_ms:g} ms window.",
                    evidence={
                        "delay_ms": candidate.candidate_delay_ms,
                        "relative_db": candidate.candidate_relative_db,
                        "window_ms": window,
                    },
                    delay_ms=candidate.candidate_delay_ms,
                    relative_db=candidate.candidate_relative_db,
                    window_ms=window,
                )
            ]
        if (
            baseline is not None
            and baseline.baseline_relative_db is not None
            and baseline.baseline_relative_db >= self.strong_reflection_db
        ):
            return [
                finding(
                    "early_reflections",
                    Severity.NOTICE,
                    "comparison.reflection_disappeared",
                    "No reflection was detected inside this profile's {window_ms:g} ms "
                    "window in the candidate; the strongest in the baseline was "
                    "{relative_db:.1f} dB at {delay_ms:.1f} ms.",
                    evidence={
                        "delay_ms": baseline.baseline_delay_ms,
                        "relative_db": baseline.baseline_relative_db,
                        "threshold_db": self.strong_reflection_db,
                        "window_ms": window,
                    },
                    delay_ms=baseline.baseline_delay_ms,
                    relative_db=baseline.baseline_relative_db,
                    window_ms=window,
                )
            ]
        return []

    def _comparison_noise(self, comparison: ComparisonResult) -> list[Finding]:
        rms = next((item for item in comparison.noise if item.name == "noise.rms_dbfs"), None)
        if rms is None or rms.validity is not Validity.VALID:
            return []
        if rms.baseline is None or rms.candidate is None or rms.delta is None:
            return []
        return [
            finding(
                "noise",
                Severity.INFO,
                "comparison.noise_rms",
                "Background noise went from {baseline_dbfs:.1f} dBFS to "
                "{candidate_dbfs:.1f} dBFS ({delta_db:+.1f} dB) at the declared-equal input gain.",
                evidence={
                    "baseline_dbfs": rms.baseline,
                    "candidate_dbfs": rms.candidate,
                    "delta_db": rms.delta,
                },
                baseline_dbfs=rms.baseline,
                candidate_dbfs=rms.candidate,
                delta_db=round(rms.delta, 1) + 0.0,  # never "-0.0 dB"
            )
        ]

    # ------------------------------------------------------------- helpers

    def _strong_reflections(self, result: AnalysisResult) -> list[Reflection]:
        return [
            r
            for r in result.reflections.reflections
            if r.relative_db >= self.strong_reflection_db
            and r.delay_ms <= self.strong_reflection_window_ms
        ]

    def _distinguishable_resonances(self, result: AnalysisResult) -> list[ResonanceCandidate]:
        return [c for c in result.resonances.candidates if c.decay_distinguishable]

    def _low_mid_imbalance(self, result: AnalysisResult) -> tuple[float, float] | None:
        """(low max RT60, mid mean RT60) when low bands clearly outlast mid bands."""
        low_bands = [
            b
            for b in result.decay.bands
            if b.center_hz is not None and b.center_hz <= self.low_band_max_hz
        ]
        mid_bands = [
            b
            for b in result.decay.bands
            if b.center_hz is not None
            and self.mid_band_min_hz <= b.center_hz <= self.mid_band_max_hz
        ]
        low = [b.rt60_estimate_s for b in low_bands if b.rt60_estimate_s is not None]
        mid = [b.rt60_estimate_s for b in mid_bands if b.rt60_estimate_s is not None]
        if not low or not mid:
            return None
        mid_mean = sum(mid) / len(mid)
        if max(low) > self.slow_low_ratio * mid_mean:
            return max(low), mid_mean
        return None

    # ------------------------------------------------ measurement integrity

    def _data_quality(self, result: AnalysisResult) -> list[Finding]:
        findings: list[Finding] = []
        ir = result.impulse_response
        speed = ir.playback_speed
        if speed is not None and speed.kind == KIND_SAMPLE_RATE and speed.played_rate_hz:
            findings.append(
                finding(
                    "measurement",
                    Severity.WARNING,
                    "measurement.playback_sample_rate",
                    "The sweep was generated at {generated_rate_hz} Hz but played at "
                    "{played_rate_hz} Hz: the DAW project runs at another sample rate and did not "
                    "convert the file. Generate the sweep at the project's sample rate, or let the "
                    "DAW convert it on import, and measure again.",
                    evidence=speed.to_dict(),
                    generated_rate_hz=speed.generated_rate_hz,
                    played_rate_hz=speed.played_rate_hz,
                )
            )
        elif speed is not None and speed.kind == KIND_TIME_STRETCH:
            findings.append(
                finding(
                    "measurement",
                    Severity.WARNING,
                    "measurement.playback_time_stretch",
                    "The sweep was played at {speed_percent:.1f} % of its speed: the DAW "
                    "time-stretched it (Warp, Flex Time, Follow Tempo, elastic audio or a stretch "
                    "mode). Switch time-stretching off for the sweep clip and measure again.",
                    evidence=speed.to_dict(),
                    speed_percent=speed.speed_ratio * 100.0,
                )
            )
        elif ir.direct_sound_confidence != "high":
            findings.append(
                finding(
                    "measurement",
                    Severity.WARNING,
                    "measurement.direct_sound",
                    "The direct sound could not be identified with confidence, so delays and "
                    "levels of reflections may be off. Check that the correct reference sweep "
                    "was used, lower the playback level if the loudspeaker distorts, and "
                    "measure again.",
                    evidence={"pre_peak_margin_db": ir.pre_peak_margin_db},
                    pre_peak_margin_db=ir.pre_peak_margin_db,
                )
            )
        noise = result.noise
        if (
            noise is not None
            and noise.rms_dbfs is None
            and any("digital silence (exact zeros)" in note for note in noise.notes)
        ):
            # A microphone always records some noise. Exact zeros where the
            # room should be heard mean a digital source: typically the DAW's
            # test-signal track exported instead of the microphone take, which
            # otherwise analyses as a near-perfect "room" with RT60 ~ 0.
            findings.append(
                finding(
                    "measurement",
                    Severity.WARNING,
                    "measurement.digital_silence",
                    "The recording has no background noise at all: its quiet part is exact "
                    "digital silence, which a microphone never records. Check that you exported "
                    "the microphone track, not the test-signal track, and that no gate or noise "
                    "reduction is on the microphone track. The room figures are not reliable "
                    "until then.",
                    evidence={"notes": list(noise.notes)},
                )
            )
        for warning in result.warnings:
            if "buffer problem" in warning:
                findings.append(
                    finding(
                        "measurement",
                        Severity.WARNING,
                        "measurement.dropouts",
                        "The audio device reported dropped or late buffers during the take, so "
                        "samples may be missing and the result may be smeared. Close other audio "
                        "programs, choose a higher latency or buffer size, and measure again.",
                        evidence={"warning": warning},
                        warning=warning,
                    )
                )
            if "clipping" in warning:
                findings.append(
                    finding(
                        "measurement",
                        Severity.WARNING,
                        "measurement.clipping",
                        "The recording clips. Lower the playback or input gain and measure again.",
                        evidence={"warning": warning},
                        warning=warning,
                    )
                )
        broadband = result.decay.broadband
        if broadband.t20.validity is Validity.INSUFFICIENT_RANGE:
            findings.append(
                finding(
                    "measurement",
                    Severity.NOTICE,
                    "measurement.insufficient_range",
                    "The decay range is too small for a reliable reverberation time. A longer "
                    "sweep, a slightly higher playback level or a quieter room increases it.",
                    evidence={
                        "peak_to_noise_db": broadband.peak_to_noise_db,
                        "reason": broadband.t20.reason,
                    },
                    peak_to_noise_db=broadband.peak_to_noise_db,
                )
            )
        return findings

    # ------------------------------------------------------------ sections

    def _reflections(self, result: AnalysisResult) -> list[Finding]:
        strong = self._strong_reflections(result)
        if not strong:
            return []
        first = max(strong, key=lambda r: r.relative_db)
        return [
            Finding(
                topic="early_reflections",
                severity=Severity.NOTICE,
                message=self.reflection_message(first),
                evidence={
                    "delay_ms": first.delay_ms,
                    "relative_db": first.relative_db,
                    "count_within_window": len(strong),
                },
                message_id="reflection.strong_close",
                params={"delay_ms": first.delay_ms, "relative_db": first.relative_db},
                locale=current_locale(),
            )
        ]

    def _decay(self, result: AnalysisResult) -> list[Finding]:
        findings: list[Finding] = []
        broadband = result.decay.broadband
        rt = broadband.rt60_estimate_s
        if rt is not None:
            if rt >= self.very_long_decay_s:
                severity, text = Severity.WARNING, "long"
            elif rt >= self.long_decay_s:
                severity, text = Severity.NOTICE, "noticeable"
            else:
                severity, text = Severity.INFO, "short"
            findings.append(
                Finding(
                    topic="reverberation",
                    severity=severity,
                    # ``text`` is shown translated; ``params["label"]`` keeps the English label.
                    message=self.decay_message(
                        rt, severity, decay_length_text(text), broadband.rt60_basis
                    ),
                    evidence={"rt60_estimate_s": rt, "basis": broadband.rt60_basis},
                    message_id="reverberation.rt60",
                    params={"rt60_s": rt, "label": text, "basis": broadband.rt60_basis},
                    locale=current_locale(),
                )
            )
        imbalance = self._low_mid_imbalance(result)
        if imbalance is not None:
            low_max, mid_mean = imbalance
            findings.append(
                Finding(
                    topic="reverberation",
                    severity=Severity.NOTICE,
                    message=self.low_imbalance_message(low_max, mid_mean),
                    evidence={"low_max_rt60_s": low_max, "mid_mean_rt60_s": mid_mean},
                    message_id="reverberation.low_imbalance",
                    params={"low_max_rt60_s": low_max, "mid_mean_rt60_s": mid_mean},
                    locale=current_locale(),
                )
            )
        return findings

    def _clarity(self, result: AnalysisResult) -> list[Finding]:
        """One notice when early/late energy is a poor fit for this recording.

        Only a VALID ratio is quoted. The threshold is an engineering choice
        for the recording, stated in the evidence, not a room grade and not
        an ISO limit.
        """
        name = self.clarity_metric
        if name not in ("c50", "c80"):
            return []
        metric = getattr(result.decay.broadband, name)
        if metric.validity is not Validity.VALID or metric.value is None:
            return []
        value = float(metric.value)
        if self.clarity_low_db is not None and value < self.clarity_low_db:
            return [
                Finding(
                    topic="clarity",
                    severity=Severity.NOTICE,
                    message=self.clarity_low_message(value, self.clarity_low_db),
                    evidence={
                        "metric": name,
                        "value_db": value,
                        "threshold_db": self.clarity_low_db,
                        "side": "low",
                    },
                    message_id="clarity.low",
                    params={
                        "metric": name,
                        "value_db": value,
                        "threshold_db": self.clarity_low_db,
                    },
                    locale=current_locale(),
                )
            ]
        if self.clarity_high_db is not None and value > self.clarity_high_db:
            return [
                Finding(
                    topic="clarity",
                    severity=Severity.NOTICE,
                    message=self.clarity_high_message(value, self.clarity_high_db),
                    evidence={
                        "metric": name,
                        "value_db": value,
                        "threshold_db": self.clarity_high_db,
                        "side": "high",
                    },
                    message_id="clarity.high",
                    params={
                        "metric": name,
                        "value_db": value,
                        "threshold_db": self.clarity_high_db,
                    },
                    locale=current_locale(),
                )
            ]
        return []

    def _noise(self, result: AnalysisResult) -> list[Finding]:
        findings: list[Finding] = []
        noise = result.noise
        for hum in noise.hum:
            if hum.detected:
                findings.append(
                    Finding(
                        topic="noise",
                        severity=Severity.WARNING,
                        message=self.hum_message(hum.base_hz),
                        evidence={
                            "base_hz": hum.base_hz,
                            "harmonics": [list(h) for h in hum.harmonics],
                        },
                        message_id="noise.hum",
                        params={"base_hz": hum.base_hz},
                        locale=current_locale(),
                    )
                )
        if noise.rms_dbfs is not None:
            peak_db = 20.0 * math.log10(max(abs(result.impulse_response.peak_value), 1e-12))
            direct_dbfs = _direct_level_dbfs(result, peak_db)
            findings.append(
                Finding(
                    topic="noise",
                    severity=Severity.INFO,
                    message=self.noise_floor_message(
                        noise.rms_dbfs, noise_segment_text(noise.segment_source)
                    ),
                    evidence={
                        "rms_dbfs": noise.rms_dbfs,
                        "segment_source": noise.segment_source,
                        "ir_peak_db": peak_db,
                    },
                    message_id="noise.floor",
                    params={"rms_dbfs": noise.rms_dbfs, "segment": noise.segment_source},
                    locale=current_locale(),
                )
            )
            if (
                direct_dbfs is not None
                and direct_dbfs - noise.rms_dbfs < self.quiet_noise_margin_db
            ):
                margin = direct_dbfs - noise.rms_dbfs
                findings.append(
                    finding(
                        "noise",
                        Severity.NOTICE,
                        "noise.direct_to_noise",
                        "The direct sound is only {direct_to_noise_db:.0f} dB above the "
                        "noise floor in the quiet segment. Sources quieter than this will be "
                        "recorded with audible noise; lower the noise at the source or increase "
                        "the playback level within the headroom of the chain.",
                        evidence={"direct_to_noise_db": margin},
                        direct_to_noise_db=margin,
                    )
                )
        return findings

    def _resonances(self, result: AnalysisResult) -> list[Finding]:
        candidates = self._distinguishable_resonances(result)
        if not candidates:
            return []
        return [
            Finding(
                topic="low_frequency",
                severity=Severity.NOTICE,
                message=self.resonance_message(candidates),
                evidence={"candidates": [c.to_dict() for c in candidates]},
                message_id="low_frequency.resonance",
                params={"listed": ", ".join(f"{c.frequency_hz:.0f} Hz" for c in candidates[:4])},
                locale=current_locale(),
            )
        ]

    # ------------------------------------------------------------ messages
    #
    # ``decay_message`` receives ``text`` and ``noise_floor_message`` receives
    # ``segment_source`` already translated (``decay_length_text`` /
    # ``noise_segment_text``); a profile only inserts them into its sentence.

    def reflection_message(self, r: Reflection) -> str:
        return _(
            "A relatively strong early reflection is present approximately "
            "{delay_ms:.0f} ms after the direct sound ({relative_db:.1f} dB). "
            "For close vocal or instrument recording, try moving the microphone or the "
            "performer farther from nearby hard surfaces, or treat that surface, and "
            "measure again."
        ).format(delay_ms=r.delay_ms, relative_db=r.relative_db)

    def decay_message(self, rt: float, severity: Severity, text: str, basis: str | None) -> str:
        if severity is Severity.INFO:
            if basis:
                return _(
                    "The broadband decay is short (estimated RT60 {rt:.2f} s from {basis}). "
                    "This is typical of a treated or small, well-damped room."
                ).format(rt=rt, basis=basis)
            return _(
                "The broadband decay is short (estimated RT60 {rt:.2f} s). "
                "This is typical of a treated or small, well-damped room."
            ).format(rt=rt)
        if basis:
            return _(
                "The broadband decay is {text} (estimated RT60 {rt:.2f} s from {basis}). "
                "Dry close-miked recordings will pick up audible room sound; consider "
                "absorption or a closer microphone position."
            ).format(text=text, rt=rt, basis=basis)
        return _(
            "The broadband decay is {text} (estimated RT60 {rt:.2f} s). "
            "Dry close-miked recordings will pick up audible room sound; consider "
            "absorption or a closer microphone position."
        ).format(text=text, rt=rt)

    def low_imbalance_message(self, low_max: float, mid_mean: float) -> str:
        return _(
            "Low frequencies decay clearly more slowly than the mid range "
            "({low_max:.2f} s vs {mid_mean:.2f} s), which usually makes bass-heavy sources "
            "sound boomy at this position. Bass trapping or a different position helps."
        ).format(low_max=low_max, mid_mean=mid_mean)

    def hum_message(self, base_hz: float) -> str:
        return _(
            "Mains hum components at multiples of {base_hz:.0f} Hz were detected in "
            "the quiet part of the recording. Check grounding, cables, dimmers and "
            "power supplies before treating the room."
        ).format(base_hz=base_hz)

    def noise_floor_message(self, rms_dbfs: float, segment_source: str | None) -> str:
        segment = segment_source or "quiet"
        return _(
            "Background noise in the {segment} segment is {rms_dbfs:.1f} dBFS RMS "
            "(uncalibrated digital level, not dB SPL). Compare it with the level of the "
            "sources you record at the same gain."
        ).format(segment=segment, rms_dbfs=rms_dbfs)

    def resonance_message(self, candidates: list[ResonanceCandidate]) -> str:
        listed = ", ".join(f"{c.frequency_hz:.0f} Hz" for c in candidates[:4])
        return _(
            "Potential low-frequency resonances around {listed}: these frequencies stand out "
            "in the response and ring longer than their surroundings. Measure one or two other "
            "positions to see whether they follow the room or the position."
        ).format(listed=listed)

    def clarity_low_message(self, value_db: float, threshold_db: float) -> str:
        return _(
            "Early sound is not clearly ahead of the later room sound "
            "(C50 {value:.1f} dB, below {threshold:.0f} dB). For close-miked recording "
            "this can blur the source; move the microphone closer or add absorption, "
            "then measure again. This is one position, not a room grade."
        ).format(value=value_db, threshold=threshold_db)

    def clarity_high_message(self, value_db: float, threshold_db: float) -> str:
        return _(
            "Late room sound is weak (C80 {value:.1f} dB, above {threshold:.0f} dB). "
            "This is one position, not a room grade."
        ).format(value=value_db, threshold=threshold_db)


class GenericProfile(ProfileBase):
    """Profile-independent observations that apply to any close-miked recording."""

    name = "generic"
    description = "General observations, not tied to a specific instrument or voice."


class VocalProfile(ProfileBase):
    """Close-miked lead or backing vocals."""

    name = "vocal"
    description = "Close-miked lead or backing vocals."

    strong_reflection_db = -12.0
    strong_reflection_window_ms = 25.0
    long_decay_s = 0.5
    very_long_decay_s = 0.8
    clarity_low_db = 2.0

    def reflection_message(self, r: Reflection) -> str:
        return _(
            "A strong early reflection is present approximately {delay_ms:.0f} ms after the "
            "direct sound ({relative_db:.1f} dB). Close-miked vocals are coloured by "
            "reflections this early; move the microphone closer to the singer and farther from "
            "the nearest hard surface, or treat that surface, then measure again."
        ).format(delay_ms=r.delay_ms, relative_db=r.relative_db)

    def decay_message(self, rt: float, severity: Severity, text: str, basis: str | None) -> str:
        if severity is Severity.INFO:
            if basis:
                return _(
                    "The broadband decay is short (estimated RT60 {rt:.2f} s from {basis}). "
                    "A dry room like this suits close vocal recording."
                ).format(rt=rt, basis=basis)
            return _(
                "The broadband decay is short (estimated RT60 {rt:.2f} s). "
                "A dry room like this suits close vocal recording."
            ).format(rt=rt)
        if basis:
            return _(
                "The broadband decay is {text} (estimated RT60 {rt:.2f} s from {basis}). "
                "A vocal that is this live picks up room colour between phrases; add absorption "
                "or move to a drier position."
            ).format(text=text, rt=rt, basis=basis)
        return _(
            "The broadband decay is {text} (estimated RT60 {rt:.2f} s). "
            "A vocal that is this live picks up room colour between phrases; add absorption "
            "or move to a drier position."
        ).format(text=text, rt=rt)

    def low_imbalance_message(self, low_max: float, mid_mean: float) -> str:
        return _(
            "Low frequencies decay more slowly than the mid range "
            "({low_max:.2f} s vs {mid_mean:.2f} s), which makes vocals sound boxy at this "
            "position. Bass trapping or a different position helps."
        ).format(low_max=low_max, mid_mean=mid_mean)

    def noise_floor_message(self, rms_dbfs: float, segment_source: str | None) -> str:
        segment = segment_source or "quiet"
        return _(
            "Background noise in the {segment} segment is {rms_dbfs:.1f} dBFS RMS "
            "(uncalibrated digital level, not dB SPL). Vocal tracks are often compressed, "
            "which brings this noise up; compare it with your chain's noise at the same gain."
        ).format(segment=segment, rms_dbfs=rms_dbfs)

    def clarity_low_message(self, value_db: float, threshold_db: float) -> str:
        return _(
            "Speech clarity is low for close vocals (C50 {value:.1f} dB, below "
            "{threshold:.0f} dB). Diction may blur between words; move the microphone "
            "closer or add absorption. This is one position, not a room grade."
        ).format(value=value_db, threshold=threshold_db)


class VoiceOverProfile(ProfileBase):
    """Voice-over, narration and audiobook."""

    name = "voiceover"
    description = "Voice-over, narration and audiobook."

    strong_reflection_db = -14.0
    strong_reflection_window_ms = 20.0
    long_decay_s = 0.4
    very_long_decay_s = 0.7
    clarity_low_db = 4.0

    def reflection_message(self, r: Reflection) -> str:
        return _(
            "An early reflection is present approximately {delay_ms:.0f} ms after the direct "
            "sound ({relative_db:.1f} dB). Voice-over is usually close-miked and heavily "
            "processed, so even a reflection this weak colours the voice; move the microphone "
            "closer to the talent and farther from the nearest hard surface, or treat the surface."
        ).format(delay_ms=r.delay_ms, relative_db=r.relative_db)

    def decay_message(self, rt: float, severity: Severity, text: str, basis: str | None) -> str:
        if severity is Severity.INFO:
            if basis:
                return _(
                    "The broadband decay is short (estimated RT60 {rt:.2f} s from {basis}). "
                    "This suits voice-over: the narration stays dry and close."
                ).format(rt=rt, basis=basis)
            return _(
                "The broadband decay is short (estimated RT60 {rt:.2f} s). "
                "This suits voice-over: the narration stays dry and close."
            ).format(rt=rt)
        if basis:
            return _(
                "The broadband decay is {text} (estimated RT60 {rt:.2f} s from {basis}). "
                "Voice-over needs a dry room; room tone of this length will sit under the "
                "narration. Add absorption or move to a drier position."
            ).format(text=text, rt=rt, basis=basis)
        return _(
            "The broadband decay is {text} (estimated RT60 {rt:.2f} s). "
            "Voice-over needs a dry room; room tone of this length will sit under the "
            "narration. Add absorption or move to a drier position."
        ).format(text=text, rt=rt)

    def low_imbalance_message(self, low_max: float, mid_mean: float) -> str:
        return _(
            "Low frequencies decay more slowly than the mid range "
            "({low_max:.2f} s vs {mid_mean:.2f} s), which makes voice-over sound muddy. "
            "Bass trapping or a different position helps."
        ).format(low_max=low_max, mid_mean=mid_mean)

    def noise_floor_message(self, rms_dbfs: float, segment_source: str | None) -> str:
        segment = segment_source or "quiet"
        return _(
            "Background noise in the {segment} segment is {rms_dbfs:.1f} dBFS RMS "
            "(uncalibrated digital level, not dB SPL). Voice-over is usually quiet and "
            "close-miked, so this floor will be audible under the narration."
        ).format(segment=segment, rms_dbfs=rms_dbfs)

    def resonance_message(self, candidates: list[ResonanceCandidate]) -> str:
        listed = ", ".join(f"{c.frequency_hz:.0f} Hz" for c in candidates[:4])
        return _(
            "Potential low-frequency resonances around {listed}: these frequencies stand out "
            "in the response and ring longer than their surroundings, which colours voice and "
            "dialogue. Move the microphone or treat the affected corner, then measure again."
        ).format(listed=listed)

    def clarity_low_message(self, value_db: float, threshold_db: float) -> str:
        return _(
            "Speech clarity is low for voice-over (C50 {value:.1f} dB, below "
            "{threshold:.0f} dB). Narration usually wants the first 50 ms to hold more "
            "of the energy; move the microphone closer or add absorption. This is one "
            "position, not a room grade."
        ).format(value=value_db, threshold=threshold_db)


class AcousticGuitarProfile(ProfileBase):
    """Acoustic guitar, single microphone or close pair."""

    name = "acoustic_guitar"
    description = "Acoustic guitar, single microphone or close pair."

    strong_reflection_db = -10.0
    strong_reflection_window_ms = 30.0
    long_decay_s = 0.7
    very_long_decay_s = 1.1
    clarity_metric = "c80"
    clarity_low_db = 0.0

    def reflection_message(self, r: Reflection) -> str:
        return _(
            "A strong early reflection is present approximately {delay_ms:.0f} ms after the "
            "direct sound ({relative_db:.1f} dB). Acoustic guitar is vulnerable to comb "
            "filtering from early reflections; move the microphone or the instrument farther "
            "from the nearest hard surface, or treat it, then measure again."
        ).format(delay_ms=r.delay_ms, relative_db=r.relative_db)

    def decay_message(self, rt: float, severity: Severity, text: str, basis: str | None) -> str:
        if severity is Severity.INFO:
            if basis:
                return _(
                    "The broadband decay is short (estimated RT60 {rt:.2f} s from {basis}). "
                    "Acoustic guitar keeps its transients and body in a room like this."
                ).format(rt=rt, basis=basis)
            return _(
                "The broadband decay is short (estimated RT60 {rt:.2f} s). "
                "Acoustic guitar keeps its transients and body in a room like this."
            ).format(rt=rt)
        if basis:
            return _(
                "The broadband decay is {text} (estimated RT60 {rt:.2f} s from {basis}). "
                "For acoustic guitar, a decay this long clouds transients and adds boom; "
                "a position with absorption behind the performer helps."
            ).format(text=text, rt=rt, basis=basis)
        return _(
            "The broadband decay is {text} (estimated RT60 {rt:.2f} s). "
            "For acoustic guitar, a decay this long clouds transients and adds boom; "
            "a position with absorption behind the performer helps."
        ).format(text=text, rt=rt)

    def low_imbalance_message(self, low_max: float, mid_mean: float) -> str:
        return _(
            "Low frequencies decay more slowly than the mid range "
            "({low_max:.2f} s vs {mid_mean:.2f} s), which makes the guitar sound boomy at "
            "this position. Bass trapping or a different position helps."
        ).format(low_max=low_max, mid_mean=mid_mean)

    def clarity_low_message(self, value_db: float, threshold_db: float) -> str:
        return _(
            "Musical clarity is low for acoustic guitar (C80 {value:.1f} dB, below "
            "{threshold:.0f} dB). The note may sit in the room rather than in the "
            "instrument; move the microphone closer or add absorption. This is one "
            "position, not a room grade."
        ).format(value=value_db, threshold=threshold_db)


class DrumsProfile(ProfileBase):
    """Drums, close mics (kick, snare, toms) with or without overheads."""

    name = "drums"
    description = "Drums, close mics (kick, snare, toms) with or without overheads."

    # Drums are loud and close-miked: only a hard slap is worth reporting.
    strong_reflection_db = -6.0
    strong_reflection_window_ms = 20.0
    long_decay_s = 0.8
    very_long_decay_s = 1.2
    # The kit wants the room; a low clarity ratio is not a defect here.
    clarity_metric = None
    clarity_low_db = None

    def reflection_message(self, r: Reflection) -> str:
        return _(
            "A very strong early reflection is present approximately {delay_ms:.0f} ms after "
            "the direct sound ({relative_db:.1f} dB). Drums mask most reflections, but a slap "
            "this strong will smear transients; move the kit or the overheads, or hang "
            "absorption at the reflection point."
        ).format(delay_ms=r.delay_ms, relative_db=r.relative_db)

    def decay_message(self, rt: float, severity: Severity, text: str, basis: str | None) -> str:
        if severity is Severity.INFO:
            if basis:
                return _(
                    "The broadband decay is short (estimated RT60 {rt:.2f} s from {basis}). "
                    "The kit will stay tight in a room like this."
                ).format(rt=rt, basis=basis)
            return _(
                "The broadband decay is short (estimated RT60 {rt:.2f} s). "
                "The kit will stay tight in a room like this."
            ).format(rt=rt)
        if basis:
            return _(
                "The broadband decay is {text} (estimated RT60 {rt:.2f} s from {basis}). "
                "A room this live rings under the kit; for a tighter drum sound add absorption "
                "or move the kit."
            ).format(text=text, rt=rt, basis=basis)
        return _(
            "The broadband decay is {text} (estimated RT60 {rt:.2f} s). "
            "A room this live rings under the kit; for a tighter drum sound add absorption "
            "or move the kit."
        ).format(text=text, rt=rt)

    def low_imbalance_message(self, low_max: float, mid_mean: float) -> str:
        return _(
            "Low frequencies decay more slowly than the mid range "
            "({low_max:.2f} s vs {mid_mean:.2f} s), so the kick and low toms will boom at "
            "this position. Bass trapping or a different kit position helps."
        ).format(low_max=low_max, mid_mean=mid_mean)

    def _noise(self, _result: AnalysisResult) -> list[Finding]:
        # Drums overwhelm any plausible background noise; a noise finding would be noise.
        return []


class RoomMicProfile(ProfileBase):
    """Room microphone or ambient pickup: the room is the instrument."""

    name = "room_mic"
    description = "Room microphone or ambient pickup: the room is the instrument."

    # The room is what is being recorded; only a hard slap is a defect.
    strong_reflection_db = -5.0
    strong_reflection_window_ms = 40.0
    long_decay_s = 0.9
    very_long_decay_s = 1.4
    # A room microphone wants late energy. Flag a ratio that is too dry, not one that is low.
    clarity_metric = "c80"
    clarity_low_db = None
    clarity_high_db = 8.0

    def reflection_message(self, r: Reflection) -> str:
        return _(
            "A very strong early reflection is present approximately {delay_ms:.0f} ms after "
            "the direct sound ({relative_db:.1f} dB). For a room microphone this is a hard "
            "slap that will sit under everything; reposition the microphone or add absorption "
            "at the reflection point."
        ).format(delay_ms=r.delay_ms, relative_db=r.relative_db)

    def decay_message(self, rt: float, severity: Severity, text: str, basis: str | None) -> str:
        if severity is Severity.INFO:
            if basis:
                return _(
                    "The broadband decay is short (estimated RT60 {rt:.2f} s from {basis}). "
                    "A room microphone in a room this dry records mostly direct sound; if you want "
                    "ambience, the microphone needs to be farther from the source."
                ).format(rt=rt, basis=basis)
            return _(
                "The broadband decay is short (estimated RT60 {rt:.2f} s). "
                "A room microphone in a room this dry records mostly direct sound; if you want "
                "ambience, the microphone needs to be farther from the source."
            ).format(rt=rt)
        if severity is Severity.WARNING:
            if basis:
                return _(
                    "The broadband decay is {text} (estimated RT60 {rt:.2f} s from {basis}). "
                    "For a room microphone this is a long room tone that may swamp the source; "
                    "check whether the ambience stays usable, and consider absorption or a closer "
                    "microphone position."
                ).format(text=text, rt=rt, basis=basis)
            return _(
                "The broadband decay is {text} (estimated RT60 {rt:.2f} s). "
                "For a room microphone this is a long room tone that may swamp the source; "
                "check whether the ambience stays usable, and consider absorption or a closer "
                "microphone position."
            ).format(text=text, rt=rt)
        if basis:
            return _(
                "The broadband decay is {text} (estimated RT60 {rt:.2f} s from {basis}). "
                "For a room microphone this is usable ambience; keep the microphone position and "
                "listen for how it sits under the source."
            ).format(text=text, rt=rt, basis=basis)
        return _(
            "The broadband decay is {text} (estimated RT60 {rt:.2f} s). "
            "For a room microphone this is usable ambience; keep the microphone position and "
            "listen for how it sits under the source."
        ).format(text=text, rt=rt)

    def low_imbalance_message(self, low_max: float, mid_mean: float) -> str:
        return _(
            "Low frequencies decay more slowly than the mid range "
            "({low_max:.2f} s vs {mid_mean:.2f} s), so the room sound will be bass-heavy at "
            "this position. Bass trapping or a different microphone position helps."
        ).format(low_max=low_max, mid_mean=mid_mean)

    def noise_floor_message(self, rms_dbfs: float, segment_source: str | None) -> str:
        segment = segment_source or "quiet"
        return _(
            "Background noise in the {segment} segment is {rms_dbfs:.1f} dBFS RMS "
            "(uncalibrated digital level, not dB SPL). A room microphone captures everything, "
            "so this floor is part of what you record; it is audible whenever the source pauses."
        ).format(segment=segment, rms_dbfs=rms_dbfs)

    def resonance_message(self, candidates: list[ResonanceCandidate]) -> str:
        listed = ", ".join(f"{c.frequency_hz:.0f} Hz" for c in candidates[:4])
        return _(
            "Potential low-frequency resonances around {listed}: these frequencies ring longer "
            "than their surroundings, so the room sound will be uneven there. Measure one or "
            "two other positions to see whether they follow the room."
        ).format(listed=listed)

    def clarity_high_message(self, value_db: float, threshold_db: float) -> str:
        return _(
            "Late room sound is weak for a room microphone (C80 {value:.1f} dB, above "
            "{threshold:.0f} dB). A room microphone usually wants more of the room after "
            "80 ms; move it farther from the source or into a livelier part of the room. "
            "This is one position, not a room grade."
        ).format(value=value_db, threshold=threshold_db)


class ChoirProfile(ProfileBase):
    """Choir or small ensemble, one or more microphones."""

    name = "choir"
    description = "Choir or small ensemble, one or more microphones."

    strong_reflection_db = -12.0
    strong_reflection_window_ms = 30.0
    long_decay_s = 0.8
    very_long_decay_s = 1.3
    clarity_low_db = -2.0

    def reflection_message(self, r: Reflection) -> str:
        return _(
            "An early reflection is present approximately {delay_ms:.0f} ms after the direct "
            "sound ({relative_db:.1f} dB). For an ensemble, early reflections smear diction; "
            "move the microphones away from the nearest hard surface or treat it, and measure "
            "again."
        ).format(delay_ms=r.delay_ms, relative_db=r.relative_db)

    def decay_message(self, rt: float, severity: Severity, text: str, basis: str | None) -> str:
        if severity is Severity.INFO:
            if basis:
                return _(
                    "The broadband decay is short (estimated RT60 {rt:.2f} s from {basis}). "
                    "An ensemble keeps its diction in a room like this."
                ).format(rt=rt, basis=basis)
            return _(
                "The broadband decay is short (estimated RT60 {rt:.2f} s). "
                "An ensemble keeps its diction in a room like this."
            ).format(rt=rt)
        if basis:
            return _(
                "The broadband decay is {text} (estimated RT60 {rt:.2f} s from {basis}). "
                "For a choir, decay this long gives ambience but blurs diction; absorption behind "
                "the ensemble or a different microphone position helps."
            ).format(text=text, rt=rt, basis=basis)
        return _(
            "The broadband decay is {text} (estimated RT60 {rt:.2f} s). "
            "For a choir, decay this long gives ambience but blurs diction; absorption behind "
            "the ensemble or a different microphone position helps."
        ).format(text=text, rt=rt)

    def low_imbalance_message(self, low_max: float, mid_mean: float) -> str:
        return _(
            "Low frequencies decay more slowly than the mid range "
            "({low_max:.2f} s vs {mid_mean:.2f} s), which makes the ensemble bottom-heavy "
            "and muddies diction. Bass trapping or a different position helps."
        ).format(low_max=low_max, mid_mean=mid_mean)

    def clarity_low_message(self, value_db: float, threshold_db: float) -> str:
        return _(
            "Speech clarity is low for an ensemble (C50 {value:.1f} dB, below "
            "{threshold:.0f} dB). Some late sound suits a choir, but this much will blur "
            "diction. This is one position, not a room grade."
        ).format(value=value_db, threshold=threshold_db)


def available_profiles() -> list[str]:
    from roomscope.interpretation.registry import available_profiles as listed

    return listed()


def get_profile(name: str) -> RecordingProfile:
    from roomscope.interpretation.registry import get_profile as fetch

    return fetch(name)
