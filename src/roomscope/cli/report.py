"""Plain-text report of an analysis result (shared by CLI and GUI overview).

The functions return plain text unless a :class:`~roomscope.cli.style.Style`
with colour is passed; the GUI always gets plain text. The wording is not a
Tier 1 interface: scripts should read ``--format json`` instead.
"""

from __future__ import annotations

import textwrap
import unicodedata

from roomscope.cli.style import PLAIN, Style
from roomscope.i18n import _
from roomscope.interpretation import Finding
from roomscope.interpretation.profiles import noise_segment_text
from roomscope.models.comparison import ComparisonResult, MetricDelta
from roomscope.models.result import (
    AnalysisResult,
    DecayMetric,
    PlacementLength,
    PlacementResult,
    Validity,
)

#: Width of the ``====`` rule under a report title (the GUI shows the same text).
RULE_WIDTH = 72
#: Column the values of the "At a glance" block start in.
_GLANCE_LABEL_WIDTH = 20


def display_width(text: str) -> int:
    """Terminal columns of ``text``: East Asian wide characters take two."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, width: int) -> str:
    """Left-align ``text`` in ``width`` terminal columns (CJK-aware ``ljust``)."""
    return text + " " * max(1, width - display_width(text))


def _metric(metric: DecayMetric) -> str:
    if metric.validity is Validity.VALID and metric.seconds is not None:
        return f"{metric.seconds:5.2f} s"
    if metric.validity is Validity.UNRELIABLE and metric.seconds is not None:
        return f"({metric.seconds:4.2f})?"
    if metric.validity is Validity.INSUFFICIENT_RANGE:
        return _("insuff.")
    return _("n/a")


def _wrap(text: str, indent: str, width: int = RULE_WIDTH) -> list[str]:
    return textwrap.wrap(
        text,
        width=width,
        initial_indent=indent,
        subsequent_indent=indent + "  ",
        break_long_words=False,
        break_on_hyphens=False,
    ) or [indent]


def _title(text: str, style: Style) -> list[str]:
    return [style.heading(text), "=" * RULE_WIDTH]


def _findings_section(findings: list[Finding], profile_name: str, style: Style) -> list[str]:
    lines = [
        "",
        style.heading(_("Interpretation ({profile} profile):").format(profile=profile_name)),
    ]
    for finding in findings:
        lines.append(
            f"  {style.severity(str(finding.severity))} {finding.topic}: {finding.message}"
        )
    return lines


# --------------------------------------------------------------------------- analysis


def summary_lines(result: AnalysisResult, style: Style = PLAIN) -> list[str]:
    """The "At a glance" block: one line per question a recording engineer asks.

    Every value is copied from the result; nothing is scored or combined.
    """

    def row(label: str, value: str) -> str:
        return f"  {pad(label, _GLANCE_LABEL_WIDTH)}{value}"

    lines = [style.heading(_("At a glance"))]

    broadband = result.decay.broadband
    if broadband.rt60_estimate_s is not None:
        reverb = _("RT60 {value:.2f} s (broadband, from {basis})").format(
            value=broadband.rt60_estimate_s, basis=broadband.rt60_basis or "-"
        )
    else:
        reverb = style.caution(_("no reliable broadband RT60 (see the table below)"))
    lines.append(row(_("Reverberation"), reverb))

    refl = result.reflections
    if refl.reflections:
        strongest = max(refl.reflections, key=lambda r: r.relative_db)
        early = _(
            "strongest at {delay:.1f} ms: {level:.1f} dB re direct ({count} above {threshold:.0f} dB)"
        ).format(
            delay=strongest.delay_ms,
            level=strongest.relative_db,
            count=len(refl.reflections),
            threshold=refl.threshold_db,
        )
    else:
        early = _("none above {threshold:.0f} dB").format(threshold=refl.threshold_db)
    lines.append(row(_("Early reflections"), early))

    res = result.resonances
    if res.candidates:
        listed = ", ".join(
            f"{c.frequency_hz:.0f} Hz (+{c.level_above_baseline_db:.1f} dB)"
            for c in res.candidates[:4]
        )
        low = _("potential resonances: {listed}").format(listed=listed)
    else:
        low = _("no potential resonance below {max_hz:.0f} Hz").format(max_hz=res.max_frequency_hz)
    lines.append(row(_("Low end"), low))

    noise = result.noise
    if noise.rms_dbfs is not None:
        floor = _("{rms:.1f} dBFS RMS (uncalibrated)").format(rms=noise.rms_dbfs)
        hums = [h for h in noise.hum if h.detected]
        if hums:
            floor += style.caution(_(", mains hum at {base:.0f} Hz").format(base=hums[0].base_hz))
    else:
        floor = _("no quiet segment in the recording")
    lines.append(row(_("Noise floor"), floor))

    quality = _("direct-sound confidence {confidence}, core warnings: {count}").format(
        confidence=result.impulse_response.direct_sound_confidence,
        count=len(result.warnings),
    )
    if result.clipping is not None and result.clipping.clipped:
        quality += ", " + style.bad(_("CLIPPING in the recording"))
    lines.append(row(_("Data quality"), quality))
    return lines


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
        value += f"  [{length.validity}]"
    return f"  {label:<26} {value}"


def _placement_section(placement: PlacementResult, style: Style = PLAIN) -> list[str]:
    heading = style.heading(
        _("Placement (tier {tier}; no coordinates are derived -- see the JSON):").format(
            tier=placement.tier
        )
    )
    figures = (
        (_("loudspeaker height"), placement.source_height_m),
        (_("plane above the devices"), placement.ceiling_height_m),
        (_("horizontal separation"), placement.horizontal_separation_m),
    )
    named = [c for c in placement.candidates if c.surface]
    if all(length.metres is None for _name, length in figures) and not named:
        # Nothing was derived: one hint instead of three identical reasons.
        missing = next(
            (length.missing_input for _n, length in figures if length.missing_input), None
        )
        hint = (
            _("  not determined -- add {input} to derive heights from the reflections").format(
                input=missing
            )
            if missing
            else _("  not determined")
        )
        return [heading, hint, ""]
    lines = [heading]
    assumed = _(" (assumed)") if placement.temperature_assumed else ""
    lines.append(
        f"  {_('speed of sound'):<26} {placement.speed_of_sound_m_s:.1f} m/s "
        + _("at {temp:.0f} C").format(temp=placement.temperature_c)
        + assumed
    )
    for name, length in figures:
        lines.append(_length(name, length))
    for name, length in figures:
        if length.reason:
            lines.extend(_wrap(f"{name}: {length.reason}", "    "))
    if named:
        lines.append(_("  attributed arrivals:"))
        for candidate in named:
            lines.append(
                f"    {candidate.delay_ms:6.1f} ms  {candidate.surface}  "
                + _("excess path {path:.2f} m").format(path=candidate.excess_path_m)
            )
    for note in placement.notes:
        lines.extend(_wrap(_("  note: {note}").format(note=note), ""))
    lines.append("")
    return lines


def format_report(
    result: AnalysisResult,
    findings: list[Finding] | None = None,
    profile_name: str = "generic",
    *,
    style: Style = PLAIN,
) -> str:
    lines: list[str] = []
    ir = result.impulse_response
    lines.extend(_title(_("RoomScope analysis"), style))
    lines.extend(summary_lines(result, style))
    lines.append("")
    lines.append(style.heading(_("Measurement")))
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
            confidence=ir.direct_sound_confidence,
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
            lines.append(_("Loopback: offered but not applied ({reason})").format(reason=lb.reason))
        else:
            lines.append(_("Loopback: offered but not applied."))
    lines.append("")
    lines.append(
        style.heading(
            _("Reverberation (extrapolated to 60 dB; 'insuff.' = insufficient decay range)")
        )
    )
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
        note = band.filter_warning.split(":")[0] if band.filter_warning else ""
        range_db = f"{band.peak_to_noise_db:8.1f}" if band.peak_to_noise_db is not None else "-"
        lines.append(
            f"{band.band_label:>10}  {_metric(band.edt):>8}  {_metric(band.t20):>8}  "
            f"{_metric(band.t30):>8}  {rt60:>10}  {range_db:>8}  {note}".rstrip()
        )
    lines.append("")
    noise = result.noise
    if noise.rms_dbfs is not None:
        lines.append(
            style.heading(
                _(
                    "Background noise ({source}, {duration:.2f} s): {rms:.1f} dBFS RMS, "
                    "peak {peak:.1f} dBFS  [{calibration}]"
                ).format(
                    source=noise_segment_text(noise.segment_source),
                    duration=noise.segment_duration_s,
                    rms=noise.rms_dbfs,
                    peak=noise.peak_dbfs,
                    calibration=noise.calibration,
                )
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
        lines.append(style.heading(_("Background noise: no quiet segment available.")))
    for note in noise.notes:
        lines.extend(_wrap(_("  note: {note}").format(note=note), ""))
    lines.append("")
    refl = result.reflections
    lines.append(
        style.heading(
            _("Early reflections ({lo:.0f}-{hi:.0f} ms, above {threshold:.0f} dB):").format(
                lo=refl.window_ms[0], hi=refl.window_ms[1], threshold=refl.threshold_db
            )
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
        lines.extend(_placement_section(placement, style))
    res = result.resonances
    lines.append(
        style.heading(
            _("Potential low-frequency resonances (< {max_hz:.0f} Hz):").format(
                max_hz=res.max_frequency_hz
            )
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
        lines.append(style.heading(_("Warnings (core diagnostics, always English):")))
        for warning in result.warnings:
            lines.extend(_wrap(f"- {warning}", "  "))
    if findings:
        lines.extend(_findings_section(findings, profile_name, style))
    return "\n".join(lines)


# --------------------------------------------------------------------------- comparison

_DECAY_METRICS = ("edt", "t20", "t30", "rt60_estimate")


def _split_decay_name(name: str) -> tuple[str, str | None]:
    """``band.63 Hz.t20`` -> (``63 Hz``, ``t20``); a missing band has no metric."""
    for metric in _DECAY_METRICS:
        suffix = "." + metric
        if name.endswith(suffix):
            scope = name[: -len(suffix)]
            return scope.removeprefix("band."), metric
    return name.removeprefix("band."), None


def _merge_sides(reason: str) -> str:
    """``baseline X (r); candidate X (r)`` -> ``both sides X (r)`` when identical."""
    head, joint = "baseline ", "; candidate "
    if not reason.startswith(head):
        return reason
    start = 0
    while (index := reason.find(joint, start)) != -1:
        left = reason[len(head) : index]
        right = reason[index + len(joint) :]
        if left == right:
            return _("both sides {state}").format(state=left)
        start = index + 1
    return reason


def _percent(item: MetricDelta | None) -> str:
    if item is None or item.validity is not Validity.VALID or item.delta_percent is None:
        return "—"
    return f"{item.delta_percent:+.1f}%"


def _seconds(value: float | None) -> str:
    return f"{value:.2f} s" if value is not None else "—"


def _decay_table(comparison: ComparisonResult, style: Style) -> list[str]:
    bands: dict[str, dict[str, MetricDelta]] = {}
    missing: dict[str, MetricDelta] = {}
    for item in comparison.decay:
        label, metric = _split_decay_name(item.name)
        if metric is None:
            missing[label] = item
            bands.setdefault(label, {})
        else:
            bands.setdefault(label, {})[metric] = item
    lines = [
        style.heading(_("Reverberation: baseline -> candidate (change only when both are VALID)")),
        f"{_('band'):>10}  {_('RT60 base'):>9}  {_('RT60 cand'):>9}  {_('change'):>8}  "
        f"{_('EDT'):>7}  {_('T20'):>7}  {_('T30'):>7}",
    ]
    for label, metrics in bands.items():
        rt = metrics.get("rt60_estimate")
        base = rt.baseline if rt is not None else None
        cand = rt.candidate if rt is not None else None
        if label in missing:
            base, cand = missing[label].baseline, missing[label].candidate
        change = _percent(rt)
        change_text = f"{change:>8}"
        if rt is not None:
            change_text = style.validity(str(rt.validity), change_text)
        lines.append(
            f"{label:>10}  {_seconds(base):>9}  {_seconds(cand):>9}  {change_text}  "
            f"{_percent(metrics.get('edt')):>7}  {_percent(metrics.get('t20')):>7}  "
            f"{_percent(metrics.get('t30')):>7}"
        )
    # Why a cell shows "—": each distinct reason once, with the cells it covers.
    reasons: dict[str, list[str]] = {}
    for item in comparison.decay:
        if item.validity is Validity.VALID or not item.reason:
            continue
        label, metric = _split_decay_name(item.name)
        where = label if metric is None else f"{label} {metric.replace('_estimate', '').upper()}"
        reasons.setdefault(_merge_sides(item.reason), []).append(where)
    if reasons:
        lines.append(style.dim(_("  — = not compared:")))
        for reason, cells in reasons.items():
            lines.extend(_wrap(f"{', '.join(cells)}: {reason}", "    "))
    return lines


def comparison_summary_lines(comparison: ComparisonResult, style: Style = PLAIN) -> list[str]:
    """The "At a glance" block of a comparison: baseline -> candidate, one line per topic."""

    def row(label: str, value: str) -> str:
        return f"  {pad(label, _GLANCE_LABEL_WIDTH)}{value}"

    lines = [style.heading(_("At a glance"))]
    rt = next((d for d in comparison.decay if d.name == "broadband.rt60_estimate"), None)
    if rt is not None and rt.validity is Validity.VALID and rt.delta_percent is not None:
        reverb = _("RT60 {base:.2f} s -> {cand:.2f} s ({percent:+.1f} %)").format(
            base=rt.baseline, cand=rt.candidate, percent=rt.delta_percent
        )
    else:
        reverb = style.caution(_("broadband RT60 not comparable (see the table below)"))
    lines.append(row(_("Reverberation"), reverb))

    counts = {"matched": 0, "appeared": 0, "disappeared": 0}
    for match in comparison.reflections:
        counts[match.status] = counts.get(match.status, 0) + 1
    if comparison.reflections:
        early = _("{gone} gone, {new} new, {kept} at both").format(
            gone=counts["disappeared"], new=counts["appeared"], kept=counts["matched"]
        )
    else:
        early = _("none above the threshold on either side")
    lines.append(row(_("Early reflections"), early))

    parts: list[str] = []
    both = [f"{r.candidate_hz:.0f} Hz" for r in comparison.resonances if r.status == "matched"]
    gone = [f"{r.baseline_hz:.0f} Hz" for r in comparison.resonances if r.status == "disappeared"]
    new = [f"{r.candidate_hz:.0f} Hz" for r in comparison.resonances if r.status == "appeared"]
    if both:
        parts.append(_("at both: {list}").format(list=", ".join(both)))
    if gone:
        parts.append(_("gone: {list}").format(list=", ".join(gone)))
    if new:
        parts.append(_("new: {list}").format(list=", ".join(new)))
    lines.append(row(_("Low end"), "; ".join(parts) if parts else _("no potential resonance")))

    rms = next((d for d in comparison.noise if d.name == "noise.rms_dbfs"), None)
    if rms is not None and rms.baseline is not None and rms.candidate is not None:
        if rms.validity is Validity.VALID and rms.delta is not None:
            noise = _("{base:.1f} -> {cand:.1f} dBFS ({delta:+.1f} dB)").format(
                base=rms.baseline, cand=rms.candidate, delta=rms.delta
            )
        else:
            noise = _("{base:.1f} -> {cand:.1f} dBFS, not compared ({validity})").format(
                base=rms.baseline, cand=rms.candidate, validity=rms.validity
            )
            if rms.reason and "gain" in rms.reason:
                noise += style.dim(_(" -- add --same-input-gain if the gain was unchanged"))
    else:
        noise = _("no quiet segment on one or both sides")
    lines.append(row(_("Noise floor"), noise))

    fr = comparison.frequency_response
    if fr is not None and fr.band_mad_db:
        band, mad = max(fr.band_mad_db, key=lambda item: item[1])
        lines.append(
            row(
                _("Frequency response"),
                _("largest change in the {band} octave ({mad:.1f} dB mean |Δ|)").format(
                    band=band, mad=mad
                ),
            )
        )
    return lines


def _delta_line(item: MetricDelta, label: str, style: Style) -> str:
    unit = f" {item.unit}" if item.unit else ""
    base = f"{item.baseline:.1f}" if item.baseline is not None else "—"
    cand = f"{item.candidate:.1f}" if item.candidate is not None else "—"
    if item.validity is Validity.VALID and item.delta is not None:
        change = f"{item.delta:+.1f}"
    else:
        change = "—"
    validity = style.validity(str(item.validity))
    return f"  {label:<14} {base:>8} {cand:>8}{unit:<6} {change:>7}  {validity}"


def format_comparison_report(
    comparison: ComparisonResult,
    findings: list[Finding] | None = None,
    profile_name: str = "generic",
    *,
    style: Style = PLAIN,
) -> str:
    """Plain-text comparison. Wording may change; this is not a Tier 1 interface."""
    lines = _title(_("RoomScope comparison"), style)
    if comparison.baseline_session:
        lines.append(_("Baseline:  {path}").format(path=comparison.baseline_session))
    if comparison.candidate_session:
        lines.append(_("Candidate: {path}").format(path=comparison.candidate_session))
    if comparison.common_band is not None:
        low, high = comparison.common_band
        lines.append(
            _("Common excitation band: {low:.0f}–{high:.0f} Hz").format(low=low, high=high)
        )
    comparable = _("yes") if comparison.comparable else _("no")
    lines.append(
        _("Comparable: {value}").format(
            value=style.good(comparable) if comparison.comparable else style.bad(comparable)
        )
    )
    for note in comparison.notes:
        lines.extend(_wrap(_("  note: {note}").format(note=note), ""))
    lines.append("")
    lines.extend(comparison_summary_lines(comparison, style))
    lines.append("")
    lines.extend(_decay_table(comparison, style))
    if comparison.frequency_response is not None and comparison.frequency_response.band_mad_db:
        lines.append("")
        lines.append(style.heading(_("Frequency-response mean |Δ| per octave (dB):")))
        cells = [f"{label} {mad:.1f}" for label, mad in comparison.frequency_response.band_mad_db]
        for start in range(0, len(cells), 5):
            lines.append(
                "  " + "   ".join(f"{cell:<13}" for cell in cells[start : start + 5]).rstrip()
            )
    if comparison.reflections:
        lines.append("")
        lines.append(style.heading(_("Early reflections (delay, level re direct sound):")))
        for match in comparison.reflections:
            if match.status == "matched":
                lines.append(
                    f"  {_('matched'):<12} {match.baseline_delay_ms:.1f}→{match.candidate_delay_ms:.1f} ms  "
                    f"{match.baseline_relative_db:.1f}→{match.candidate_relative_db:.1f} dB"
                )
            elif match.status == "appeared":
                lines.append(
                    f"  {_('appeared'):<12} {match.candidate_delay_ms:.1f} ms  "
                    f"{match.candidate_relative_db:.1f} dB"
                )
            else:
                lines.append(
                    f"  {_('disappeared'):<12} {match.baseline_delay_ms:.1f} ms  "
                    f"{match.baseline_relative_db:.1f} dB"
                )
    if comparison.resonances:
        lines.append("")
        lines.append(style.heading(_("Potential low-frequency resonances:")))
        for res in comparison.resonances:
            if res.status == "matched":
                lines.append(
                    f"  {_('matched'):<12} {res.baseline_hz:.1f}→{res.candidate_hz:.1f} Hz"
                )
            elif res.status == "appeared":
                lines.append(f"  {_('appeared'):<12} {res.candidate_hz:.1f} Hz")
            else:
                lines.append(f"  {_('disappeared'):<12} {res.baseline_hz:.1f} Hz")
    if comparison.noise:
        lines.append("")
        lines.append(style.heading(_("Noise (baseline, candidate, change):")))
        for item in comparison.noise:
            label = item.name.removeprefix("noise.")
            label = _("RMS") if label == "rms_dbfs" else label.removeprefix("band.")
            lines.append(_delta_line(item, label, style))
            if item.reason and item.validity is not Validity.VALID:
                lines.extend(_wrap(item.reason, "    "))
    for heading, items in (
        (_("Placement:"), comparison.placement),
        (_("Loopback:"), comparison.loopback),
    ):
        if all(item.validity is Validity.NOT_COMPARABLE for item in items):
            # Nothing to compare (no tape measurements / no loopback): the JSON keeps the reasons.
            continue
        lines.append("")
        lines.append(style.heading(heading))
        for item in items:
            lines.append(f"  {item.name}: {style.validity(str(item.validity))}")
            if item.reason:
                lines.extend(_wrap(item.reason, "    "))
    if findings:
        lines.extend(_findings_section(findings, profile_name, style))
    return "\n".join(lines)
