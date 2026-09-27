"""Plain-text report of an analysis result (shared by CLI and GUI overview)."""

from __future__ import annotations

from roomscope.i18n import _, localize
from roomscope.interpretation import Finding
from roomscope.interpretation.profiles import (
    band_text,
    confidence_text,
    noise_segment_text,
    profile_title,
)
from roomscope.labels import metric_label, severity_text, topic_text, validity_word
from roomscope.models.comparison import ComparisonResult
from roomscope.models.result import (
    AnalysisResult,
    DecayMetric,
    PlacementLength,
    PlacementResult,
    Validity,
)


def _filter_note(warning: str | None) -> str:
    """The short head of a band's filter warning, in the active language."""
    if not warning:
        return ""
    text = localize(warning)
    for separator in (":", "："):
        text = text.split(separator, 1)[0]
    return text


def _metric(metric: DecayMetric) -> str:
    if metric.validity is Validity.VALID and metric.seconds is not None:
        return f"{metric.seconds:5.2f} s"
    if metric.validity is Validity.UNRELIABLE and metric.seconds is not None:
        return f"({metric.seconds:4.2f})?"
    if metric.validity is Validity.INSUFFICIENT_RANGE:
        return _("insuff.")
    return _("n/a")


def _length(label: str, length: PlacementLength) -> str:
    """One placement figure, with its qualifier on the same line as the number."""
    if length.metres is None:
        hint = (
            _(" (add {input})").format(input=length.missing_input) if length.missing_input else ""
        )
        return f"  {label:<26} {_('not determined')}{hint}"
    value = f"{length.metres:.2f} m"
    if length.input_uncertainty_m is not None:
        value += _(" +/-{uncertainty:.2f} from the stated inputs only").format(
            uncertainty=length.input_uncertainty_m
        )
    if length.validity is not Validity.VALID:
        value += f"  [{validity_word(length.validity)}]"
    return f"  {label:<26} {value}"


def _placement_section(placement: PlacementResult) -> list[str]:
    lines = [
        _("Placement (tier {tier}; no coordinates are derived -- see the JSON):").format(
            tier=placement.tier
        )
    ]
    assumed = _(" (assumed)") if placement.temperature_assumed else ""
    lines.append(
        f"  {_('speed of sound'):<26} {placement.speed_of_sound_m_s:.1f} m/s "
        + _("at {temp:.0f} C").format(temp=placement.temperature_c)
        + assumed
    )
    figures = (
        (_("loudspeaker height"), placement.source_height_m),
        (_("plane above the devices"), placement.ceiling_height_m),
        (_("horizontal separation"), placement.horizontal_separation_m),
    )
    for name, length in figures:
        lines.append(_length(name, length))
    for name, length in figures:
        if length.reason:
            lines.append(f"    {name}: {localize(length.reason)}")
    named = [c for c in placement.candidates if c.surface]
    if named:
        lines.append(_("  attributed arrivals:"))
        for candidate in named:
            lines.append(
                f"    {candidate.delay_ms:6.1f} ms  {candidate.surface}  "
                + _("excess path {path:.2f} m").format(path=candidate.excess_path_m)
            )
    for note in placement.notes:
        lines.append(_("  note: {note}").format(note=localize(note)))
    lines.append("")
    return lines


def format_report(
    result: AnalysisResult, findings: list[Finding] | None = None, profile_name: str = "generic"
) -> str:
    lines: list[str] = []
    ir = result.impulse_response
    lines.append(_("RoomScope analysis"))
    lines.append("=" * 72)
    lines.append(
        _("Sample rate: {rate} Hz    created: {created}").format(
            rate=result.sample_rate, created=result.created_at
        )
    )
    margin = f"{ir.pre_peak_margin_db:.1f} dB" if ir.pre_peak_margin_db is not None else _("n/a")
    lines.append(
        _(
            "Impulse response: {seconds:.2f} s analysed, {decay:.2f} s of decay recorded, "
            "direct-sound confidence {confidence} (pre-peak margin {margin})"
        ).format(
            seconds=ir.samples.shape[0] / result.sample_rate,
            decay=ir.valid_length_s,
            confidence=confidence_text(ir.direct_sound_confidence),
            margin=margin,
        )
    )
    lines.append(
        _("Sweep found at {start:.2f} s in the recording.").format(
            start=ir.sweep_start_in_recording_s
        )
    )
    if ir.loopback is not None:
        lb = ir.loopback
        if lb.compensation_applied:
            delay = f"{lb.path_delay_ms:.2f} ms" if lb.path_delay_ms is not None else _("n/a")
            bound = (
                f"{lb.distance_upper_bound_m:.2f} m"
                if lb.distance_upper_bound_m is not None
                else _("n/a")
            )
            lines.append(
                _(
                    "Loopback: compensated; electrical path delay {delay}; "
                    "distance upper bound {bound}."
                ).format(delay=delay, bound=bound)
            )
        elif lb.reason:
            lines.append(
                _("Loopback: offered but not applied ({reason})").format(reason=localize(lb.reason))
            )
        else:
            lines.append(_("Loopback: offered but not applied."))
    lines.append("")
    lines.append(_("Reverberation (extrapolated to 60 dB; 'insuff.' = insufficient decay range)"))
    lines.append(
        f"{_('band'):>10}  {_('EDT'):>8}  {_('T20'):>8}  {_('T30'):>8}  "
        f"{_('RT60 est.'):>10}  {_('range dB'):>8}  {_('note')}"
    )
    rows = [result.decay.broadband, *result.decay.bands]
    for band in rows:
        rt60 = (
            f"{band.rt60_estimate_s:.2f} s({band.rt60_basis})"
            if band.rt60_estimate_s is not None
            else "-"
        )
        note = _filter_note(band.filter_warning)
        lines.append(
            f"{band_text(band.band_label):>10}  {_metric(band.edt):>8}  {_metric(band.t20):>8}  {_metric(band.t30):>8}  "
            f"{rt60:>10}  {band.peak_to_noise_db:8.1f}  {note}"
        )
    lines.append("")
    noise = result.noise
    if noise.rms_dbfs is not None:
        lines.append(
            _(
                "Background noise ({source}, {duration:.2f} s): {rms:.1f} dBFS RMS, "
                "peak {peak:.1f} dBFS  [{calibration}]"
            ).format(
                source=noise_segment_text(noise.segment_source),
                duration=noise.segment_duration_s,
                rms=noise.rms_dbfs,
                peak=noise.peak_dbfs,
                calibration=localize(noise.calibration),
            )
        )
        hums = [h for h in noise.hum if h.detected]
        if hums:
            for hum in hums:
                harmonics = ", ".join(f"{f:.0f} Hz (+{p:.0f} dB)" for f, p in hum.harmonics)
                lines.append(
                    _("  Potential mains hum at multiples of {base:.0f} Hz: {harmonics}").format(
                        base=hum.base_hz, harmonics=harmonics
                    )
                )
        else:
            lines.append(_("  No mains hum detected (50/60 Hz harmonics)."))
    else:
        lines.append(_("Background noise: no quiet segment available."))
    for note in noise.notes:
        lines.append(_("  note: {note}").format(note=localize(note)))
    lines.append("")
    refl = result.reflections
    lines.append(
        _("Early reflections ({lo:.0f}-{hi:.0f} ms, above {threshold:.0f} dB):").format(
            lo=refl.window_ms[0], hi=refl.window_ms[1], threshold=refl.threshold_db
        )
    )
    if refl.reflections:
        for r in refl.reflections[:10]:
            lines.append(f"  {r.delay_ms:6.1f} ms   {r.relative_db:6.1f} dB")
    else:
        lines.append(_("  none above threshold"))
    lines.append("")
    placement = result.placement
    if placement is not None:
        lines.extend(_placement_section(placement))
    res = result.resonances
    lines.append(
        _("Potential low-frequency resonances (< {max_hz:.0f} Hz):").format(
            max_hz=res.max_frequency_hz
        )
    )
    if res.candidates:
        for c in res.candidates:
            decay = (
                f"{c.narrowband_decay_20db_s * 1000:.0f} ms"
                if c.narrowband_decay_20db_s is not None
                else _("n/a")
            )
            ring = (
                f"{c.filter_ringing_20db_s * 1000:.0f} ms"
                if c.filter_ringing_20db_s is not None
                else _("n/a")
            )
            flag = (
                _("decay distinguishable from filter")
                if c.decay_distinguishable
                else _("not distinguishable from filter ringing")
            )
            lines.append(
                f"  {c.frequency_hz:6.1f} Hz  +{c.level_above_baseline_db:4.1f} dB  "
                + _("20 dB decay {decay} (filter {ring})  {flag}").format(
                    decay=decay, ring=ring, flag=flag
                )
            )
    else:
        lines.append(_("  none"))
    if result.warnings:
        lines.append("")
        lines.append(_("Warnings:"))
        for warning in result.warnings:
            lines.append(f"  - {localize(warning)}")
    if findings:
        lines.append("")
        lines.append(
            _("Interpretation ({profile} profile):").format(profile=profile_title(profile_name))
        )
        for finding in findings:
            lines.append(
                f"  [{severity_text(str(finding.severity))}] {topic_text(finding.topic)}: "
                f"{finding.message}"
            )
    return "\n".join(lines)


def format_comparison_report(
    comparison: ComparisonResult,
    findings: list[Finding] | None = None,
    profile_name: str = "generic",
) -> str:
    """Plain-text comparison. Wording may change; this is not a Tier 1 interface."""
    lines = [_("RoomScope comparison"), "=" * 72]
    if comparison.common_band is not None:
        low, high = comparison.common_band
        lines.append(_("Common excitation band: {low:g}–{high:g} Hz").format(low=low, high=high))
    lines.append(
        _("Comparable: {value}").format(value=_("yes") if comparison.comparable else _("no"))
    )
    for note in comparison.notes:
        lines.append(_("  note: {note}").format(note=localize(note)))
    lines.append("")
    lines.append(_("Decay deltas (VALID only when both sides are VALID):"))
    lines.append(
        f"{_('metric'):<32} {_('base'):>8} {_('cand'):>8} {_('delta'):>10} {'%':>8}  {_('validity')}"
    )
    for item in comparison.decay:
        base = f"{item.baseline:.3f}" if item.baseline is not None else "—"
        cand = f"{item.candidate:.3f}" if item.candidate is not None else "—"
        if item.validity is Validity.VALID and item.delta is not None:
            delta = f"{item.delta:+.3f}"
            pct = f"{item.delta_percent:+.1f}" if item.delta_percent is not None else "—"
        else:
            delta = "—"
            pct = "—"
        lines.append(
            f"{metric_label(item.name):<32} {base:>8} {cand:>8} {delta:>10} {pct:>8}  "
            f"{validity_word(item.validity)}"
        )
        if item.reason and item.validity is not Validity.VALID:
            lines.append(f"    {localize(item.reason)}")
    if comparison.frequency_response is not None:
        lines.append("")
        lines.append(_("Frequency-response mean |Δ| per octave (dB):"))
        for label, mad in comparison.frequency_response.band_mad_db:
            lines.append(f"  {label:<10} {mad:5.2f} dB")
    if comparison.reflections:
        lines.append("")
        lines.append(_("Early reflections:"))
        for match in comparison.reflections:
            if match.status == "matched":
                lines.append(
                    f"  {_('matched')}  {match.baseline_delay_ms:.1f}→{match.candidate_delay_ms:.1f} ms  "
                    f"{match.baseline_relative_db:.1f}→{match.candidate_relative_db:.1f} dB"
                )
            elif match.status == "appeared":
                lines.append(
                    f"  {_('appeared')} {match.candidate_delay_ms:.1f} ms  "
                    f"{match.candidate_relative_db:.1f} dB"
                )
            else:
                lines.append(
                    f"  {_('disappeared')} {match.baseline_delay_ms:.1f} ms  "
                    f"{match.baseline_relative_db:.1f} dB"
                )
    if comparison.noise:
        lines.append("")
        lines.append(_("Noise:"))
        for item in comparison.noise:
            extra = f"  [{localize(item.reason)}]" if item.reason else ""
            lines.append(f"  {metric_label(item.name)}: {validity_word(item.validity)}{extra}")
    if comparison.placement:
        lines.append("")
        lines.append(_("Placement:"))
        for item in comparison.placement:
            extra = f"  [{localize(item.reason)}]" if item.reason else ""
            lines.append(f"  {metric_label(item.name)}: {validity_word(item.validity)}{extra}")
    if findings:
        lines.append("")
        lines.append(
            _("Interpretation ({profile} profile):").format(profile=profile_title(profile_name))
        )
        for finding in findings:
            lines.append(
                f"  [{severity_text(str(finding.severity))}] {topic_text(finding.topic)}: "
                f"{finding.message}"
            )
    return "\n".join(lines)
