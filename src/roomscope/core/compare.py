"""Validity-aware comparison of two :class:`AnalysisResult` objects.

Pure: NumPy in, dataclasses out, no I/O, no Qt. A comparison never changes
either result. Every delta carries its own :class:`~roomscope.models.result.Validity`.
"""

from __future__ import annotations

import math

import numpy as np

from roomscope.core.filters import fractional_octave_smooth, iec_band
from roomscope.i18n import diag
from roomscope.labels import VALIDITY_WORDS
from roomscope.models.comparison import (
    T_JND_PERCENT,
    CompareSettings,
    ComparisonResult,
    FrequencyResponseDelta,
    MetricDelta,
    ReflectionMatch,
    ResonanceMatch,
    percent_applies,
)
from roomscope.models.result import (
    EXCITATION_SOURCE_UNKNOWN,
    AnalysisResult,
    BandDecay,
    DecayMetric,
    EnergyMetric,
    FrequencyResponseResult,
    PlacementLength,
    Validity,
)
from roomscope.version import __version__

#: IEC 61260-1 nominal octave centres used for the frequency-response MAD table.
_FR_OCTAVE_HZ: tuple[float, ...] = (
    31.5,
    63.0,
    125.0,
    250.0,
    500.0,
    1000.0,
    2000.0,
    4000.0,
    8000.0,
    16000.0,
)


def _octave_ratio(octaves: float) -> float:
    return float(2.0**octaves)


def _common_band(
    baseline: AnalysisResult, candidate: AnalysisResult
) -> tuple[tuple[float, float] | None, tuple[str, ...]]:
    # Every refusal note here and in compare() starts with one of
    # REFUSAL_NOTE_PREFIXES (models/comparison.py): readers find it by them.
    notes: list[str] = []
    b1 = baseline.excitation_band
    b2 = candidate.excitation_band
    # An imported IR without --band carries a 20 Hz-20 kHz placeholder (source
    # "unknown") that the analysis itself never treats as measured.
    if b1 is None or b2 is None or EXCITATION_SOURCE_UNKNOWN in (b1.source, b2.source):
        return None, (
            diag("one or both results have no excitation band, so they cannot be compared"),
        )
    low = max(b1.low_hz, b2.low_hz)
    high = min(b1.high_hz, b2.high_hz)
    if high <= low:
        return None, (diag("the excitation bands do not overlap"),)
    return (low, high), tuple(notes)


def _sweep_notes(baseline: AnalysisResult, candidate: AnalysisResult) -> list[str]:
    notes: list[str] = []
    if baseline.sample_rate != candidate.sample_rate:
        notes.append(
            diag(
                "sample rates differ ({baseline_rate} Hz vs {candidate_rate} Hz); "
                "comparison is still allowed",
                baseline_rate=baseline.sample_rate,
                candidate_rate=candidate.sample_rate,
            )
        )
    dur_a = baseline.sweep_settings.get("duration_s")
    dur_b = candidate.sweep_settings.get("duration_s")
    if dur_a is not None and dur_b is not None and dur_a != dur_b:
        notes.append(
            diag(
                "sweep durations differ ({baseline_s} s vs {candidate_s} s)",
                baseline_s=dur_a,
                candidate_s=dur_b,
            )
        )
    lvl_a = baseline.sweep_settings.get("level_dbfs")
    lvl_b = candidate.sweep_settings.get("level_dbfs")
    if lvl_a is not None and lvl_b is not None and lvl_a != lvl_b:
        notes.append(
            diag(
                "sweep levels differ ({baseline_dbfs} dBFS vs {candidate_dbfs} dBFS)",
                baseline_dbfs=lvl_a,
                candidate_dbfs=lvl_b,
            )
        )
    return notes


def _delta_from_values(
    name: str,
    baseline: float | None,
    candidate: float | None,
    *,
    unit: str,
    time: bool = False,
    extra_reason: str | None = None,
) -> MetricDelta:
    if baseline is None or candidate is None:
        reason = extra_reason or diag("one or both sides have no number")
        return MetricDelta(
            name=name,
            baseline=baseline,
            candidate=candidate,
            validity=Validity.NOT_COMPARABLE,
            reason=reason,
            unit=unit,
        )
    delta = candidate - baseline
    percent = 100.0 * delta / baseline if percent_applies(unit, baseline) else None
    return MetricDelta(
        name=name,
        baseline=baseline,
        candidate=candidate,
        validity=Validity.VALID,
        reason=None,
        delta_s=delta if time else None,
        delta_percent=percent,
        delta=delta,
        unit=unit,
    )


def _side_reasons(
    baseline: DecayMetric | EnergyMetric | PlacementLength,
    candidate: DecayMetric | EnergyMetric | PlacementLength,
) -> list[str]:
    """Why each side that is not VALID cannot be compared, one sentence per side.

    The validity is written as its word ("insufficient range"), not its id,
    so the stored English reads well and is shown translated.
    """
    reasons: list[str] = []
    if baseline.validity is not Validity.VALID:
        if baseline.reason:
            reasons.append(
                diag(
                    "baseline {validity} ({reason})",
                    validity=VALIDITY_WORDS[baseline.validity],
                    reason=baseline.reason,
                )
            )
        else:
            reasons.append(diag("baseline {validity}", validity=VALIDITY_WORDS[baseline.validity]))
    if candidate.validity is not Validity.VALID:
        if candidate.reason:
            reasons.append(
                diag(
                    "candidate {validity} ({reason})",
                    validity=VALIDITY_WORDS[candidate.validity],
                    reason=candidate.reason,
                )
            )
        else:
            reasons.append(
                diag("candidate {validity}", validity=VALIDITY_WORDS[candidate.validity])
            )
    return reasons


def _decay_metric_delta(name: str, baseline: DecayMetric, candidate: DecayMetric) -> MetricDelta:
    if baseline.validity is Validity.VALID and candidate.validity is Validity.VALID:
        return _delta_from_values(name, baseline.seconds, candidate.seconds, unit="s", time=True)
    reasons = _side_reasons(baseline, candidate)
    return MetricDelta(
        name=name,
        baseline=baseline.seconds,
        candidate=candidate.seconds,
        validity=Validity.NOT_COMPARABLE,
        reason="; ".join(reasons) if reasons else diag("metrics are not both VALID"),
        unit="s",
    )


def _energy_metric_delta(name: str, baseline: EnergyMetric, candidate: EnergyMetric) -> MetricDelta:
    """A clarity, definition or centre-time delta. Valid only when both sides are."""
    if baseline.validity is Validity.VALID and candidate.validity is Validity.VALID:
        return _delta_from_values(
            name,
            baseline.value,
            candidate.value,
            unit=baseline.unit,
            time=baseline.unit == "s",
        )
    reasons = _side_reasons(baseline, candidate)
    return MetricDelta(
        name=name,
        baseline=baseline.value,
        candidate=candidate.value,
        validity=Validity.NOT_COMPARABLE,
        reason="; ".join(reasons) if reasons else diag("metrics are not both VALID"),
        unit=baseline.unit,
    )


def _band_decay_deltas(prefix: str, baseline: BandDecay, candidate: BandDecay) -> list[MetricDelta]:
    return [
        _decay_metric_delta(f"{prefix}.edt", baseline.edt, candidate.edt),
        _decay_metric_delta(f"{prefix}.t20", baseline.t20, candidate.t20),
        _decay_metric_delta(f"{prefix}.t30", baseline.t30, candidate.t30),
        _delta_from_values(
            f"{prefix}.rt60_estimate",
            baseline.rt60_estimate_s,
            candidate.rt60_estimate_s,
            unit="s",
            time=True,
            extra_reason=diag(
                "RT60 estimate missing on one or both sides (never taken from an invalid metric)"
            ),
        )
        if baseline.rt60_estimate_s is not None and candidate.rt60_estimate_s is not None
        else MetricDelta(
            name=f"{prefix}.rt60_estimate",
            baseline=baseline.rt60_estimate_s,
            candidate=candidate.rt60_estimate_s,
            validity=Validity.NOT_COMPARABLE,
            reason=diag(
                "RT60 estimate missing on one or both sides (never taken from an invalid metric)"
            ),
            unit="s",
        ),
    ]


def _compare_decay(baseline: AnalysisResult, candidate: AnalysisResult) -> tuple[MetricDelta, ...]:
    """Broadband and per-band deltas; a band present on one side only is reported
    as ``not_comparable`` whichever side lacks it (#9).

    Early/late energy is compared on the broadband response only. Per-band
    ratios stay in each result; averaging them into this table would mix a
    speech ratio with a band the excitation may barely cover.
    """
    left = baseline.decay.broadband
    right = candidate.decay.broadband
    items = _band_decay_deltas("broadband", left, right)
    items.extend(
        [
            _energy_metric_delta("broadband.c50", left.c50, right.c50),
            _energy_metric_delta("broadband.c80", left.c80, right.c80),
            _energy_metric_delta("broadband.d50", left.d50, right.d50),
            _energy_metric_delta("broadband.centre_time", left.centre_time, right.centre_time),
        ]
    )
    by_label = {band.band_label: band for band in candidate.decay.bands}
    for band in baseline.decay.bands:
        other = by_label.get(band.band_label)
        if other is None:
            items.append(
                MetricDelta(
                    name=f"band.{band.band_label}",
                    baseline=band.rt60_estimate_s,
                    candidate=None,
                    validity=Validity.NOT_COMPARABLE,
                    reason=diag("band missing from the candidate"),
                    unit="s",
                )
            )
            continue
        items.extend(_band_decay_deltas(f"band.{band.band_label}", band, other))
    baseline_labels = {band.band_label for band in baseline.decay.bands}
    for band in candidate.decay.bands:
        if band.band_label in baseline_labels:
            continue
        items.append(
            MetricDelta(
                name=f"band.{band.band_label}",
                baseline=None,
                candidate=band.rt60_estimate_s,
                validity=Validity.NOT_COMPARABLE,
                reason=diag("band missing from the baseline"),
                unit="s",
            )
        )
    return tuple(items)


def _coarser_smoothing(a: int, b: int) -> int:
    if a <= 0:
        return b
    if b <= 0:
        return a
    return min(a, b)


def _curve(fr: FrequencyResponseResult) -> tuple[np.ndarray, np.ndarray] | None:
    """``(frequencies, magnitude_db)`` on the result's native grid.

    DC and non-positive frequencies are dropped (the comparison works in log
    frequency). The raw curve is preferred; the stored smoothed curve is the
    fallback when the raw one is absent.
    """
    freq = np.asarray(fr.frequencies_hz, dtype=np.float64)
    raw = np.asarray(fr.magnitude_db_raw, dtype=np.float64)
    magnitude = raw
    if freq.size < 2 or raw.size != freq.size:
        smoothed = fr.magnitude_db_smoothed
        if smoothed is None or np.asarray(smoothed).size != freq.size or freq.size < 2:
            return None
        magnitude = np.asarray(smoothed, dtype=np.float64)
    keep = freq > 0.0
    if np.count_nonzero(keep) < 2:
        return None
    return freq[keep], magnitude[keep]


def _smoothed_on_grid(
    curve: tuple[np.ndarray, np.ndarray], fraction: int, grid: np.ndarray
) -> np.ndarray:
    """Smooth ``curve`` with ``fraction`` on its native grid, then sample ``grid``.

    A curve that is already the stored smoothed one is smoothed again with the
    comparison fraction, which only widens its window.
    """
    freq, magnitude = curve
    smoothed = fractional_octave_smooth(freq, magnitude, fraction)
    return np.asarray(np.interp(np.log(grid), np.log(freq), smoothed), dtype=np.float64)


def _compare_frequency_response(
    baseline: AnalysisResult,
    candidate: AnalysisResult,
    band: tuple[float, float],
    settings: CompareSettings,
) -> FrequencyResponseDelta | None:
    left = _curve(baseline.frequency_response)
    right = _curve(candidate.frequency_response)
    if left is None or right is None:
        return None
    low, high = band
    n_oct = math.log2(high / low)
    n = max(8, round(n_oct * settings.log_grid_points_per_octave) + 1)
    grid = low * (2.0 ** np.linspace(0.0, n_oct, n))
    fraction = _coarser_smoothing(
        baseline.frequency_response.smoothing_fraction,
        candidate.frequency_response.smoothing_fraction,
    )
    if fraction <= 0:
        # Neither side was smoothed: average over one grid step at least, so a
        # grid point stands for its neighbourhood instead of one raw bin.
        fraction = settings.log_grid_points_per_octave
    # Smooth each curve on its own (dense, linear) grid first and only then
    # sample it on the shared log grid. Interpolating the raw spectrum first
    # would point-sample its comb-filter ripple, which differs from take to
    # take, and the difference would mostly be sampling noise (#9).
    mag_a = _smoothed_on_grid(left, fraction, grid)
    mag_b = _smoothed_on_grid(right, fraction, grid)
    diff = mag_b - mag_a
    mad: list[tuple[str, float]] = []
    for nominal in _FR_OCTAVE_HZ:
        octave = iec_band(nominal, 1)
        mask = (grid >= max(octave.low_hz, low)) & (grid <= min(octave.high_hz, high))
        if not np.any(mask):
            continue
        mad.append((octave.label, float(np.mean(np.abs(diff[mask])))))
    return FrequencyResponseDelta(
        frequencies_hz=np.asarray(grid, dtype=np.float64),
        difference_db=np.asarray(diff, dtype=np.float64),
        band_mad_db=tuple(mad),
        smoothing_fraction=fraction,
        reference=diag(
            "candidate minus baseline (dB) on a shared log grid inside the common excitation band"
        ),
    )


def _match_reflections(
    baseline: AnalysisResult,
    candidate: AnalysisResult,
    settings: CompareSettings,
) -> tuple[tuple[ReflectionMatch, ...], str | None]:
    conf_a = baseline.reflections.direct_sound_confidence
    conf_b = candidate.reflections.direct_sound_confidence
    if conf_a != "high" or conf_b != "high":
        return (), diag(
            "early reflections are not compared unless both sides have high direct-sound "
            "confidence (baseline {baseline_confidence}, candidate {candidate_confidence})",
            baseline_confidence=conf_a,
            candidate_confidence=conf_b,
        )
    left = list(baseline.reflections.reflections)
    right = list(candidate.reflections.reflections)
    used_right: set[int] = set()
    matches: list[ReflectionMatch] = []
    for item in left:
        best_i: int | None = None
        best_d = settings.reflection_match_ms
        for i, other in enumerate(right):
            if i in used_right:
                continue
            d = abs(other.delay_ms - item.delay_ms)
            if d <= best_d:
                best_d = d
                best_i = i
        if best_i is None:
            matches.append(
                ReflectionMatch(
                    status="disappeared",
                    baseline_delay_ms=item.delay_ms,
                    baseline_relative_db=item.relative_db,
                )
            )
            continue
        other = right[best_i]
        used_right.add(best_i)
        matches.append(
            ReflectionMatch(
                status="matched",
                baseline_delay_ms=item.delay_ms,
                candidate_delay_ms=other.delay_ms,
                baseline_relative_db=item.relative_db,
                candidate_relative_db=other.relative_db,
                delay_delta_ms=other.delay_ms - item.delay_ms,
                level_delta_db=other.relative_db - item.relative_db,
            )
        )
    for i, other in enumerate(right):
        if i in used_right:
            continue
        matches.append(
            ReflectionMatch(
                status="appeared",
                candidate_delay_ms=other.delay_ms,
                candidate_relative_db=other.relative_db,
            )
        )
    matches.sort(
        key=lambda m: (
            m.baseline_delay_ms is None,
            m.baseline_delay_ms or m.candidate_delay_ms or 0.0,
        )
    )
    return tuple(matches), None


def _quiet_ok(result: AnalysisResult) -> bool:
    return result.noise.segment_source is not None and result.noise.rms_dbfs is not None


def _compare_noise(
    baseline: AnalysisResult, candidate: AnalysisResult, settings: CompareSettings
) -> tuple[MetricDelta, ...]:
    if not _quiet_ok(baseline) or not _quiet_ok(candidate):
        reason = diag("one or both sessions have no verified quiet segment")
        return (
            MetricDelta(
                name="noise.rms_dbfs",
                baseline=baseline.noise.rms_dbfs,
                candidate=candidate.noise.rms_dbfs,
                validity=Validity.NOT_COMPARABLE,
                reason=reason,
                unit="dBFS",
            ),
        )
    if not settings.same_input_gain:
        reason = diag("gain not declared equal")
        return (
            MetricDelta(
                name="noise.rms_dbfs",
                baseline=baseline.noise.rms_dbfs,
                candidate=candidate.noise.rms_dbfs,
                validity=Validity.UNRELIABLE,
                reason=reason,
                delta=None
                if baseline.noise.rms_dbfs is None or candidate.noise.rms_dbfs is None
                else candidate.noise.rms_dbfs - baseline.noise.rms_dbfs,
                unit="dBFS",
            ),
        )
    items = [
        _delta_from_values(
            "noise.rms_dbfs",
            baseline.noise.rms_dbfs,
            candidate.noise.rms_dbfs,
            unit="dBFS",
        )
    ]
    cand_bands = {float(c): lvl for c, lvl in candidate.noise.band_levels_dbfs}
    for centre, level in baseline.noise.band_levels_dbfs:
        items.append(
            _delta_from_values(
                f"noise.band.{centre:g}Hz",
                level,
                cand_bands.get(float(centre)),
                unit="dBFS",
            )
        )
    return tuple(items)


def _match_resonances(
    baseline: AnalysisResult, candidate: AnalysisResult, settings: CompareSettings
) -> tuple[ResonanceMatch, ...]:
    left = list(baseline.resonances.candidates)
    right = list(candidate.resonances.candidates)
    used: set[int] = set()
    matches: list[ResonanceMatch] = []
    ratio = _octave_ratio(settings.resonance_match_octaves)
    for item in left:
        best_i: int | None = None
        best_r = ratio
        for i, other in enumerate(right):
            if i in used or item.frequency_hz <= 0.0 or other.frequency_hz <= 0.0:
                continue
            r = max(item.frequency_hz / other.frequency_hz, other.frequency_hz / item.frequency_hz)
            if r <= best_r:
                best_r = r
                best_i = i
        if best_i is None:
            matches.append(
                ResonanceMatch(
                    status="disappeared",
                    baseline_hz=item.frequency_hz,
                    baseline_decay_distinguishable=item.decay_distinguishable,
                )
            )
            continue
        other = right[best_i]
        used.add(best_i)
        matches.append(
            ResonanceMatch(
                status="matched",
                baseline_hz=item.frequency_hz,
                candidate_hz=other.frequency_hz,
                baseline_decay_distinguishable=item.decay_distinguishable,
                candidate_decay_distinguishable=other.decay_distinguishable,
            )
        )
    for i, other in enumerate(right):
        if i in used:
            continue
        matches.append(
            ResonanceMatch(
                status="appeared",
                candidate_hz=other.frequency_hz,
                candidate_decay_distinguishable=other.decay_distinguishable,
            )
        )
    return tuple(matches)


def _placement_length_delta(
    name: str, baseline: PlacementLength, candidate: PlacementLength
) -> MetricDelta:
    if baseline.validity is Validity.VALID and candidate.validity is Validity.VALID:
        return _delta_from_values(name, baseline.metres, candidate.metres, unit="m")
    reasons = _side_reasons(baseline, candidate)
    return MetricDelta(
        name=name,
        baseline=baseline.metres,
        candidate=candidate.metres,
        validity=Validity.NOT_COMPARABLE,
        reason="; ".join(reasons) if reasons else diag("placement lengths are not both VALID"),
        unit="m",
    )


def _compare_placement(
    baseline: AnalysisResult, candidate: AnalysisResult
) -> tuple[MetricDelta, ...]:
    a = baseline.placement
    b = candidate.placement
    if a is None or b is None or a.tier < 2 or b.tier < 2:
        reason = diag("placement heights are compared only when both results are tier 2")
        return (
            MetricDelta(
                name="placement.source_height_m",
                baseline=None if a is None else a.source_height_m.metres,
                candidate=None if b is None else b.source_height_m.metres,
                validity=Validity.NOT_COMPARABLE,
                reason=reason,
                unit="m",
            ),
        )
    return (
        _placement_length_delta("placement.source_height_m", a.source_height_m, b.source_height_m),
        _placement_length_delta(
            "placement.ceiling_height_m", a.ceiling_height_m, b.ceiling_height_m
        ),
        _placement_length_delta(
            "placement.horizontal_separation_m",
            a.horizontal_separation_m,
            b.horizontal_separation_m,
        ),
    )


def _compare_loopback(
    baseline: AnalysisResult, candidate: AnalysisResult
) -> tuple[MetricDelta, ...]:
    a = baseline.impulse_response.loopback
    b = candidate.impulse_response.loopback
    if (
        a is None
        or b is None
        or not a.compensation_applied
        or not b.compensation_applied
        or a.path_delay_ms is None
        or b.path_delay_ms is None
    ):
        return (
            MetricDelta(
                name="loopback.path_delay_ms",
                baseline=None if a is None else a.path_delay_ms,
                candidate=None if b is None else b.path_delay_ms,
                validity=Validity.NOT_COMPARABLE,
                reason=diag(
                    "path delay is compared only when both results used a compensated loopback"
                ),
                unit="ms",
            ),
        )
    return (
        _delta_from_values("loopback.path_delay_ms", a.path_delay_ms, b.path_delay_ms, unit="ms"),
    )


def compare(
    baseline: AnalysisResult,
    candidate: AnalysisResult,
    *,
    settings: CompareSettings | None = None,
) -> ComparisonResult:
    """Compare ``candidate`` against ``baseline``. Symmetric in what it refuses."""
    settings = settings or CompareSettings()
    notes: list[str] = []
    notes.extend(_sweep_notes(baseline, candidate))
    # Why the pair is refused, if it is; empty when the bands overlap.
    common, refusal = _common_band(baseline, candidate)
    notes.append(
        diag(
            "ISO 3382-1 quotes a just-noticeable difference for reverberation time of about "
            "{jnd_percent:g} % (clause not verified against the standard text). A change is "
            "not called significant from a single pair of positions.",
            jnd_percent=T_JND_PERCENT,
        )
    )

    comparable = False
    if common is not None:
        low, high = common
        octaves = math.log2(high / low) if low > 0.0 else 0.0
        if octaves + 1e-12 >= settings.min_common_band_octaves:
            comparable = True
        else:
            refusal = (
                diag(
                    "common excitation band {low:g}-{high:g} Hz is {octaves:.2f} octaves, "
                    "narrower than the required {required:g} octave",
                    low=low,
                    high=high,
                    octaves=octaves,
                    required=settings.min_common_band_octaves,
                ),
            )
            common = None

    if not comparable:
        return ComparisonResult(
            comparable=False,
            common_band=common,
            # The reason comes first: it is the note a refusal quotes.
            notes=(*refusal, *notes),
            baseline_created_at=baseline.created_at,
            candidate_created_at=candidate.created_at,
            roomscope_version=__version__,
            settings=settings.to_dict(),
        )

    assert common is not None
    fr_delta = _compare_frequency_response(baseline, candidate, common, settings)
    if fr_delta is None:
        notes.append(
            diag("frequency-response curves are missing on one or both sides (--no-curves)")
        )
    reflections, refl_note = _match_reflections(baseline, candidate, settings)
    if refl_note:
        notes.append(refl_note)
    return ComparisonResult(
        comparable=True,
        common_band=common,
        notes=tuple(notes),
        decay=_compare_decay(baseline, candidate),
        frequency_response=fr_delta,
        reflections=reflections,
        noise=_compare_noise(baseline, candidate, settings),
        resonances=_match_resonances(baseline, candidate, settings),
        placement=_compare_placement(baseline, candidate),
        loopback=_compare_loopback(baseline, candidate),
        baseline_created_at=baseline.created_at,
        candidate_created_at=candidate.created_at,
        roomscope_version=__version__,
        settings=settings.to_dict(),
    )
