"""What the command line prints, laid out through :mod:`roomscope.cli.console`.

The GUI keeps its own plain-text reports (:mod:`roomscope.cli.report`,
:func:`roomscope.diagnostics.format_environment_report`); these renderers read
the same models and add structure for a terminal: sections, aligned fields,
tables, and a symbol with every status. Stored diagnostics are shown with
:func:`~roomscope.i18n.localize`; nothing here changes a stored value.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from roomscope.cli.console import Console, Status
from roomscope.i18n import _, localize, pgettext
from roomscope.interpretation import Finding
from roomscope.interpretation.profiles import (
    band_text,
    confidence_text,
    noise_segment_text,
    profile_title,
)
from roomscope.labels import metric_label, topic_text, validity_word
from roomscope.models.comparison import ComparisonResult
from roomscope.models.result import (
    AnalysisResult,
    DecayMetric,
    PlacementLength,
    PlacementResult,
    Validity,
)

if TYPE_CHECKING:
    from roomscope.audio.backend import DeviceInfo
    from roomscope.audio.inventory import DeviceInventory
    from roomscope.models.configuration import SweepSettings


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
    """The report of one analysis: overview, results by topic, findings."""
    c = console
    ir = result.impulse_response
    lines = c.title(_("RoomScope analysis"))

    lines += c.section(_("Input"))
    lines += c.fields(
        [
            *inputs,
            (_("Sample rate"), rate_text(result.sample_rate)),
            (_("Created"), created_text(result.created_at)),
        ]
    )

    lines += _summary(c, result)

    lines += c.section(_("Impulse response"))
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

    lines += _reverberation(c, result)
    lines += _noise(c, result)
    lines += _reflections(c, result)
    if result.placement is not None:
        lines += _placement(c, result.placement)
    lines += _resonances(c, result)

    if result.warnings:
        lines += c.section(_("Warnings"))
        for warning in result.warnings:
            lines += c.status("warn", localize(warning))
    lines += _findings(c, findings, profile_name)
    return "\n".join(lines)


def _summary(c: Console, result: AnalysisResult) -> list[str]:
    broadband = result.decay.broadband
    rows: list[tuple[str, str]] = []
    if broadband.rt60_estimate_s is not None:
        rows.append(
            (
                _("RT60 estimate"),
                f"{c.symbol('ok')} {broadband.rt60_estimate_s:.2f} s"
                + c.muted(f"  ({broadband.rt60_basis})"),
            )
        )
    else:
        rows.append((_("RT60 estimate"), f"{c.symbol('skip')} {_('not computed')}"))
    for name, metric in (("EDT", broadband.edt), ("T20", broadband.t20), ("T30", broadband.t30)):
        if metric.seconds is not None and metric.validity is Validity.VALID:
            value = f"{c.symbol('ok')} {metric.seconds:.2f} s"
        elif metric.seconds is not None and metric.validity is Validity.UNRELIABLE:
            value = f"{c.symbol('unsure')} {metric.seconds:.2f} s  {validity_word(metric.validity)}"
        else:
            value = validity_cell(c, metric.validity)
        rows.append((name, value))
    noise = result.noise
    if noise.rms_dbfs is not None:
        rows.append((_("Background noise"), f"{noise.rms_dbfs:.1f} dBFS RMS"))
    reflections = result.reflections.reflections
    if reflections:
        strongest = max(reflections, key=lambda r: r.relative_db)
        rows.append(
            (
                _("Early reflections"),
                _("{count} found{sep}strongest {delay:.1f} ms, {level:.1f} dB").format(
                    count=len(reflections),
                    sep=c.sep(),
                    delay=strongest.delay_ms,
                    level=strongest.relative_db,
                ),
            )
        )
    else:
        rows.append((_("Early reflections"), _("none above the threshold")))
    rows.append(
        (
            _("Warnings"),
            f"{c.symbol('warn')} {len(result.warnings)}"
            if result.warnings
            else f"{c.symbol('ok')} {_('none')}",
        )
    )
    return c.section(_("Summary"), _("broadband")) + c.fields(rows)


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
    lines += c.table(
        [_("Band"), "EDT", "T20", "T30", "RT60", _("Decay range")],
        rows,
        align="lrrrrr",
    )
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
            *((name, _length_text(c, length)) for name, length in figures),
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
    c = console
    lines = c.title(_("RoomScope comparison"))
    lines += c.section(_("Sessions"))
    rows = []
    if comparison.baseline_session:
        rows.append((_("Baseline"), comparison.baseline_session))
    if comparison.candidate_session:
        rows.append((_("Candidate"), comparison.candidate_session))
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

    lines += c.section(_("Decay"), _("a delta is valid only when both sides are valid"))
    table_rows = []
    reasons: list[str] = []
    for item in comparison.decay:
        base = f"{item.baseline:.3f}" if item.baseline is not None else c.dash()
        cand = f"{item.candidate:.3f}" if item.candidate is not None else c.dash()
        if item.validity is Validity.VALID and item.delta is not None:
            delta = f"{item.delta:+.3f}"
            pct = f"{item.delta_percent:+.1f} %" if item.delta_percent is not None else c.dash()
        else:
            delta = pct = c.dash()
        table_rows.append(
            [metric_label(item.name), base, cand, delta, pct, validity_cell(c, item.validity)]
        )
        if item.reason and item.validity is not Validity.VALID:
            reasons.append(f"{metric_label(item.name)}: {localize(item.reason)}")
    lines += c.table(
        [_("Metric"), _("Baseline"), _("Candidate"), "Δ", "Δ %", _("Validity")],
        table_rows,
        align="lrrrrl",
    )
    if reasons:
        lines.append("")
        for reason in reasons:
            lines += c.status("skip", reason)

    if comparison.frequency_response is not None:
        lines += c.section(_("Frequency response"), _("mean |Δ| per octave"))
        lines += c.table(
            [_("Band"), _("Mean |Δ|")],
            [[label, f"{mad:.2f} dB"] for label, mad in comparison.frequency_response.band_mad_db],
            align="lr",
        )
    if comparison.reflections:
        lines += c.section(_("Early reflections"))
        rows_refl = []
        for match in comparison.reflections:
            if match.status == "matched":
                rows_refl.append(
                    [
                        _("matched"),
                        f"{match.baseline_delay_ms:.1f} → {match.candidate_delay_ms:.1f} ms",
                        f"{match.baseline_relative_db:.1f} → {match.candidate_relative_db:.1f} dB",
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
    for title, items in ((_("Noise"), comparison.noise), (_("Placement"), comparison.placement)):
        if not items:
            continue
        lines += c.section(title)
        for item in items:
            lines += c.status(
                validity_status(item.validity),
                f"{metric_label(item.name)}: {validity_word(item.validity)}",
                detail=localize(item.reason) if item.reason else "",
            )
    lines += _findings(c, findings, profile_name)
    return "\n".join(lines)


# --- Environment report -------------------------------------------------------------


def _edition_name(edition: str) -> str:
    if edition == "developer":
        return pgettext("edition", "developer")
    if edition == "user":
        return pgettext("edition", "user")
    return edition


def render_environment(console: Console, report: dict[str, Any]) -> str:
    """``roomscope doctor``: sections a maintainer can read in a GitHub issue."""
    from roomscope.diagnostics import privacy_note

    c = console
    lines = c.title(_("RoomScope environment report"))
    build = report.get("build") or {}
    edition = _edition_name(report["edition"])
    if report.get("frozen_bundle"):
        edition += c.sep() + _("desktop bundle")
    rows = [
        (_("Version"), str(report["roomscope"])),
        (_("Edition"), edition),
        (
            _("Build"),
            build["commit"]
            if build.get("commit")
            else _("no commit recorded (source or pip install)"),
        ),
    ]
    if build.get("ci_run"):
        rows.append((_("CI run"), build["ci_run"]))
    lines += c.section("RoomScope") + c.fields(rows)

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
    packages = [(name, found or _("not installed")) for name, found in report["packages"].items()]
    packages.append(("libsndfile", report.get("libsndfile") or _("unknown")))
    lines += c.fields(packages)

    lines += c.section(_("Settings"))
    lines += c.fields(
        (key, c.dash() if value in ("", None) else str(value))
        for key, value in report.get("settings", {}).items()
    )
    lines += c.section(_("Paths"), _("your home folder is shown as ~"))
    lines += c.fields((key, str(value)) for key, value in report["paths"].items())

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
            else _("sample rates not probed; run roomscope doctor --probe"),
        )
        lines += _device_rows(c, devices, probed)

    lines += c.section(_("Privacy"))
    lines += c.status("ok", _("Nothing was sent anywhere: this report is only printed."))
    lines += c.status("warn", privacy_note())
    return "\n".join(lines)


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
    """``roomscope devices``: one row per device."""
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
    return "\n".join(lines)


def render_inventory(console: Console, inventory: DeviceInventory) -> str:
    """``roomscope devices --probe``: every device with the rates it accepts."""
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
    return "\n".join(lines)


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
    return "\n".join(lines)


# --- Sweep -----------------------------------------------------------------------------


def render_sweep_written(
    console: Console, settings: SweepSettings, wav_path: object, sidecar: object
) -> str:
    c = console
    lines = c.title(_("RoomScope test signal"))
    lines.append("")
    lines += c.status("ok", _("Wrote {path}").format(path=wav_path))
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
    lines += c.status("ok", _("Wrote {sidecar} (keep it next to the WAV)").format(sidecar=sidecar))
    lines += c.section(_("Next"))
    lines += c.paragraph(
        _(
            "1. Import the WAV into your DAW, play it through the monitors and record "
            "the measurement microphone."
        )
    )
    lines += c.paragraph(_("2. Export the recording as WAV and analyse it:"))
    lines.append("     " + c.accent(f"roomscope analyze --recording <file> --sweep {wav_path}"))
    return "\n".join(lines)


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
    lines = c.title(_("RoomScope standalone measurement"))

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
    lines += c.section(_("Devices")) + c.fields(rows)

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
    return "\n".join(lines)


# --- Messages on stderr ------------------------------------------------------------------


def render_error(console: Console, message: str, *, detail: str = "") -> str:
    """``× error: message`` wrapped under itself, with an optional detail line."""
    text = _("error: {message}").format(message=message)
    if not console.unicode:
        lines = console.paragraph(text, indent=0)
        if detail:
            lines += console.paragraph(detail, indent=2)
        return "\n".join(lines)
    return "\n".join(console.status("error", text, indent=0, detail=detail, style=("red", "bold")))


def render_status(console: Console, kind: Status, text: str) -> str:
    """One status line at the left margin (warnings, stops, saved files)."""
    if not console.unicode and kind in ("warn", "error"):
        return "\n".join(console.paragraph(text, indent=0))
    return "\n".join(console.status(kind, text, indent=0))
