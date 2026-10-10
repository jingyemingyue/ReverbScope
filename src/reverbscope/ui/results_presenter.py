"""What the Results page shows, computed from a result without Qt.

Pure functions: an :class:`AnalysisResult`, its findings and its health
report in, display rows and texts out. Nothing here decides a threshold;
every judgement comes from :mod:`reverbscope.health` and the recording
profile, and this module only arranges it for the screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reverbscope.health import HealthCheck, HealthReport, HealthStatus, affects_text, status_word
from reverbscope.i18n import _, list_join, localize
from reverbscope.interpretation import Finding
from reverbscope.interpretation.profiles import confidence_text, noise_segment_text
from reverbscope.labels import severity_text, surface_text, topic_text, validity_word
from reverbscope.models.result import AnalysisResult, BoundaryCandidate, PlacementResult, Validity

#: Display word and chip tone of a metric validity.
VALIDITY_DISPLAY = {
    Validity.VALID: ("valid", "good"),
    Validity.UNRELIABLE: ("unreliable", "warn"),
    Validity.INSUFFICIENT_RANGE: ("insufficient range", "warn"),
    Validity.NOT_COMPUTED: ("not computed", "neutral"),
    Validity.OUTSIDE_EXCITATION: ("outside the excitation range", "neutral"),
    Validity.NOT_COMPARABLE: ("not comparable", "warn"),
}
CONFIDENCE_TONE = {"high": "good", "medium": "info", "low": "bad"}
HEALTH_TONE = {
    HealthStatus.GOOD: "good",
    HealthStatus.WARNING: "warn",
    HealthStatus.INVALID: "bad",
    HealthStatus.UNKNOWN: "neutral",
}

#: The analysis groups of the workspace, in reading order.
GROUP_FREQUENCY = "frequency"
GROUP_DECAY = "decay"
GROUP_NOISE = "noise"
GROUP_IMPULSE = "impulse"
GROUP_PLACEMENT = "placement"
GROUPS = (GROUP_FREQUENCY, GROUP_DECAY, GROUP_NOISE, GROUP_IMPULSE, GROUP_PLACEMENT)

#: Where a finding's topic (a stable id of the interpretation) is read.
FINDING_GROUP = {
    "reverberation": GROUP_DECAY,
    "clarity": GROUP_DECAY,
    "noise": GROUP_NOISE,
    "early_reflections": GROUP_IMPULSE,
    "low_frequency": GROUP_FREQUENCY,
}
#: Where a health check's metric groups are read (``health.METRIC_*``).
METRIC_GROUP_VIEW = {
    "decay": GROUP_DECAY,
    "energy": GROUP_DECAY,
    "frequency_response": GROUP_FREQUENCY,
    "noise": GROUP_NOISE,
    "reflections": GROUP_IMPULSE,
    "placement": GROUP_PLACEMENT,
    "resonances": GROUP_FREQUENCY,
}
_SEVERITY_RANK = {"warning": 0, "notice": 1, "info": 2}
_HEALTH_RANK = {
    HealthStatus.INVALID: 0,
    HealthStatus.WARNING: 1,
    HealthStatus.UNKNOWN: 2,
    HealthStatus.GOOD: 3,
}
#: How many findings the overview shows before "show all".
TOP_FINDINGS = 3


def group_title(key: str) -> str:
    return {
        GROUP_FREQUENCY: _("Frequency and low end"),
        GROUP_DECAY: _("Decay"),
        GROUP_NOISE: _("Noise"),
        GROUP_IMPULSE: _("Impulse and early reflections"),
        GROUP_PLACEMENT: _("Placement geometry"),
    }.get(key, key)


def validity_text(validity: Validity) -> tuple[str, str]:
    """The translated word and colour tone shown for a validity."""
    _word, tone = VALIDITY_DISPLAY.get(validity, (str(validity), "neutral"))
    return validity_word(validity), tone


def finding_group(finding: Finding) -> str | None:
    """The analysis group that holds the chart a finding points at; ``None``
    for a finding about the measurement itself (the health card has it)."""
    return FINDING_GROUP.get(finding.topic)


def check_group(check: HealthCheck) -> str | None:
    """The first analysis group a health check bears on."""
    for group in check.affects:
        view = METRIC_GROUP_VIEW.get(group)
        if view is not None:
            return view
    return None


def ranked_findings(findings: list[Finding]) -> list[tuple[int, Finding]]:
    """``(original index, finding)`` worst first; the order within a severity
    is the profile's own."""
    return sorted(
        enumerate(findings), key=lambda item: _SEVERITY_RANK.get(str(item[1].severity), 9)
    )


def ranked_checks(report: HealthReport) -> list[HealthCheck]:
    return sorted(report.problems, key=lambda check: _HEALTH_RANK.get(check.status, 9))


@dataclass(frozen=True)
class KeyFigure:
    """One of the four tiles: value, qualifier, chip and the group its chart is in."""

    value: str
    sub: str
    chip: str
    tone: str
    group: str


def key_figures(result: AnalysisResult) -> dict[str, KeyFigure]:
    """The four key figures: ``rt60``, ``noise``, ``reflections``, ``direct``."""
    figures: dict[str, KeyFigure] = {}
    broadband = result.decay.broadband
    if broadband.rt60_estimate_s is not None:
        word, tone = validity_text(broadband.t30.validity)
        if broadband.rt60_basis and broadband.rt60_basis != "T30":
            word, tone = validity_text(
                broadband.t20.validity if broadband.rt60_basis == "T20" else broadband.edt.validity
            )
        figures["rt60"] = KeyFigure(
            f"{broadband.rt60_estimate_s:.2f} s",
            _("broadband, estimated from {basis}").format(basis=broadband.rt60_basis),
            word,
            tone,
            GROUP_DECAY,
        )
    else:
        word, tone = validity_text(broadband.t30.validity)
        figures["rt60"] = KeyFigure(
            "-", _("no reverberation time could be reported"), word, tone, GROUP_DECAY
        )

    noise = result.noise
    if noise.rms_dbfs is not None:
        hum = next((h for h in noise.hum if h.detected), None)
        chip, tone = (
            (_("hum {base:g} Hz").format(base=hum.base_hz), "warn")
            if hum is not None
            else (_("no hum"), "good")
        )
        figures["noise"] = KeyFigure(
            f"{noise.rms_dbfs:.1f} dBFS",
            _("RMS, {segment} segment, uncalibrated").format(
                segment=noise_segment_text(noise.segment_source)
            ),
            chip,
            tone,
            GROUP_NOISE,
        )
    else:
        figures["noise"] = KeyFigure(
            "-", _("no quiet segment to measure"), _("not computed"), "neutral", GROUP_NOISE
        )

    refl = result.reflections
    if refl.reflections:
        strongest = max(refl.reflections, key=lambda r: r.relative_db)
        figures["reflections"] = KeyFigure(
            str(len(refl.reflections)),
            _("strongest at {delay:.1f} ms, {level:.1f} dB").format(
                delay=strongest.delay_ms, level=strongest.relative_db
            ),
            _("above {threshold:g} dB").format(threshold=refl.threshold_db),
            "info",
            GROUP_IMPULSE,
        )
    elif refl.window_truncated and refl.analysed_window_ms is not None:
        # The response ended before the window did: later arrivals were
        # not seen, so an empty list is not a clean room (the command line
        # says the same in its At-a-glance row).
        figures["reflections"] = KeyFigure(
            "0",
            _("none above {threshold:.0f} dB in the {end:.1f} ms that could be searched").format(
                threshold=refl.threshold_db, end=refl.analysed_window_ms[1]
            ),
            _("incomplete window"),
            "warn",
            GROUP_IMPULSE,
        )
    else:
        figures["reflections"] = KeyFigure(
            "0",
            _("none above {threshold:g} dB").format(threshold=refl.threshold_db),
            _("clean"),
            "good",
            GROUP_IMPULSE,
        )

    ir = result.impulse_response
    margin = (
        _("pre-peak margin {margin:.1f} dB").format(margin=ir.pre_peak_margin_db)
        if ir.pre_peak_margin_db is not None
        else _("pre-peak margin not checkable")
    )
    if ir.playback_speed is not None:
        figures["direct"] = KeyFigure(
            confidence_text(ir.direct_sound_confidence),
            _("sweep played at {percent:.1f} % speed").format(
                percent=ir.playback_speed.speed_ratio * 100.0
            ),
            _("wrong speed"),
            "bad",
            GROUP_IMPULSE,
        )
    else:
        confidence = ir.direct_sound_confidence
        figures["direct"] = KeyFigure(
            confidence_text(confidence),
            margin,
            _("confidence"),
            CONFIDENCE_TONE.get(confidence, "neutral"),
            GROUP_IMPULSE,
        )
    return figures


# --- the three questions of the overview ----------------------------------------


def trust_text(report: HealthReport) -> tuple[str, str]:
    """Is this measurement trustworthy? A sentence and a banner tone."""
    if report.overall is HealthStatus.INVALID:
        titles = list_join(c.title for c in report.problems if c.status is HealthStatus.INVALID)
        return (
            _(
                "No: the measurement itself failed ({checks}). Fix the measurement and "
                "measure again before reading the room from these numbers."
            ).format(checks=titles),
            "bad",
        )
    if report.overall is HealthStatus.WARNING:
        titles = list_join(c.title for c in report.problems if c.status is HealthStatus.WARNING)
        return (
            _(
                "With limits: the measurement is usable but {checks} put some figures in "
                "doubt. Those figures are marked below and in the charts."
            ).format(checks=titles),
            "warn",
        )
    if report.overall is HealthStatus.UNKNOWN:
        titles = list_join(c.title for c in report.problems)
        return (
            _(
                "Partly: {checks} could not be checked, so the figures they bear on are unverified."
            ).format(checks=titles),
            "info",
        )
    return _("Yes: every check on the take itself is good."), "good"


def health_summary(report: HealthReport) -> str:
    summary = _("{good} of {total} checks good.").format(
        good=len(report.good), total=len(report.checks)
    )
    if report.unavailable:
        summary += " " + _("Not reported: {groups}.").format(
            groups=affects_text(report.unavailable)
        )
    if report.good:
        summary += " " + _("Good: {titles}.").format(
            titles=list_join(check.title for check in report.good)
        )
    return summary


def check_message(check: HealthCheck) -> str:
    """The card text of a check: reason, what it affects, the fix and the details."""
    parts = [check.reason]
    if check.affects:
        parts.append(_("Affects: {groups}").format(groups=affects_text(check.affects)))
    parts.extend(check.fix)
    parts.extend(check.details)
    return "\n".join(parts)


def main_problems(findings: list[Finding], problem: str, profile_title: str) -> str:
    """What are the main problems? One sentence over the findings."""
    if not findings and problem:
        return _("The {profile} profile could not interpret this result: {error}").format(
            profile=profile_title, error=problem
        )
    warnings = sum(1 for f in findings if str(f.severity) == "warning")
    notices = sum(1 for f in findings if str(f.severity) == "notice")
    if not findings:
        return _("No findings under the {profile} profile.").format(profile=profile_title)
    if warnings:
        topics = list_join(
            dict.fromkeys(topic_text(f.topic) for f in findings if str(f.severity) == "warning")
        )
        return _("{n} warning(s) ({topics}) and {m} notice(s) under the {profile} profile.").format(
            n=warnings, topics=topics, m=notices, profile=profile_title
        )
    if notices:
        return _("No warning; {m} notice(s) under the {profile} profile.").format(
            m=notices, profile=profile_title
        )
    return _("Nothing to warn about under the {profile} profile.").format(profile=profile_title)


def next_steps(report: HealthReport, findings: list[Finding]) -> list[tuple[str, str | None]]:
    """What to check or change next: ``(sentence, group to open or None)``.

    The steps are the health checks' own fixes while the take is not good
    (a measurement that cannot be trusted is fixed first), then the charts
    behind the warnings; nothing here invents a threshold.
    """
    steps: list[tuple[str, str | None]] = []
    for check in ranked_checks(report):
        for fix in check.fix[:2]:
            steps.append(
                (_("{check}: {fix}").format(check=check.title, fix=fix), check_group(check))
            )
        if len(steps) >= 3:
            break
    if report.overall is HealthStatus.INVALID:
        return steps
    for _index, finding in ranked_findings(findings):
        if str(finding.severity) != "warning":
            continue
        group = finding_group(finding)
        if group is None:
            continue
        steps.append(
            (
                _("Open {chart} for the {topic} warning.").format(
                    chart=group_title(group), topic=topic_text(finding.topic)
                ),
                group,
            )
        )
        if len(steps) >= 5:
            break
    if not steps and findings:
        steps.append(
            (_("Nothing to fix; move the microphone or treat the room and compare."), None)
        )
    return steps


# --- details --------------------------------------------------------------------


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return _("yes") if value else _("no")
    if isinstance(value, float):
        return f"{value:.3g}" if abs(value) < 0.01 and value != 0 else f"{value:.2f}"
    if isinstance(value, (list, tuple)):
        return list_join(_format_value(item) for item in value)
    if value is None:
        return _("not available")
    return localize(str(value))


_UNIT_SUFFIXES = {
    "_db": "dB",
    "_dbfs": "dBFS",
    "_hz": "Hz",
    "_ms": "ms",
    "_s": "s",
    "_m": "m",
    "_percent": "%",
    "_c": "°C",
}


def evidence_rows(evidence: dict[str, Any]) -> list[tuple[str, str]]:
    """``(name, value)`` rows from a finding's or check's evidence dict: the
    key names the unit (``rt60_s``), which is moved into the value."""
    rows: list[tuple[str, str]] = []
    for key, value in evidence.items():
        unit = ""
        name = key
        for suffix, word in _UNIT_SUFFIXES.items():
            if key.endswith(suffix):
                unit = word
                name = key[: -len(suffix)]
                break
        text = _format_value(value)
        if unit and not isinstance(value, (bool, str)) and value is not None:
            text = f"{text} {unit}"
        rows.append((name.replace("_", " "), text))
    return rows


def finding_rows(finding: Finding) -> list[tuple[str, str]]:
    rows = [
        (_("Severity"), severity_text(str(finding.severity))),
        (_("Topic"), topic_text(finding.topic)),
    ]
    if finding.message_id:
        rows.append((_("Identifier"), finding.message_id))
    rows.extend(evidence_rows(finding.evidence))
    return rows


def check_rows(check: HealthCheck) -> list[tuple[str, str]]:
    rows = [(_("Status"), status_word(check.status)), (_("Reason"), check.reason)]
    if check.affects:
        rows.append((_("Affects"), affects_text(check.affects)))
    rows.extend(evidence_rows(check.evidence))
    for step in check.fix:
        rows.append((_("What to do"), step))
    for detail in check.details:
        rows.append((_("Where"), detail))
    return rows


# --- placement ------------------------------------------------------------------

#: The field of the measurement page that supplies a missing placement input
#: (the core names the command-line option).
PLACEMENT_FIELDS = {
    "--speaker-distance": "Loudspeaker distance",
    "--mic-height": "Microphone height",
}


def missing_input_field(missing_input: str | None) -> str | None:
    """The field to fill in for a core ``missing_input`` option, translated."""
    if missing_input is None:
        return None
    names = {
        "--speaker-distance": _("Loudspeaker distance"),
        "--mic-height": _("Microphone height"),
    }
    return names.get(missing_input, missing_input)


def placement_summary(placement: PlacementResult | None) -> str:
    if placement is None:
        return _(
            "No placement result: no loudspeaker distance was entered, so the reflections "
            "stay in milliseconds."
        )
    assumed = _(" (assumed)") if placement.temperature_assumed else ""
    return _(
        "Placement tier {tier}. No coordinates, room length, room width or "
        "named wall are derived. Speed of sound {speed:.1f} m/s at "
        "{temp:.0f} °C{assumed}."
    ).format(
        tier=placement.tier,
        speed=placement.speed_of_sound_m_s,
        temp=placement.temperature_c,
        assumed=assumed,
    )


def placement_missing(placement: PlacementResult | None) -> list[str]:
    """The fields still to fill in for the next tier, by their names."""
    if placement is None:
        return [_("Loudspeaker distance")]
    names: list[str] = []
    for length in (
        placement.source_height_m,
        placement.horizontal_separation_m,
        placement.ceiling_height_m,
    ):
        field = missing_input_field(length.missing_input)
        if field is not None and field not in names:
            names.append(field)
    return names


def placement_length_rows(placement: PlacementResult) -> list[tuple[str, str, str, str]]:
    """``(figure, value, validity, note)`` for the three solved lengths."""
    rows: list[tuple[str, str, str, str]] = []
    for caption, length in (
        (_("Loudspeaker height"), placement.source_height_m),
        (_("Plane above the devices"), placement.ceiling_height_m),
        (_("Horizontal separation"), placement.horizontal_separation_m),
    ):
        if length.metres is None:
            value = _("not determined")
            field = missing_input_field(length.missing_input)
            if field is not None:
                value += f" ({field})"
        else:
            value = f"{length.metres:.2f} m"
            if length.input_uncertainty_m is not None:
                value += f" ±{length.input_uncertainty_m:.2f}"
            if length.alternatives_m:
                value += " " + _("or {values}").format(
                    values=" / ".join(f"{alt:.2f} m" for alt in length.alternatives_m)
                )
        rows.append((caption, value, validity_word(length.validity), localize(length.reason or "")))
    return rows


def candidate_rows(placement: PlacementResult) -> list[tuple[str, ...]]:
    """``(delay, level, excess path, surface, plane?)`` per candidate."""
    rows: list[tuple[str, ...]] = []
    for candidate in placement.candidates:
        plane = _("yes") if candidate.interpretable_as_plane else _("no")
        if candidate.interpretable_as_plane is None:
            plane = _("untested")
        rows.append(
            (
                f"{candidate.delay_ms:.2f}",
                f"{candidate.relative_db:.1f}",
                f"{candidate.excess_path_m:.2f}",
                surface_text(candidate.surface),
                plane,
            )
        )
    return rows


def candidate_detail_rows(candidate: BoundaryCandidate) -> list[tuple[str, str]]:
    """Everything the model says about one arrival, with its validity."""
    rows = [
        (_("Delay"), f"{candidate.delay_ms:.2f} ms"),
        (_("Level re direct"), f"{candidate.relative_db:.1f} dB"),
        (_("Excess path"), f"{candidate.excess_path_m:.2f} m"),
    ]
    if candidate.mirror_path_m is not None:
        rows.append((_("Image-source path"), f"{candidate.mirror_path_m:.2f} m"))
    if candidate.product_m2 is not None:
        rows.append((_("Product of the two distances"), f"{candidate.product_m2:.2f} m²"))
    if candidate.geometric_mean_m is not None:
        rows.append((_("Geometric mean distance"), f"{candidate.geometric_mean_m:.2f} m"))
    if candidate.mean_distance_bracket_m is not None:
        low, high = candidate.mean_distance_bracket_m
        rows.append((_("Mean distance bracket"), f"{low:.2f} – {high:.2f} m"))
    if candidate.specular_ceiling_db is not None:
        rows.append((_("Specular ceiling"), f"{candidate.specular_ceiling_db:.1f} dB"))
    if candidate.interpretable_as_plane is None:
        rows.append((_("Plane reflection?"), _("untested (the tier did not allow it)")))
    elif candidate.interpretable_as_plane:
        rows.append((_("Plane reflection?"), _("yes")))
        rows.append((_("Attributed to"), surface_text(candidate.surface) or _("no surface")))
    else:
        rows.append((_("Plane reflection?"), _("no")))
    if candidate.excluded_reason:
        rows.append((_("Why excluded"), localize(candidate.excluded_reason)))
    return rows


def placement_notes(placement: PlacementResult) -> list[str]:
    notes = [localize(note) for note in placement.notes]
    if placement.coordinates_withheld:
        notes.append(localize(placement.coordinates_withheld))
    return notes


# --- the other groups' tables ---------------------------------------------------


def resonance_rows(result: AnalysisResult) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for candidate in result.resonances.candidates:
        decay = (
            f"{candidate.narrowband_decay_20db_s:.2f} s"
            if candidate.narrowband_decay_20db_s is not None
            else _("n/a")
        )
        rows.append(
            (
                f"{candidate.frequency_hz:.1f}",
                f"{candidate.level_above_baseline_db:+.1f}",
                decay,
                _("yes") if candidate.decay_distinguishable else _("no"),
            )
        )
    return rows


def resonance_detail_rows(result: AnalysisResult, index: int) -> list[tuple[str, str]]:
    candidate = result.resonances.candidates[index]

    def seconds(value: float | None) -> str:
        return f"{value:.2f} s" if value is not None else _("not available")

    return [
        (_("Frequency"), f"{candidate.frequency_hz:.1f} Hz"),
        (_("Level above baseline"), f"{candidate.level_above_baseline_db:+.1f} dB"),
        (_("Narrow-band decay (20 dB)"), seconds(candidate.narrowband_decay_20db_s)),
        (_("Filter ringing (20 dB)"), seconds(candidate.filter_ringing_20db_s)),
        (_("Surroundings decay (20 dB)"), seconds(candidate.surroundings_decay_20db_s)),
        (
            _("Decay distinguishable"),
            _("yes") if candidate.decay_distinguishable else _("no"),
        ),
    ]


def resonance_note(result: AnalysisResult) -> str:
    searched = result.resonances.searched_range_hz
    parts: list[str] = []
    if searched is not None:
        parts.append(
            _("Searched {low:.0f}–{high:.0f} Hz.").format(low=searched[0], high=searched[1])
        )
    else:
        parts.append(_("No frequency range could be searched for resonances."))
    parts.extend(localize(note) for note in result.resonances.notes)
    return " ".join(parts)


def band_detail_rows(result: AnalysisResult, row: int) -> list[tuple[str, str]]:
    """The metrics of one decay-table row (0 = broadband) with their reasons."""
    bands = (result.decay.broadband, *result.decay.bands)
    if not 0 <= row < len(bands):
        return []
    band = bands[row]
    rows: list[tuple[str, str]] = []
    for metric in (band.edt, band.t20, band.t30):
        value = f"{metric.seconds:.2f} s" if metric.seconds is not None else _("n/a")
        text = f"{value} ({validity_word(metric.validity)})"
        if metric.reason:
            text += f"\n{localize(metric.reason)}"
        rows.append((metric.name, text))
    if band.rt60_estimate_s is not None:
        rows.append(
            (
                _("RT60 estimate"),
                _("{seconds:.2f} s from {basis}").format(
                    seconds=band.rt60_estimate_s, basis=band.rt60_basis
                ),
            )
        )
    if band.peak_to_noise_db is not None:
        rows.append((_("Decay range"), f"{band.peak_to_noise_db:.1f} dB"))
    if band.curvature_percent is not None:
        rows.append((_("Curvature"), f"{band.curvature_percent:.0f} %"))
    for energy in (band.c50, band.c80, band.d50, band.centre_time):
        if energy.value is None:
            text = validity_word(energy.validity)
        elif energy.unit == "dB":
            text = f"{energy.value:+.1f} dB"
        elif energy.unit == "%":
            text = f"{energy.value:.0f} %"
        else:
            text = f"{energy.value * 1000:.0f} ms"
        if energy.reason:
            text += f"\n{localize(energy.reason)}"
        rows.append((energy.name, text))
    for warning in band.warnings:
        rows.append((_("Warning"), localize(warning)))
    if band.filter_warning:
        rows.append((_("Filter"), localize(band.filter_warning)))
    return rows


def noise_band_rows(result: AnalysisResult) -> list[tuple[str, str]]:
    from reverbscope.labels import frequency_text

    rows: list[tuple[str, str]] = []
    for centre, level in result.noise.band_levels_dbfs:
        rows.append((frequency_text(centre), f"{level:.1f}" if level is not None else _("n/a")))
    return rows


def noise_detail_rows(result: AnalysisResult) -> list[tuple[str, str]]:
    noise = result.noise
    rows: list[tuple[str, str]] = [
        (_("Segment"), noise_segment_text(noise.segment_source)),
    ]
    if noise.segment_duration_s is not None:
        rows.append((_("Segment length"), f"{noise.segment_duration_s:.2f} s"))
    rows.append(
        (
            _("RMS"),
            f"{noise.rms_dbfs:.1f} dBFS" if noise.rms_dbfs is not None else _("not computed"),
        )
    )
    rows.append(
        (
            _("Peak"),
            f"{noise.peak_dbfs:.1f} dBFS" if noise.peak_dbfs is not None else _("not computed"),
        )
    )
    for hum in noise.hum:
        if hum.detected:
            rows.append(
                (
                    _("Hum"),
                    _("{base:g} Hz and {n} harmonic(s)").format(
                        base=hum.base_hz, n=len(hum.harmonics)
                    ),
                )
            )
    rows.append((_("Calibration"), localize(noise.calibration)))
    for note in noise.notes:
        rows.append((_("Note"), localize(note)))
    return rows


def reflection_rows(result: AnalysisResult) -> list[tuple[str, str]]:
    return [(f"{r.delay_ms:.2f}", f"{r.relative_db:.1f}") for r in result.reflections.reflections]


def impulse_detail_rows(result: AnalysisResult) -> list[tuple[str, str]]:
    ir = result.impulse_response
    refl = result.reflections
    rows: list[tuple[str, str]] = [
        (_("Direct-sound confidence"), confidence_text(ir.direct_sound_confidence)),
        (
            _("Pre-peak margin"),
            f"{ir.pre_peak_margin_db:.1f} dB"
            if ir.pre_peak_margin_db is not None
            else _("not checkable"),
        ),
        (_("Valid length"), f"{ir.valid_length_s:.2f} s"),
        (_("Sweep passes found"), str(ir.sweep_passes)),
    ]
    if ir.playback_speed is not None:
        rows.append(
            (
                _("Playback speed"),
                _("{percent:.1f} % of the generated speed").format(
                    percent=ir.playback_speed.speed_ratio * 100.0
                ),
            )
        )
    if ir.direct_level_dbfs is not None:
        rows.append((_("Direct level"), f"{ir.direct_level_dbfs:.1f} dBFS"))
    window = refl.analysed_window_ms or refl.window_ms
    rows.append((_("Reflection window"), f"{window[0]:.1f}–{window[1]:.1f} ms"))
    rows.append((_("Threshold"), f"{refl.threshold_db:g} dB"))
    if refl.window_truncated:
        rows.append((_("Window"), _("cut short: the response ended before the window did")))
    if ir.loopback is not None:
        rows.append(
            (
                _("Loopback"),
                _("compensated") if ir.loopback.compensation_applied else _("not applied"),
            )
        )
    for note in (*ir.notes, *refl.notes):
        rows.append((_("Note"), localize(note)))
    return rows
