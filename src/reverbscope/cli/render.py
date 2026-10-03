"""What the command line prints, laid out through :mod:`reverbscope.cli.console`.

Every command reads the same way: what ran and on what (title and context),
the result (status lines, "At a glance"), the detail, then what to do next.
The GUI shows the same analysis and comparison reports in its text panes
(rendered with a plain :class:`Console`), so there is one report layout.
Stored diagnostics are shown with :func:`~reverbscope.i18n.localize`; nothing
here changes a stored value.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reverbscope.cli.console import Console, Status, Verbatim, cell_width, glue_units, shell_command
from reverbscope.edition import RELEASES_URL, is_terminal_package
from reverbscope.i18n import _, localize, pgettext
from reverbscope.interpretation import Finding
from reverbscope.interpretation.profiles import (
    band_text,
    confidence_text,
    noise_segment_text,
    profile_title,
)
from reverbscope.labels import metric_label, topic_text, validity_word
from reverbscope.models.comparison import ComparisonResult, MetricDelta
from reverbscope.models.result import (
    AnalysisResult,
    BandDecay,
    DecayMetric,
    EnergyMetric,
    PlacementLength,
    PlacementResult,
    Validity,
)

if TYPE_CHECKING:
    from reverbscope.audio.backend import DeviceInfo
    from reverbscope.audio.inventory import DeviceInventory
    from reverbscope.demo import DemoRun
    from reverbscope.models.configuration import SweepSettings


#: The GUI's "Full report" panes: the same layout as the terminal, as plain
#: text (no colour) in a fixed width that suits the pane's monospace font.
REPORT_CONSOLE = Console(color=False, unicode=True, width=96)


# --- Small formatters ----------------------------------------------------------


def rate_text(hz: float) -> str:
    """48000 -> ``48 kHz``, 44100 -> ``44.1 kHz``."""
    khz = hz / 1000.0
    return f"{khz:g} kHz" if khz >= 1 else f"{hz:g} Hz"


def rates_text(rates: Sequence[int], console: Console) -> str:
    if not rates:
        return pgettext("sample rates", "none")
    return console.sep().join(f"{rate / 1000:g}" for rate in rates) + " kHz"


def frequency_text(hz: float) -> str:
    return f"{hz / 1000:.3g} kHz" if hz >= 1000 else f"{hz:.3g} Hz"


def created_text(created: str) -> str:
    """An ISO time stamp as ``2026-09-27 14:10 +00:00``; other text unchanged."""
    try:
        moment = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return created
    offset = moment.strftime("%z")
    if len(offset) == 5:
        offset = f"{offset[:3]}:{offset[3:]}"
    return f"{moment:%Y-%m-%d %H:%M} {offset}".strip()


def validity_status(validity: Validity) -> Status:
    if validity is Validity.VALID:
        return "ok"
    if validity is Validity.UNRELIABLE:
        return "unsure"
    if validity is Validity.INSUFFICIENT_RANGE:
        return "warn"
    return "skip"


def validity_cell(console: Console, validity: Validity) -> str:
    """``✓ valid``, ``? unreliable``: a symbol and the word, never colour alone."""
    return f"{console.symbol(validity_status(validity))} {validity_word(validity)}"


def severity_status(severity: str) -> Status:
    return {"warning": "warn", "notice": "warn", "info": "info"}.get(severity, "info")  # type: ignore[return-value]


def severity_word(severity: str) -> str:
    return {"warning": _("Warning"), "notice": _("Notice"), "info": _("Info")}.get(
        severity, severity
    )


def _metric_cell(console: Console, metric: DecayMetric) -> str:
    """A decay time, marked when it is not a VALID measurement."""
    if metric.seconds is not None and metric.validity is Validity.VALID:
        return f"{metric.seconds:.2f} s"
    if metric.seconds is not None and metric.validity is Validity.UNRELIABLE:
        return console.style(f"{metric.seconds:.2f} s", "yellow") + " " + console.symbol("unsure")
    if metric.validity is Validity.INSUFFICIENT_RANGE:
        return console.symbol("warn")
    return console.symbol("skip")


def _findings(console: Console, findings: Sequence[Finding], profile_name: str) -> list[str]:
    if not findings:
        return []
    lines = console.section(
        _("Interpretation ({profile} profile)").format(profile=profile_title(profile_name))
    )
    for number, finding in enumerate(findings):
        if number:
            lines.append("")
        severity = str(finding.severity)
        head = f"{severity_word(severity)}{console.sep()}{topic_text(finding.topic)}"
        lines += console.status(severity_status(severity), console.bold(head))
        lines += console.paragraph(finding.message, indent=4)
    return lines


# --- Analysis ----------------------------------------------------------------------


def render_analysis(
    console: Console,
    result: AnalysisResult,
    findings: Sequence[Finding] = (),
    profile_name: str = "generic",
    *,
    inputs: Sequence[tuple[str, str]] = (),
) -> str:
    """The report of one analysis: context, "At a glance", results by topic,
    diagnostics, then the interpretation."""
    c = console
    lines = c.title(_("ReverbScope analysis"))
    lines.append("")
    lines += c.fields(
        [
            *inputs,
            (_("Sample rate"), rate_text(result.sample_rate)),
            (_("Created"), created_text(result.created_at)),
        ]
    )
    lines += at_a_glance(c, result, findings)
    lines += _reverberation(c, result)
    lines += _noise(c, result)
    lines += _reflections(c, result)
    if result.placement is not None:
        lines += _placement(c, result.placement)
    lines += _resonances(c, result)
    lines += _diagnostics(c, result)
    lines += _findings(c, findings, profile_name)
    return c.fit("\n".join(lines))


def _topic_status(findings: Sequence[Finding], *topics: str) -> Status:
    """``warn`` when the profile raised a warning or notice on one of ``topics``.

    The thresholds are the recording profile's (see the interpretation); the
    summary only repeats what it concluded.
    """
    for finding in findings:
        if finding.topic in topics and str(finding.severity) in ("warning", "notice"):
            return "warn"
    return "ok"


def _glance_label_width() -> int:
    """One label column for every "At a glance" block, so they line up when shown together."""
    labels = (
        _("Reverberation"),
        _("Clarity"),
        _("Early reflections"),
        _("Low end"),
        _("Noise floor"),
        _("Data quality"),
        _("Frequency response"),
    )
    return max(cell_width(label) for label in labels)


def at_a_glance(c: Console, result: AnalysisResult, findings: Sequence[Finding] = ()) -> list[str]:
    """One line per question a recording engineer asks first.

    Every value is copied from the result; the symbol follows the profile's
    findings on that topic. The sections below hold the detail.
    """
    rows: list[tuple[str, str]] = []

    def row(label: str, status: Status, text: str) -> None:
        rows.append((label, f"{c.symbol(status)} {glue_units(text)}"))

    broadband = result.decay.broadband
    if broadband.rt60_estimate_s is not None:
        text = _("RT60 {seconds:.2f} s").format(seconds=broadband.rt60_estimate_s)
        if broadband.rt60_basis:
            text += c.muted(f" ({broadband.rt60_basis})")
        if broadband.edt.seconds is not None and broadband.edt.validity is Validity.VALID:
            text += c.sep() + f"EDT {broadband.edt.seconds:.2f} s"
        row(_("Reverberation"), _topic_status(findings, "reverberation"), text)
    else:
        row(_("Reverberation"), "unsure", _("no reliable broadband RT60 (see Reverberation)"))

    clarity = _clarity_glance(c, broadband)
    if clarity is not None:
        row(_("Clarity"), _topic_status(findings, "clarity"), clarity)

    refl = result.reflections
    if refl.reflections:
        strongest = max(refl.reflections, key=lambda r: r.relative_db)
        row(
            _("Early reflections"),
            _topic_status(findings, "early_reflections"),
            _(
                "strongest {level:.1f} dB at {delay:.1f} ms{sep}{count} above {threshold:.0f} dB"
            ).format(
                level=strongest.relative_db,
                delay=strongest.delay_ms,
                sep=c.sep(),
                count=len(refl.reflections),
                threshold=refl.threshold_db,
            ),
        )
    else:
        row(
            _("Early reflections"),
            "ok",
            _("none above {threshold:.0f} dB").format(threshold=refl.threshold_db),
        )

    res = result.resonances
    if res.candidates:
        strongest_modes = sorted(
            res.candidates, key=lambda cand: cand.level_above_baseline_db, reverse=True
        )[:3]
        listed = ", ".join(
            f"{cand.frequency_hz:.0f} Hz (+{cand.level_above_baseline_db:.1f} dB)"
            for cand in strongest_modes
        )
        row(
            _("Low end"),
            _topic_status(findings, "low_frequency"),
            _("potential resonances at {listed}").format(listed=listed),
        )
    else:
        row(
            _("Low end"),
            "ok",
            _("no potential resonance below {max_hz:.0f} Hz").format(max_hz=res.max_frequency_hz),
        )

    noise = result.noise
    if noise.rms_dbfs is not None:
        text = _("{rms:.1f} dBFS RMS").format(rms=noise.rms_dbfs)
        hums = [hum for hum in noise.hum if hum.detected]
        status = _topic_status(findings, "noise")
        if hums:
            text += c.sep() + _("mains hum at {base:.0f} Hz").format(base=hums[0].base_hz)
            status = "warn"
        row(_("Noise floor"), status, text)
    else:
        row(_("Noise floor"), "skip", _("no quiet segment in the recording"))

    ir = result.impulse_response
    quality = _("direct sound: confidence {confidence}").format(
        confidence=confidence_text(ir.direct_sound_confidence)
    )
    status = _topic_status(findings, "measurement")
    if result.warnings:
        quality += c.sep() + _("{n} warning(s), see Diagnostics").format(n=len(result.warnings))
        status = "warn"
    else:
        quality += c.sep() + _("no warnings")
    if result.clipping is not None and result.clipping.clipped:
        quality += c.sep() + _("the recording clipped")
        status = "error"
    row(_("Data quality"), status, quality)
    return c.section(_("At a glance")) + c.fields(rows, min_label=_glance_label_width())


def _diagnostics(c: Console, result: AnalysisResult) -> list[str]:
    """How the impulse response was found, and the core's warnings."""
    ir = result.impulse_response
    lines = c.section(_("Diagnostics"))
    margin = f"{ir.pre_peak_margin_db:.1f} dB" if ir.pre_peak_margin_db is not None else c.dash()
    rows = [
        (
            _("Sweep found"),
            _("{start:.2f} s into the recording").format(start=ir.sweep_start_in_recording_s),
        ),
        (
            _("Analysed"),
            _("{seconds:.2f} s, of which {decay:.2f} s is decay").format(
                seconds=ir.samples.shape[0] / result.sample_rate, decay=ir.valid_length_s
            ),
        ),
        (
            _("Direct sound"),
            _("confidence {confidence}{sep}pre-peak margin {margin}").format(
                confidence=confidence_text(ir.direct_sound_confidence),
                sep=c.sep(),
                margin=margin,
            ),
        ),
    ]
    if ir.loopback is not None:
        rows.append((_("Loopback"), _loopback_text(c, result)))
    lines += c.fields(rows)
    if result.warnings:
        lines.append("")
        for warning in result.warnings:
            lines += c.status("warn", localize(warning))
    return lines


def _loopback_text(c: Console, result: AnalysisResult) -> str:
    lb = result.impulse_response.loopback
    assert lb is not None
    if lb.compensation_applied:
        delay = f"{lb.path_delay_ms:.2f} ms" if lb.path_delay_ms is not None else c.dash()
        bound = (
            f"{lb.distance_upper_bound_m:.2f} m"
            if lb.distance_upper_bound_m is not None
            else c.dash()
        )
        return _("compensated{sep}path delay {delay}{sep}distance at most {bound}").format(
            sep=c.sep(), delay=delay, bound=bound
        )
    if lb.reason:
        return _("not applied: {reason}").format(reason=localize(lb.reason))
    return _("offered but not applied")


def _reverberation(c: Console, result: AnalysisResult) -> list[str]:
    lines = c.section(_("Reverberation"), _("extrapolated to 60 dB"))
    rows = []
    seen: set[Validity] = set()
    notes: list[str] = []
    for band in (result.decay.broadband, *result.decay.bands):
        for metric in (band.edt, band.t20, band.t30):
            seen.add(metric.validity)
        rt60 = (
            f"{band.rt60_estimate_s:.2f} s " + c.muted(f"({band.rt60_basis})")
            if band.rt60_estimate_s is not None
            else c.symbol("skip")
        )
        span = f"{band.peak_to_noise_db:.1f} dB" if band.peak_to_noise_db is not None else c.dash()
        rows.append(
            [
                band_text(band.band_label),
                _metric_cell(c, band.edt),
                _metric_cell(c, band.t20),
                _metric_cell(c, band.t30),
                rt60,
                span,
            ]
        )
        if band.filter_warning:
            notes.append(f"{band_text(band.band_label)}: {localize(band.filter_warning)}")
    headers = [_("Band"), "EDT", "T20", "T30", "RT60", _("Decay range")]
    bases = {band.rt60_basis for band in (result.decay.broadband, *result.decay.bands)}
    basis_note = ""
    if not c.fits(headers, rows, gap=2) and len(bases - {None, ""}) == 1:
        # A narrow terminal: every band's RT60 has the same basis; say it once
        # instead of in every row, so the table still fits.
        (basis,) = bases - {None, ""}
        for row, band in zip(rows, (result.decay.broadband, *result.decay.bands), strict=True):
            if band.rt60_estimate_s is not None:
                row[4] = f"{band.rt60_estimate_s:.2f} s"
        basis_note = _("RT60 extrapolated from {basis} in every band").format(basis=basis)
    lines += c.table(headers, rows, align="lrrrrr")
    if basis_note:
        lines += c.paragraph(basis_note, style=("dim",))
    legend = [
        f"{c.symbol(validity_status(v))} {validity_word(v)}"
        for v in (
            Validity.UNRELIABLE,
            Validity.INSUFFICIENT_RANGE,
            Validity.NOT_COMPUTED,
            Validity.OUTSIDE_EXCITATION,
        )
        if v in seen
    ]
    if legend:
        lines.append("")
        lines.append("  " + "   ".join(legend))
    for note in notes:
        lines += c.status("info", note)
    lines += _energy(c, result)
    return lines


def _clarity_glance(c: Console, band: BandDecay) -> str | None:
    """C50 / C80 / D50 for the at-a-glance line, or ``None`` when none is valid."""
    parts: list[str] = []
    if band.c50.validity is Validity.VALID and band.c50.value is not None:
        parts.append(f"C50 {band.c50.value:+.1f} dB")
    if band.c80.validity is Validity.VALID and band.c80.value is not None:
        parts.append(f"C80 {band.c80.value:+.1f} dB")
    if band.d50.validity is Validity.VALID and band.d50.value is not None:
        parts.append(f"D50 {band.d50.value:.0f} %")
    if not parts:
        return None
    return c.sep().join(parts)


def _energy_number(metric: EnergyMetric) -> str | None:
    if metric.value is None:
        return None
    if metric.unit == "dB":
        return f"{metric.value:+.1f} dB"
    if metric.unit == "%":
        return f"{metric.value:.0f} %"
    return f"{metric.value * 1000:.0f} ms"


def _energy_cell(c: Console, metric: EnergyMetric) -> str:
    number = _energy_number(metric)
    if number is not None and metric.validity is Validity.VALID:
        return number
    if number is not None and metric.validity is Validity.UNRELIABLE:
        return c.style(number, "yellow") + " " + c.symbol("unsure")
    if metric.validity is Validity.INSUFFICIENT_RANGE:
        return c.symbol("warn")
    return c.symbol("skip")


def _energy(c: Console, result: AnalysisResult) -> list[str]:
    """C50, C80, D50 and centre time. Ratios, not a judgement of the room."""
    lines = c.section(
        _("Early and late energy"),
        _("ratios from the same truncation as the decay; not a room score"),
    )
    lines += c.paragraph(
        _(
            "C50 is early energy over late energy at 50 ms (speech). C80 is the same "
            "at 80 ms (music). D50 is the share of energy in the first 50 ms. Centre "
            "time is the energy-weighted average time. Time zero is the detected "
            "direct sound. A ratio is reported only when the decay range is at least "
            "20 dB, and it is not a room score."
        )
    )
    rows = []
    for band in (result.decay.broadband, *result.decay.bands):
        rows.append(
            [
                band_text(band.band_label),
                _energy_cell(c, band.c50),
                _energy_cell(c, band.c80),
                _energy_cell(c, band.d50),
                _energy_cell(c, band.centre_time),
            ]
        )
    lines += c.table(
        [_("Band"), "C50", "C80", "D50", _("Centre time")],
        rows,
        align="lrrrr",
    )
    return lines


def _noise(c: Console, result: AnalysisResult) -> list[str]:
    noise = result.noise
    lines = c.section(_("Background noise"))
    if noise.rms_dbfs is None:
        lines += c.status("skip", _("No quiet segment was available."))
    else:
        peak = f"{noise.peak_dbfs:.1f} dBFS" if noise.peak_dbfs is not None else c.dash()
        segment = noise_segment_text(noise.segment_source)
        if noise.segment_duration_s is not None:
            segment += f"{c.sep()}{noise.segment_duration_s:.2f} s"
        lines += c.fields(
            [
                (
                    _("Level"),
                    _("{rms:.1f} dBFS RMS{sep}peak {peak}").format(
                        rms=noise.rms_dbfs, sep=c.sep(), peak=peak
                    ),
                ),
                (_("Segment"), segment),
                (_("Calibration"), localize(noise.calibration)),
            ]
        )
        hums = [h for h in noise.hum if h.detected]
        for hum in hums:
            harmonics = ", ".join(f"{f:.0f} Hz (+{p:.0f} dB)" for f, p in hum.harmonics)
            lines += c.status(
                "warn",
                _("Potential mains hum at multiples of {base:.0f} Hz: {harmonics}").format(
                    base=hum.base_hz, harmonics=harmonics
                ),
            )
        if not hums:
            lines += c.status("ok", _("No mains hum detected (50/60 Hz harmonics)."))
    for note in noise.notes:
        lines += c.status("info", localize(note))
    return lines


def _reflections(c: Console, result: AnalysisResult) -> list[str]:
    refl = result.reflections
    lines = c.section(
        _("Early reflections"),
        _("{lo:.0f}–{hi:.0f} ms, above {threshold:.0f} dB").format(
            lo=refl.window_ms[0], hi=refl.window_ms[1], threshold=refl.threshold_db
        ),
    )
    if not refl.reflections:
        return lines + c.status("skip", _("None above the threshold."))
    rows = [[f"{r.delay_ms:.1f} ms", f"{r.relative_db:.1f} dB"] for r in refl.reflections[:10]]
    lines += c.table([_("Delay"), _("Level")], rows, align="rr")
    hidden = len(refl.reflections) - 10
    if hidden > 0:
        lines += c.paragraph(_("{n} more in result.json").format(n=hidden), style=("dim",))
    return lines


def _length_text(c: Console, length: PlacementLength) -> str:
    if length.metres is None:
        text = f"{c.symbol('skip')} {_('not determined')}"
        if length.missing_input:
            text += c.muted("  " + _("(add {input})").format(input=length.missing_input))
        return text
    value = f"{length.metres:.2f} m"
    if length.input_uncertainty_m is not None:
        value += c.muted(
            "  "
            + _("±{uncertainty:.2f} m from the stated inputs only").format(
                uncertainty=length.input_uncertainty_m
            )
        )
    if length.validity is not Validity.VALID:
        value += "  " + validity_cell(c, length.validity)
    return value


def _placement(c: Console, placement: PlacementResult) -> list[str]:
    lines = c.section(
        _("Placement"),
        _("tier {tier}; no coordinates are derived (see the JSON)").format(tier=placement.tier),
    )
    assumed = _(" (assumed)") if placement.temperature_assumed else ""
    figures = (
        (_("Loudspeaker height"), placement.source_height_m),
        (_("Plane above the devices"), placement.ceiling_height_m),
        (_("Horizontal separation"), placement.horizontal_separation_m),
    )
    lines += c.fields(
        [
            (
                _("Speed of sound"),
                f"{placement.speed_of_sound_m_s:.1f} m/s "
                + _("at {temp:.0f} C").format(temp=placement.temperature_c)
                + assumed,
            ),
            *(
                ((name, _length_text(c, length)) for name, length in figures)
                if any(length.metres is not None for _name, length in figures)
                else [(_("Geometry"), _length_text(c, figures[0][1]))]
            ),
        ]
    )
    # The same reason often applies to every figure; say it once.
    reasons: dict[str, list[str]] = {}
    for name, length in figures:
        if length.reason:
            reasons.setdefault(localize(length.reason), []).append(name)
    for reason, names in reasons.items():
        prefix = "" if len(names) == len(figures) else ", ".join(names) + ": "
        lines += c.status("info", prefix + reason)
    named = [candidate for candidate in placement.candidates if candidate.surface]
    if named:
        lines.append("")
        lines += c.table(
            [_("Arrival"), _("Surface"), _("Excess path")],
            [
                [f"{cand.delay_ms:.1f} ms", str(cand.surface), f"{cand.excess_path_m:.2f} m"]
                for cand in named
            ],
            align="rlr",
        )
    for note in placement.notes:
        lines += c.status("info", localize(note))
    return lines


def _resonances(c: Console, result: AnalysisResult) -> list[str]:
    res = result.resonances
    lines = c.section(
        _("Low-frequency resonances"),
        _("candidates below {max_hz:.0f} Hz").format(max_hz=res.max_frequency_hz),
    )
    if not res.candidates:
        return lines + c.status("skip", _("None found."))
    rows = []
    for cand in res.candidates:
        decay = (
            f"{cand.narrowband_decay_20db_s * 1000:.0f} ms"
            if cand.narrowband_decay_20db_s is not None
            else c.dash()
        )
        ring = (
            f"{cand.filter_ringing_20db_s * 1000:.0f} ms"
            if cand.filter_ringing_20db_s is not None
            else c.dash()
        )
        rows.append(
            [
                f"{cand.frequency_hz:.1f} Hz",
                f"+{cand.level_above_baseline_db:.1f} dB",
                decay,
                ring,
                f"{c.symbol('ok')} {_('yes')}"
                if cand.decay_distinguishable
                else f"{c.symbol('skip')} {_('no')}",
            ]
        )
    return lines + c.table(
        [
            _("Frequency"),
            _("Above baseline"),
            _("20 dB decay"),
            _("Filter ringing"),
            _("Distinguishable"),
        ],
        rows,
        align="rrrrl",
    )


# --- Comparison ------------------------------------------------------------------


def render_comparison(
    console: Console,
    comparison: ComparisonResult,
    findings: Sequence[Finding] = (),
    profile_name: str = "generic",
) -> str:
    """Baseline against candidate: the sessions, "At a glance", every delta, findings."""
    c = console
    lines = c.title(_("ReverbScope comparison"))
    lines.append("")
    rows: list[tuple[str, str]] = []
    if comparison.baseline_session:
        rows.append((_("Baseline"), Verbatim(comparison.baseline_session)))
    if comparison.candidate_session:
        rows.append((_("Candidate"), Verbatim(comparison.candidate_session)))
    if comparison.common_band is not None:
        low, high = comparison.common_band
        rows.append((_("Common band"), f"{frequency_text(low)} – {frequency_text(high)}"))
    rows.append(
        (
            _("Comparable"),
            f"{c.symbol('ok')} {_('yes')}"
            if comparison.comparable
            else f"{c.symbol('error')} {_('no')}",
        )
    )
    lines += c.fields(rows)
    for note in comparison.notes:
        lines += c.status("info", localize(note))

    lines += comparison_at_a_glance(c, comparison)

    lines += _decay_deltas(c, comparison.decay)

    if comparison.frequency_response is not None:
        lines += c.section(_("Frequency response"), _("mean |Δ| per octave"))
        lines += c.table(
            [_("Band"), _("Mean |Δ|")],
            [[label, f"{mad:.2f} dB"] for label, mad in comparison.frequency_response.band_mad_db],
            align="lr",
        )
    if comparison.reflections:
        lines += c.section(_("Early reflections"))
        arrow = f" {c.arrow()} "
        rows_refl = []
        for match in comparison.reflections:
            if match.status == "matched":
                rows_refl.append(
                    [
                        _("matched"),
                        f"{match.baseline_delay_ms:.1f}{arrow}{match.candidate_delay_ms:.1f} ms",
                        f"{match.baseline_relative_db:.1f}{arrow}"
                        f"{match.candidate_relative_db:.1f} dB",
                    ]
                )
            elif match.status == "appeared":
                rows_refl.append(
                    [
                        _("appeared"),
                        f"{match.candidate_delay_ms:.1f} ms",
                        f"{match.candidate_relative_db:.1f} dB",
                    ]
                )
            else:
                rows_refl.append(
                    [
                        _("disappeared"),
                        f"{match.baseline_delay_ms:.1f} ms",
                        f"{match.baseline_relative_db:.1f} dB",
                    ]
                )
        lines += c.table([_("Status"), _("Delay"), _("Level")], rows_refl, align="lrr")
    if comparison.resonances:
        lines += c.section(_("Low-frequency resonances"))
        rows_res = []
        for res in comparison.resonances:
            base = f"{res.baseline_hz:.1f} Hz" if res.baseline_hz is not None else c.dash()
            cand = f"{res.candidate_hz:.1f} Hz" if res.candidate_hz is not None else c.dash()
            rows_res.append([_resonance_status(res.status), base, cand])
        lines += c.table([_("Status"), _("Baseline"), _("Candidate")], rows_res, align="lrr")
    if comparison.noise:
        lines += _noise_deltas(c, comparison.noise)
    for title, items in (
        (_("Placement"), comparison.placement),
        (_("Loopback"), comparison.loopback),
    ):
        if not items:
            continue
        lines += c.section(title)
        lines += _delta_statuses(c, items)
    lines += _findings(c, findings, profile_name)
    return c.fit("\n".join(lines))


#: Decay metrics of a comparison, in table order, with their short names.
_DECAY_METRICS = (
    ("edt", "EDT"),
    ("t20", "T20"),
    ("t30", "T30"),
    ("rt60_estimate", "RT60"),
    ("c50", "C50"),
    ("c80", "C80"),
    ("d50", "D50"),
    ("centre_time", "Ts"),
)


def _split_decay_name(name: str) -> tuple[str, str]:
    """``band.63 Hz.t20`` -> (``63 Hz``, ``T20``); ``broadband.edt`` -> (Broadband, EDT)."""
    for key, short in _DECAY_METRICS:
        if name.endswith("." + key):
            scope = name[: -len(key) - 1]
            if scope == "broadband":
                return band_text("broadband"), short
            return scope.removeprefix("band."), short
    return metric_label(name), ""


def _decay_deltas(c: Console, items: Sequence[MetricDelta]) -> list[str]:
    """Every decay delta, grouped by band: baseline, candidate, Δ, Δ % and a
    validity symbol (explained in the legend); reasons follow, each once."""
    lines = c.section(_("Reverberation"), _("a delta is valid only when both sides are valid"))
    rows = []
    seen: list[Validity] = []
    previous = ""
    for item in items:
        band, metric = _split_decay_name(item.name)
        base = f"{item.baseline:.3f}" if item.baseline is not None else c.dash()
        cand = f"{item.candidate:.3f}" if item.candidate is not None else c.dash()
        if item.validity is Validity.VALID and item.delta is not None:
            delta = f"{item.delta:+.3f}"
            pct = f"{item.delta_percent:+.1f} %" if item.delta_percent is not None else c.dash()
        else:
            delta = pct = c.dash()
        if item.validity not in seen:
            seen.append(item.validity)
        rows.append(
            [
                "" if band == previous else band,
                metric,
                base,
                cand,
                delta,
                pct,
                c.symbol(validity_status(item.validity)),
            ]
        )
        previous = band
    headers = [_("Band"), _("Metric"), _("Baseline"), _("Candidate"), "Δ", "Δ %", ""]
    align = "llrrrrl"
    if not c.fits(headers, rows, gap=2):
        # A narrow terminal drops the absolute delta (baseline and candidate
        # are both shown) before the table has to fall apart into blocks.
        headers, align = headers[:4] + headers[5:], align[:4] + align[5:]
        rows = [row[:4] + row[5:] for row in rows]
    lines += c.table(headers, rows, align=align, gap=2, title_columns=2)
    if seen:
        legend = [
            f"{c.symbol(validity_status(v))} {validity_word(v)}"
            for v in sorted(seen, key=list(Validity).index)
        ]
        lines.append("")
        lines.append("  " + "   ".join(legend))
    return lines + _reasons(c, items)


def _resonance_status(status: str) -> str:
    return {
        "matched": _("matched"),
        "appeared": _("appeared"),
        "disappeared": _("disappeared"),
    }.get(status, status)


def _noise_label(name: str) -> str:
    """``noise.rms_dbfs`` -> Broadband; ``noise.band.1000Hz`` -> ``1 kHz``."""
    band = name.removeprefix("noise.band.")
    if band != name and band.endswith("Hz"):
        try:
            return frequency_text(float(band[:-2]))
        except ValueError:
            return band
    if name == "noise.rms_dbfs":
        return band_text("broadband")
    return metric_label(name)


def _noise_deltas(c: Console, items: Sequence[MetricDelta]) -> list[str]:
    """Background noise per band: baseline, candidate (dBFS) and the change (dB)."""
    lines = c.section(_("Background noise"), _("dBFS RMS; a change needs the same input gain"))
    rows = []
    for item in items:
        base = f"{item.baseline:.1f}" if item.baseline is not None else c.dash()
        cand = f"{item.candidate:.1f}" if item.candidate is not None else c.dash()
        delta = (
            f"{item.delta:+.1f} dB"
            if item.validity is Validity.VALID and item.delta is not None
            else c.dash()
        )
        rows.append(
            [
                _noise_label(item.name),
                base,
                cand,
                delta,
                validity_cell(c, item.validity),
            ]
        )
    lines += c.table(
        [_("Band"), _("Baseline"), _("Candidate"), "Δ", _("Validity")], rows, align="lrrrl"
    )
    return lines + _reasons(c, items, label=_noise_label)


def _reasons(c: Console, items: Sequence[MetricDelta], *, label: Any = metric_label) -> list[str]:
    """Why deltas were not computed: each reason once, with the metrics it covers."""
    grouped: dict[str, list[str]] = {}
    for item in items:
        if item.reason and item.validity is not Validity.VALID:
            grouped.setdefault(localize(item.reason), []).append(label(item.name))
    lines: list[str] = []
    if grouped:
        lines.append("")
    for reason, names in grouped.items():
        lines += c.status("skip", ", ".join(names), detail=reason)
    return lines


def _delta_statuses(c: Console, items: Sequence[MetricDelta]) -> list[str]:
    """Deltas as status lines; metrics that share a validity and a reason share a line."""
    grouped: dict[tuple[Validity, str], list[MetricDelta]] = {}
    for item in items:
        grouped.setdefault((item.validity, item.reason or ""), []).append(item)
    lines: list[str] = []
    for (validity, reason), members in grouped.items():
        if validity is Validity.VALID:
            for item in members:
                lines += c.status("ok", _delta_text(c, item))
            continue
        names = ", ".join(metric_label(item.name) for item in members)
        lines += c.status(
            validity_status(validity),
            f"{names}: {validity_word(validity)}",
            detail=localize(reason) if reason else "",
        )
    return lines


def _delta_text(c: Console, item: MetricDelta) -> str:
    unit = f" {item.unit}" if item.unit else ""
    base = f"{item.baseline:.2f}" if item.baseline is not None else c.dash()
    cand = f"{item.candidate:.2f}" if item.candidate is not None else c.dash()
    text = f"{metric_label(item.name)}: {base} {c.arrow()} {cand}{unit}"
    if item.delta is not None:
        text += f" ({item.delta:+.2f}{unit})"
    return text


def comparison_at_a_glance(c: Console, comparison: ComparisonResult) -> list[str]:
    """Baseline against candidate, one line per topic; the symbol says whether
    the topic could be compared, never whether the change is good."""
    rows: list[tuple[str, str]] = []
    arrow = f" {c.arrow()} "

    def row(label: str, status: Status, text: str) -> None:
        rows.append((label, f"{c.symbol(status)} {glue_units(text)}"))

    rt = next((d for d in comparison.decay if d.name == "broadband.rt60_estimate"), None)
    if (
        rt is not None
        and rt.validity is Validity.VALID
        and rt.baseline is not None
        and rt.candidate is not None
    ):
        text = f"RT60 {rt.baseline:.2f} s{arrow}{rt.candidate:.2f} s"
        if rt.delta_percent is not None:
            text += f" ({rt.delta_percent:+.1f} %)"
        row(_("Reverberation"), "ok", text)
    else:
        row(_("Reverberation"), "unsure", _("broadband RT60 not comparable (see Reverberation)"))

    c50 = next((d for d in comparison.decay if d.name == "broadband.c50"), None)
    c80 = next((d for d in comparison.decay if d.name == "broadband.c80"), None)
    if (
        c50 is not None
        and c50.validity is Validity.VALID
        and c50.baseline is not None
        and c50.candidate is not None
    ):
        text = f"C50 {c50.baseline:+.1f} dB{arrow}{c50.candidate:+.1f} dB"
        if (
            c80 is not None
            and c80.validity is Validity.VALID
            and c80.baseline is not None
            and c80.candidate is not None
        ):
            text += c.sep() + f"C80 {c80.baseline:+.1f} dB{arrow}{c80.candidate:+.1f} dB"
        row(_("Clarity"), "ok", text)

    if comparison.reflections:
        counts = {"matched": 0, "appeared": 0, "disappeared": 0}
        for match in comparison.reflections:
            counts[match.status] = counts.get(match.status, 0) + 1
        row(
            _("Early reflections"),
            "ok",
            _("{gone} gone{sep}{new} new{sep}{kept} at both").format(
                gone=counts["disappeared"],
                new=counts["appeared"],
                kept=counts["matched"],
                sep=c.sep(),
            ),
        )
    else:
        row(_("Early reflections"), "ok", _("none above the threshold on either side"))

    parts: list[str] = []
    for status, label in (
        ("matched", _("at both: {list}")),
        ("disappeared", _("gone: {list}")),
        ("appeared", _("new: {list}")),
    ):
        found = [
            f"{(r.candidate_hz if r.candidate_hz is not None else r.baseline_hz):.0f} Hz"
            for r in comparison.resonances
            if r.status == status
        ]
        if found:
            parts.append(label.format(list=", ".join(found)))
    row(_("Low end"), "ok", "; ".join(parts) if parts else _("no potential resonance"))

    rms = next((d for d in comparison.noise if d.name == "noise.rms_dbfs"), None)
    if rms is not None and rms.baseline is not None and rms.candidate is not None:
        text = f"{rms.baseline:.1f}{arrow}{rms.candidate:.1f} dBFS"
        if rms.validity is Validity.VALID and rms.delta is not None:
            row(_("Noise floor"), "ok", text + f" ({rms.delta:+.1f} dB)")
        else:
            text += c.sep() + _("not compared: {validity}").format(
                validity=validity_word(rms.validity)
            )
            if not comparison.settings.get("same_input_gain", False):
                text += c.sep() + _("add --same-input-gain if the input gain was unchanged")
            row(_("Noise floor"), validity_status(rms.validity), text)
    else:
        row(_("Noise floor"), "skip", _("no quiet segment on one or both sides"))

    fr = comparison.frequency_response
    if fr is not None and fr.band_mad_db:
        band, mad = max(fr.band_mad_db, key=lambda item: item[1])
        row(
            _("Frequency response"),
            "ok",
            _("largest change in the {band} octave, {mad:.1f} dB mean |Δ|").format(
                band=band, mad=mad
            ),
        )
    return c.section(_("At a glance")) + c.fields(rows, min_label=_glance_label_width())


# --- Environment report -------------------------------------------------------------


def _edition_name(edition: str) -> str:
    if edition == "developer":
        return pgettext("edition", "developer")
    if edition == "user":
        return pgettext("edition", "user")
    return edition


def render_environment(console: Console, report: dict[str, Any]) -> str:
    """``reverbscope doctor``: sections a maintainer can read in a GitHub issue."""
    from reverbscope.diagnostics import privacy_note

    c = console
    lines = c.title(_("ReverbScope environment report"))
    build = report.get("build") or {}
    terminal = build.get("package") == "terminal"
    if terminal:
        edition = _("Terminal Edition")
    elif build.get("package") == "desktop" or report.get("frozen_bundle"):
        edition = _("Desktop Edition")
    else:
        edition = _("source or pip install")
    tools = _("shown") if report["edition"] == "developer" else _("hidden")
    rows = [
        (_("Version"), str(report["reverbscope"])),
        (_("Edition"), edition),
        (_("Developer tools"), tools),
        (
            _("Build"),
            build["commit"]
            if build.get("commit")
            else _("no commit recorded (source or pip install)"),
        ),
    ]
    if build.get("ci_run"):
        rows.append((_("CI run"), Verbatim(build["ci_run"])))
    lines += c.section("ReverbScope") + c.fields(rows)

    lines += c.section(_("System"))
    lines += c.fields(
        [
            (_("Platform"), str(report["platform"])),
            (_("Architecture"), str(report["machine"])),
            ("Python", f"{report['python']} ({report['implementation']})"),
            (_("Language"), str(report["language"])),
        ]
    )

    lines += c.section(_("Libraries"))
    # The Terminal Edition is built without the GUI and its charts.
    gui_only = {"matplotlib", "PySide6_Essentials", "shiboken6"}
    packages = [
        (
            name,
            found
            or (
                _("not included (Terminal Edition)")
                if terminal and name in gui_only
                else _("not installed")
            ),
        )
        for name, found in report["packages"].items()
    ]
    packages.append(("libsndfile", report.get("libsndfile") or _("unknown")))
    lines += c.fields(packages)

    lines += c.section(_("Settings"))
    lines += c.fields(
        (key, c.dash() if value in ("", None) else str(value))
        for key, value in report.get("settings", {}).items()
    )
    lines += c.section(_("Paths"), _("your home folder is shown as ~"))
    lines += c.fields((key, Verbatim(str(value))) for key, value in report["paths"].items())

    lines += c.section(_("Self-check"))
    callbacks = report.get("audio_callbacks")
    if callbacks is None:
        lines += c.status("skip", _("Audio callbacks: not checked"))
    elif callbacks == "ok":
        lines += c.status("ok", _("Audio callbacks: ok"))
    else:
        lines += c.status(
            "error", _("Audio callbacks: {status}").format(status=localize(str(callbacks)))
        )

    audio = report.get("audio", {})
    lines += c.section(_("Audio"))
    if "error" in audio:
        lines += c.status(
            "error", _("unavailable: {error}").format(error=localize(str(audio["error"])))
        )
    else:
        devices = audio.get("devices", [])
        default_in = next(
            (p["device"]["name"] for p in devices if p["device"].get("is_default_input")), None
        )
        default_out = next(
            (p["device"]["name"] for p in devices if p["device"].get("is_default_output")), None
        )
        apis = ", ".join(
            f"{api['name']} ({api['device_count']})" for api in audio.get("host_apis", [])
        )
        lines += c.fields(
            [
                (pgettext("environment report", "backend"), str(audio.get("backend"))),
                ("PortAudio", audio.get("portaudio_version") or c.dash()),
                (pgettext("environment report", "host APIs"), apis or c.dash()),
                (pgettext("environment report", "devices"), str(len(devices))),
                (pgettext("environment report", "default input"), default_in or c.dash()),
                (pgettext("environment report", "default output"), default_out or c.dash()),
            ]
        )
        for note in audio.get("notes", []):
            lines += c.status("info", localize(note))
        probed = bool(audio.get("rates_probed"))
        lines += c.section(
            _("Devices"),
            _("sample rates accepted for 1 channel; nothing was played")
            if probed
            else _("sample rates not probed; run reverbscope doctor --probe"),
        )
        lines += _device_rows(c, devices, probed)

    lines += c.section(_("Privacy"))
    lines += c.status("ok", _("Nothing was sent anywhere: this report is only printed."))
    lines += c.status("warn", privacy_note())
    return c.fit("\n".join(lines))


def _default_marks(device: dict[str, Any], *, short: bool = False) -> str:
    """Which system default the device is ("Input, Output" under a Default column)."""
    marks = []
    if device.get("is_default_input"):
        marks.append(_("Input") if short else pgettext("environment report", "default input"))
    if device.get("is_default_output"):
        marks.append(_("Output") if short else pgettext("environment report", "default output"))
    return ", ".join(marks)


def _recommended(probe: dict[str, Any]) -> str:
    rec_in, rec_out = bool(probe.get("recommended_input")), bool(probe.get("recommended_output"))
    if rec_in and rec_out:
        return _("recommended input + output")
    if rec_in:
        return _("recommended input")
    if rec_out:
        return _("recommended output")
    return ""


def _device_rows(c: Console, probes: Sequence[dict[str, Any]], probed: bool) -> list[str]:
    """Devices as a table, or one block per device when the rates were probed."""
    if not probes:
        return c.status("skip", _("No audio device found."))
    if not probed:
        rows = []
        for probe in probes:
            device = probe["device"]
            rows.append(
                [
                    str(device["index"]),
                    device["name"],
                    device["host_api"],
                    str(device["max_input_channels"] or c.dash()),
                    str(device["max_output_channels"] or c.dash()),
                    rate_text(device["default_sample_rate"]),
                    _default_marks(device, short=True),
                ]
            )
        return c.table(
            ["#", _("Device"), _("Host API"), _("In"), _("Out"), _("Rate"), _("Default")],
            rows,
            align="lllrrrl",
            title_columns=2,
        )
    lines: list[str] = []
    for number, probe in enumerate(probes):
        device = probe["device"]
        if number:
            lines.append("")
        lines += c.paragraph(f"[{device['index']}] {device['name']}", indent=2, style=("bold",))
        recommended = _recommended(probe)
        if recommended:
            lines += c.status("ok", recommended, indent=6)
        facts = [
            device["host_api"],
            _("{inputs} in / {outputs} out").format(
                inputs=device["max_input_channels"], outputs=device["max_output_channels"]
            ),
            _("default {rate}").format(rate=rate_text(device["default_sample_rate"])),
        ]
        marks = _default_marks(device)
        if marks:
            facts.append(marks)
        lines += c.paragraph(c.sep().join(facts), indent=6)
        rate_rows: list[tuple[str, str]] = []
        if device["max_input_channels"] > 0:
            rate_rows.append((_("Record"), rates_text(probe.get("input_rates", []), c)))
        if device["max_output_channels"] > 0:
            rate_rows.append((_("Play"), rates_text(probe.get("output_rates", []), c)))
        lines += c.fields(rate_rows, indent=6)
        for note in probe.get("notes", []):
            lines += c.status("info", localize(note), indent=6)
    return lines


# --- Devices ---------------------------------------------------------------------------


def render_devices(console: Console, devices: Sequence[DeviceInfo]) -> str:
    """``reverbscope devices``: one row per device."""
    payload = [
        {
            "device": {
                "index": d.index,
                "name": d.name,
                "host_api": d.host_api,
                "max_input_channels": d.max_input_channels,
                "max_output_channels": d.max_output_channels,
                "default_sample_rate": d.default_sample_rate,
                "is_default_input": d.is_default_input,
                "is_default_output": d.is_default_output,
            }
        }
        for d in devices
    ]
    lines = console.title(_("Audio devices"))
    lines.append("")
    lines += _device_rows(console, payload, probed=False)
    lines.append("")
    lines += console.paragraph(
        _("Use the number with --input-device / --output-device."), style=("dim",)
    )
    return console.fit("\n".join(lines))


def render_inventory(console: Console, inventory: DeviceInventory) -> str:
    """``reverbscope devices --probe``: every device with the rates it accepts."""
    data = inventory.to_dict()
    lines = console.title(_("Audio devices"))
    if inventory.portaudio_version:
        lines.append("")
        lines += console.fields([("PortAudio", inventory.portaudio_version)])
    lines += console.section(
        _("Devices"),
        _("sample rates accepted for 1 channel; nothing was played")
        if data.get("rates_probed")
        else "",
    )
    lines += _device_rows(console, data.get("devices", []), bool(data.get("rates_probed")))
    for note in inventory.notes:
        lines += console.status("info", localize(note))
    return console.fit("\n".join(lines))


def render_host_apis(console: Console, inventory: DeviceInventory) -> str:
    lines = console.title(_("Audio systems (host APIs)"))
    if inventory.portaudio_version:
        lines.append("")
        lines += console.fields([("PortAudio", inventory.portaudio_version)])
    lines.append("")
    rows = [
        [
            str(api.index),
            api.name,
            str(api.device_count),
            console.dash() if api.rank is None else str(api.rank + 1),
        ]
        for api in inventory.host_apis
    ]
    lines += console.table(
        ["#", _("Host API"), _("Devices"), _("Preference")], rows, align="llrr", title_columns=2
    )
    for api in inventory.host_apis:
        if api.note:
            lines += console.status("info", f"{api.name}: {localize(api.note)}")
    return console.fit("\n".join(lines))


# --- Sweep -----------------------------------------------------------------------------


def render_sweep_written(
    console: Console, settings: SweepSettings, wav_path: object, sidecar: object
) -> str:
    c = console
    lines = c.title(_("ReverbScope test signal"))
    lines.append("")
    lines += c.status("ok", Verbatim(_("Wrote {path}").format(path=wav_path)))
    lines += c.fields(
        [
            (
                _("Length"),
                _("{seconds:.1f} s at {rate}").format(
                    seconds=settings.total_samples / settings.sample_rate,
                    rate=rate_text(settings.sample_rate),
                ),
            ),
            (
                _("Sweep"),
                f"{frequency_text(settings.start_hz)} – {frequency_text(settings.end_hz)}"
                f"{c.sep()}{settings.duration_s:g} s{c.sep()}{settings.level_dbfs:g} dBFS",
            ),
        ],
        indent=4,
    )
    lines += c.status(
        "ok",
        Verbatim(_("Wrote {path}").format(path=sidecar)),
        detail=_("Keep it next to the WAV: the analysis rebuilds the exact sweep from it."),
    )
    lines += c.section(_("Next steps"))
    lines += c.steps(
        [
            (
                _("Import {name} into your DAW and play it through the monitors.").format(
                    name=Path(str(wav_path)).name
                ),
                "",
            ),
            (_("Record the measurement microphone on another track at the same sample rate."), ""),
            (
                _("Export that track as WAV (no trimming needed) and analyse it:"),
                shell_command(
                    [
                        "reverbscope",
                        "analyze",
                        "--recording",
                        _("<take.wav>"),
                        "--sweep",
                        str(wav_path),
                        "--out",
                        _("<session>"),
                    ]
                ),
            ),
        ]
    )
    lines += c.paragraph(
        _("Start with the monitors turned down and raise them between takes if needed."),
        style=("dim",),
    )
    return c.fit("\n".join(lines))


def render_saved_next_steps(console: Console, session: object) -> str:
    """After a saved analysis: where the session is and what to do with it."""
    c = console
    lines = c.status("ok", Verbatim(_("Saved session to {path}").format(path=session)), indent=0)
    lines += c.section(_("Next steps"))
    lines += c.steps(
        [
            (
                _("Measure another position into a new folder, then compare the two:"),
                shell_command(["reverbscope", "compare", str(session), _("<other-session>")]),
            ),
            (
                (_("To see it with charts, get ReverbScope Desktop Edition:"), RELEASES_URL)
                if is_terminal_package()
                else (_("Open the session in the desktop app:"), "reverbscope gui")
            ),
        ]
    )
    return c.fit("\n".join(lines))


# --- Measure ---------------------------------------------------------------------------


def _find(devices: Sequence[DeviceInfo], index: int | None, default_attr: str) -> DeviceInfo | None:
    if index is not None:
        return next((d for d in devices if d.index == index), None)
    return next((d for d in devices if getattr(d, default_attr)), None)


def render_measure_plan(
    console: Console,
    *,
    devices: Sequence[DeviceInfo],
    input_device: int | None,
    output_device: int | None,
    input_channels: Sequence[int],
    loopback_channel: int | None,
    output_channel: int,
    settings: SweepSettings,
    backend: str,
    options: Any,
    clock_warning: str | None,
    safe_max_level: float,
) -> str:
    """The devices a take will use and the checks that passed before it plays."""
    c = console
    inp = _find(devices, input_device, "is_default_input")
    out = _find(devices, output_device, "is_default_output")
    lines = c.title(_("ReverbScope standalone measurement"))

    def device_text(device: DeviceInfo | None, fallback: str) -> str:
        return f"[{device.index}] {device.name}" if device is not None else fallback

    microphone = [ch for ch in input_channels if ch != loopback_channel]
    in_text = device_text(inp, _("system default")) + c.sep()
    in_text += _("input {channels}").format(channels=", ".join(str(ch) for ch in microphone))
    if loopback_channel is not None:
        in_text += c.sep() + _("loopback on input {channel}").format(channel=loopback_channel)
    out_text = device_text(out, _("system default")) + c.sep()
    out_text += _("output {channel}").format(channel=output_channel)
    rows = [(_("Input"), in_text), (_("Output"), out_text)]
    api = inp.host_api if inp is not None else (out.host_api if out is not None else backend)
    rows.append((_("Host API"), api))
    rows.append((_("Sample rate"), rate_text(settings.sample_rate)))
    rows.append((_("Level"), f"{settings.level_dbfs:g} dBFS"))
    rows.append(
        (
            _("Sweep"),
            f"{settings.duration_s:g} s{c.sep()}{frequency_text(settings.start_hz)} – "
            f"{frequency_text(settings.end_hz)}",
        )
    )
    stream = []
    if getattr(options, "latency", None):
        stream.append(_("latency {latency}").format(latency=options.latency))
    if getattr(options, "wasapi_exclusive", False):
        stream.append(_("WASAPI exclusive mode"))
    if getattr(options, "coreaudio_change_device_rate", False):
        stream.append(_("sets the Core Audio device rate"))
    if stream:
        rows.append((_("Stream"), c.sep().join(stream)))
    lines.append("")
    lines += c.fields(rows)

    lines += c.section(_("Checks"), _("nothing has been played yet"))
    lines += c.status("ok", _("Input and output use one host API"))
    lines += c.status("ok", _("The selected channels exist"))
    for kind, device in (("input", inp), ("output", out)):
        if device is None:
            continue
        text = (
            _("The input device accepts {rate}")
            if kind == "input"
            else _("The output device accepts {rate}")
        )
        lines += c.status("ok", text.format(rate=rate_text(settings.sample_rate)))
    if settings.level_dbfs > safe_max_level:
        lines += c.status(
            "warn",
            _("Level above {max_level:g} dBFS, confirmed with --acknowledge-level").format(
                max_level=safe_max_level
            ),
        )
    else:
        lines += c.status(
            "ok",
            _("Level at or below {max_level:g} dBFS").format(max_level=safe_max_level),
        )
    if clock_warning:
        lines += c.status("warn", localize(clock_warning))
    return c.fit("\n".join(lines))


# --- Messages on stderr ------------------------------------------------------------------


def render_error(
    console: Console, message: str, *, detail: str = "", hints: Sequence[str] = ()
) -> str:
    """``× error: message``, an optional explanation, and commands to try.

    ::

        × error: file not found: take.wav

          Try:
            reverbscope analyze --help
    """
    c = console
    text = _("error: {message}").format(message=message)
    if c.unicode:
        lines = c.status("error", text, indent=0, style=("red", "bold"))
    else:  # "[ERROR] error:" would say it twice
        lines = c.paragraph(text, indent=0)
    if detail:
        lines += c.paragraph(detail, indent=2)
    if hints:
        lines.append("")
        lines.append("  " + _("Try:"))
        lines += ["    " + c.command(hint) for hint in hints]
    return c.fit("\n".join(lines))


def render_status(console: Console, kind: Status, text: str, *, keep: bool = False) -> str:
    """One status line at the left margin (warnings, stops, saved files).

    ``keep`` prints the line whole (it names a path the user may copy).
    """
    if keep:
        text = Verbatim(text)
    if not console.unicode and kind in ("warn", "error"):
        # The text starts with its own word ("warning:"); "[WARN]" would repeat it.
        return text if keep else "\n".join(console.paragraph(text, indent=0))
    return console.fit("\n".join(console.status(kind, text, indent=0)))


# --- Home screen -------------------------------------------------------------------------


def render_home(console: Console, version: str, *, terminal_edition: bool = False) -> str:
    """Bare ``reverbscope``: what it is, three ways in, and where the rest is.

    The Terminal Edition has no GUI, so it offers ``doctor`` instead of ``gui``.
    """
    c = console
    name = "ReverbScope" + (" " + _("Terminal Edition") if terminal_edition else "")
    lines = [c.bold(name) + " " + c.muted(version)]
    lines += c.paragraph(
        _(
            "Measure and compare the rooms you record in: reverberation, early reflections, "
            "low-frequency resonances and noise, from any DAW."
        ),
        indent=0,
    )
    lines.append("")
    lines += c.commands(
        [
            ("reverbscope demo", _("Try it with synthetic data; no audio interface needed")),
            (
                ("reverbscope doctor", _("Check this computer's audio setup"))
                if terminal_edition
                else ("reverbscope gui", _("Open the desktop app"))
            ),
            ("reverbscope sweep --out sweep.wav", _("Write the test signal to play from your DAW")),
        ]
    )
    lines.append("")
    lines += c.paragraph(
        _("Run {command} for every command and option.").format(command="reverbscope --help"),
        indent=0,
        style=("dim",),
    )
    return c.fit("\n".join(lines))


# --- Demo ----------------------------------------------------------------------------------


def demo_position_text(key: str, fallback: str) -> str:
    """A demo position's description in the active language (session.json keeps English)."""
    return {
        "position-a": _("close to the desk and the side wall"),
        "position-b": _("moved 1 m back from the desk"),
    }.get(key, fallback)


def render_demo(
    console: Console,
    run: DemoRun,
    findings: Sequence[Sequence[Finding]],
    *,
    gui_available: bool,
    terminal_edition: bool = False,
) -> str:
    """``reverbscope demo``: what was simulated, what the analysis found, what next."""
    c = console
    settings = run.settings
    lines = c.title(_("ReverbScope demo"))
    lines.append("")
    lines += c.status(
        "warn",
        _("Synthetic data: a simulated room, not a measurement."),
        style=("bold",),
        detail=_(
            "No audio device was used and nothing was played. The numbers below describe "
            "the simulation; every session is marked as a synthetic demo."
        ),
    )

    lines += c.section(_("Files written"))
    rows: list[tuple[str, str]] = [
        (_("Test signal"), Verbatim(str(run.sweep_path))),
    ]
    for take in run.takes:
        rows.append(
            (
                _("Position {label}").format(label=take.position.label),
                Verbatim(str(take.session_dir)),
            )
        )
    rows.append((_("Comparison"), Verbatim(str(run.comparison_path))))
    lines += c.fields(rows)
    lines += c.paragraph(
        _("{duration:g} s sweep{sep}{start} – {end}{sep}{rate}").format(
            duration=settings.duration_s,
            sep=c.sep(),
            start=frequency_text(settings.start_hz),
            end=frequency_text(settings.end_hz),
            rate=rate_text(settings.sample_rate),
        ),
        style=("dim",),
    )

    for take, take_findings in zip(run.takes, findings, strict=True):
        glance = at_a_glance(c, take.result, take_findings)
        title = _("Position {label}").format(label=take.position.label)
        description = demo_position_text(take.position.key, take.position.description)
        # The glance block's own heading is replaced by the position's.
        lines += c.section(title, description) + glance[2:]

    first, second = run.takes[0], run.takes[1]
    glance = comparison_at_a_glance(c, run.comparison)
    lines += (
        c.section(
            _("Comparison {a} {arrow} {b}").format(
                a=first.position.label, b=second.position.label, arrow=c.arrow()
            )
        )
        + glance[2:]
    )

    lines += c.section(_("What the demo shows"))
    for text in (
        _("A strong desk reflection at 2.4 ms at position A is gone at position B."),
        _("The 110 Hz room mode stays at both positions: it belongs to the room, not the spot."),
        _("Mains hum at 50 Hz is clearly lower at position B."),
    ):
        lines += c.status("info", text)

    lines += c.section(_("Next steps"))
    if gui_available:
        gui_step = (_("Open the sessions in the desktop app:"), "reverbscope gui")
    elif terminal_edition:
        gui_step = (_("To see them with charts, get ReverbScope Desktop Edition:"), RELEASES_URL)
    else:
        gui_step = (
            _("Open them in the desktop app (download it, or add PySide6 to this Python):"),
            'pip install "PySide6_Essentials>=6.6"',
        )
    lines += c.steps(
        [
            (
                _("Read the full report of one position:"),
                shell_command(["reverbscope", "show", str(first.session_dir)]),
            ),
            (
                _("See every delta between the two positions:"),
                shell_command(
                    [
                        "reverbscope",
                        "compare",
                        str(first.session_dir),
                        str(second.session_dir),
                        "--same-input-gain",
                    ]
                ),
            ),
            gui_step,
            (
                _("Measure your own room: write the test signal for your DAW."),
                "reverbscope sweep --out sweep.wav",
            ),
        ]
    )
    return c.fit("\n".join(lines))


def render_terminal_edition_gui(console: Console) -> str:
    """``reverbscope gui`` in the Terminal Edition: which download has the GUI."""
    c = console
    lines = c.status(
        "info",
        _("This is the Terminal Edition of ReverbScope. Install the Desktop Edition to use the GUI."),
        indent=0,
    )
    lines += c.paragraph(
        _("Every command-line feature works here: reverbscope --help lists them."), indent=2
    )
    lines.append("")
    lines.append("  " + _("Download:"))
    lines.append("    " + c.command(RELEASES_URL))
    return c.fit("\n".join(lines))
