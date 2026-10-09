"""Measurement health: is this measurement trustworthy, and if not, what to do.

Reads an :class:`~reverbscope.models.result.AnalysisResult` and never changes
it. The analysis already decides what it can and cannot report (every metric
carries its validity and its reason); this module gathers those decisions into
the list a recording engineer reads first: named checks, each *good*,
*warning*, *invalid* or *unknown*, with the reason, the metrics it bears on
and what to do next. There is no score. The worst check decides the overall
status, and *unknown* means the check could not be made, not that it passed.

The thresholds are the analysis's own (``docs/MEASUREMENT_METHODOLOGY.md``
§12): the direct-sound confidence limits of ``core.deconvolution``, the
decay-range rule of ``core.decay`` (evaluation range plus the noise margin),
the clipping and folded-distortion detectors of ``core.linearity``. The
harmonic-distortion limit, the headroom limit, the dropout limits and the
recording-length limit are ReverbScope's own, chosen for a recording-room
measurement and stated as such; none of them is an international standard.

Like the findings, a report is computed when a result is shown, in the
interface language; ``result.json`` does not store it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from reverbscope.i18n import N_, _, current_locale, labelled, list_join, localize, pgettext
from reverbscope.models.result import (
    EXCITATION_SOURCE_DECLARED,
    EXCITATION_SOURCE_UNKNOWN,
    KIND_SAMPLE_RATE,
    KIND_TIME_STRETCH,
    AnalysisResult,
    DecayMetric,
    EnergyMetric,
    PlaybackSpeed,
    Validity,
)


class HealthStatus(StrEnum):
    GOOD = "good"
    WARNING = "warning"
    INVALID = "invalid"
    UNKNOWN = "unknown"


#: Worst first: the overall status is the first of these that any check has.
_WORST_FIRST = (
    HealthStatus.INVALID,
    HealthStatus.WARNING,
    HealthStatus.UNKNOWN,
    HealthStatus.GOOD,
)

#: Metric groups a check can bear on (stable ids, written to JSON).
METRIC_DECAY = "decay"
METRIC_ENERGY = "energy"
METRIC_FREQUENCY_RESPONSE = "frequency_response"
METRIC_NOISE = "noise"
METRIC_REFLECTIONS = "reflections"
METRIC_PLACEMENT = "placement"
METRIC_RESONANCES = "resonances"
_EVERYTHING = (
    METRIC_DECAY,
    METRIC_ENERGY,
    METRIC_FREQUENCY_RESPONSE,
    METRIC_NOISE,
    METRIC_REFLECTIONS,
    METRIC_PLACEMENT,
    METRIC_RESONANCES,
)
#: Every metric group, in the order a report names them.
METRIC_GROUPS = _EVERYTHING

#: Harmonic level (dB re the direct sound) from which the chain is called
#: distorting. The harmonic responses of an exponential sweep are separated in
#: time from the room response (Farina 2000), so they do not spoil the decay;
#: at this level the chain is near its limit and the next few dB clip.
#: ReverbScope's own limit, not a standard.
HARMONIC_WARNING_DB = -20.0
#: A recording whose peak is within this of full scale has no headroom left:
#: a louder reflection or a louder room would clip. ReverbScope's own limit.
HEADROOM_DB = 1.0
#: Decay recorded after the direct sound below which long reverberation times
#: cannot be evaluated (s); the analysis notes the same limit.
SHORT_DECAY_S = 1.0
#: Dropouts in the recorded sweep from which the response is called invalid:
#: this many, or this much of the sweep missing. ReverbScope's own limits.
DROPOUTS_INVALID_COUNT = 10
DROPOUTS_INVALID_MS = 50.0


@dataclass(frozen=True)
class HealthCheck:
    """One named check of the measurement."""

    #: Stable identifier (``playback_speed``, ``clipping``, ...).
    id: str
    status: HealthStatus
    #: Short name in the interface language ("Playback speed").
    title: str
    #: Why the check has this status, in the interface language.
    reason: str
    #: Metric groups this check bears on (``METRIC_*``); empty when none.
    affects: tuple[str, ...] = ()
    #: The measured values the status rests on (units in the keys).
    evidence: dict[str, Any] = field(default_factory=dict)
    #: What to do next, one step per entry, in the interface language.
    fix: tuple[str, ...] = ()
    #: Reference lines under the steps (where each DAW keeps a setting).
    details: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": str(self.status),
            "title": self.title,
            "reason": self.reason,
            "affects": list(self.affects),
            "evidence": self.evidence,
            "fix": list(self.fix),
            "details": list(self.details),
        }


@dataclass(frozen=True)
class HealthReport:
    """The checks of one result and the status the worst of them gives."""

    overall: HealthStatus
    checks: tuple[HealthCheck, ...]
    #: Metric groups the result reports no number for at all.
    unavailable: tuple[str, ...]
    locale: str = "en"

    @property
    def affected(self) -> tuple[str, ...]:
        """Metric groups that some check other than *good* bears on."""
        seen: list[str] = []
        for check in self.checks:
            if check.status is HealthStatus.GOOD:
                continue
            for group in check.affects:
                if group not in seen:
                    seen.append(group)
        return tuple(group for group in _EVERYTHING if group in seen)

    @property
    def problems(self) -> tuple[HealthCheck, ...]:
        return tuple(check for check in self.checks if check.status is not HealthStatus.GOOD)

    @property
    def good(self) -> tuple[HealthCheck, ...]:
        return tuple(check for check in self.checks if check.status is HealthStatus.GOOD)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": str(self.overall),
            "locale": self.locale,
            "checks": [check.to_dict() for check in self.checks],
            "affected": list(self.affected),
            "unavailable": list(self.unavailable),
        }


def status_word(status: HealthStatus | str) -> str:
    """The status in the interface language."""
    words = {
        HealthStatus.GOOD: pgettext("health", "good"),
        HealthStatus.WARNING: pgettext("health", "warning"),
        HealthStatus.INVALID: pgettext("health", "invalid"),
        HealthStatus.UNKNOWN: pgettext("health", "unknown"),
    }
    try:
        return words[HealthStatus(status)]
    except ValueError:
        return str(status)


def metric_group_text(group: str) -> str:
    """A metric group in the interface language, as the report names it."""
    names = {
        METRIC_DECAY: pgettext("metric group", "reverberation"),
        METRIC_ENERGY: pgettext("metric group", "clarity"),
        METRIC_FREQUENCY_RESPONSE: pgettext("metric group", "frequency response"),
        METRIC_NOISE: pgettext("metric group", "noise floor"),
        METRIC_REFLECTIONS: pgettext("metric group", "early reflections"),
        METRIC_PLACEMENT: pgettext("metric group", "placement"),
        METRIC_RESONANCES: pgettext("metric group", "resonances"),
    }
    return names.get(group, group)


def assess(result: AnalysisResult) -> HealthReport:
    """The health report of ``result`` in the interface language."""
    checks = [
        check
        for check in (
            _reference(result),
            _sweep(result),
            _playback_speed(result),
            _direct_sound(result),
            _clipping(result),
            _distortion(result),
            _device(result),
            _dropouts(result),
            _decay_range(result),
            _noise(result),
            _length(result),
            _loopback(result),
        )
        if check is not None
    ]
    statuses = {check.status for check in checks}
    overall = next((status for status in _WORST_FIRST if status in statuses), HealthStatus.GOOD)
    return HealthReport(
        overall=overall,
        checks=tuple(checks),
        unavailable=_unavailable(result),
        locale=current_locale(),
    )


# --- the checks ---------------------------------------------------------------------


def _imported(result: AnalysisResult) -> bool:
    """An impulse response from another tool: no sweep and no recording were seen."""
    band = result.excitation_band
    return band is None or band.source in (EXCITATION_SOURCE_DECLARED, EXCITATION_SOURCE_UNKNOWN)


def _has_sweep_definition(result: AnalysisResult) -> bool:
    return bool(result.sweep_settings)


def _imported_reason() -> str:
    return _(
        "an imported impulse response: no sweep and no recording were seen, so how it was "
        "acquired could not be checked"
    )


def _reference(result: AnalysisResult) -> HealthCheck:
    title = _("Reference")
    if _imported(result):
        return HealthCheck("reference", HealthStatus.UNKNOWN, title, _imported_reason())
    if _has_sweep_definition(result):
        return HealthCheck(
            "reference",
            HealthStatus.GOOD,
            title,
            _("the sweep definition regenerated the exact reference sweep"),
        )
    return HealthCheck(
        "reference",
        HealthStatus.WARNING,
        title,
        _(
            "the reference is an audio file without a sweep definition: a regularised "
            "inverse was used, and the playback-speed and distortion checks could not run"
        ),
        fix=(
            _(
                "Keep the .reverbscope-sweep.json file next to the sweep WAV, or choose it as "
                "the reference, so that the exact sweep is regenerated."
            ),
        ),
    )


#: The stored (English) note the analysis puts on a band it narrowed because
#: the recording started after the sweep began.
_LATE_START = "the recording starts "


def _sweep(result: AnalysisResult) -> HealthCheck:
    title = _("Sweep")
    if _imported(result):
        return HealthCheck("sweep", HealthStatus.UNKNOWN, title, _imported_reason())
    ir = result.impulse_response
    evidence: dict[str, Any] = {
        "sweep_start_in_recording_s": ir.sweep_start_in_recording_s,
        "sweep_passes": ir.sweep_passes,
    }
    if ir.sweep_passes > 1:
        return HealthCheck(
            "sweep",
            HealthStatus.WARNING,
            title,
            _(
                "the recording holds {passes} sweep passes; the pass starting at {start:.2f} s "
                "was analysed and the others were ignored"
            ).format(passes=ir.sweep_passes, start=ir.sweep_start_in_recording_s),
            evidence=evidence,
            fix=(_("Record one pass only: switch loop or cycle recording off."),),
        )
    band = ir.excitation_band
    # The analysis narrows the band and says so when the recording starts
    # inside the sweep; the band's own lower edge sits above the sweep's first
    # frequency by design (the fade-in is not fully excited), so it is no sign.
    if band is not None and band.note is not None and band.note.startswith(_LATE_START):
        evidence["excitation_low_hz"] = band.low_hz
        return HealthCheck(
            "sweep",
            HealthStatus.WARNING,
            title,
            _(
                "the recording starts after the sweep began: nothing below {low_hz:.0f} Hz was "
                "recorded, and the bands below it are withheld"
            ).format(low_hz=band.low_hz),
            affects=(
                METRIC_DECAY,
                METRIC_ENERGY,
                METRIC_FREQUENCY_RESPONSE,
                METRIC_RESONANCES,
            ),
            evidence=evidence,
            fix=(
                _(
                    "Start recording before playback (the test file begins with silence for "
                    "this) and export the whole take."
                ),
            ),
        )
    return HealthCheck(
        "sweep",
        HealthStatus.GOOD,
        title,
        _(
            "found {start:.2f} s into the recording, one pass, the whole swept range recorded"
        ).format(start=ir.sweep_start_in_recording_s),
        evidence=evidence,
    )


#: Where each DAW sets its project sample rate, as ``docs/user-guide/daw-setup.md``
#: describes it (menu names as in the English interface; the Chinese catalog
#: keeps them).
DAW_SAMPLE_RATE_SETTINGS: tuple[tuple[str, str], ...] = (
    (
        "Pro Tools",
        N_(
            "Session Setup shows the session rate; generate the sweep at that rate rather than "
            "enabling Apply SRC in File ▸ Import ▸ Audio"
        ),
    ),
    ("Logic Pro", N_("File ▸ Project Settings ▸ Audio ▸ Sample Rate")),
    ("GarageBand", N_("no sample-rate setting: generate the sweep at 44.1 kHz")),
    ("Cubase / Nuendo", N_("Project ▸ Project Setup")),
    (
        "Fender Studio Pro",
        N_("Session ▸ Session Setup (Song ▸ Song Setup in Studio One before v8)"),
    ),
    (
        "Ableton Live",
        N_(
            "Settings (Options ▸ Settings on Windows, Live ▸ Settings on macOS) ▸ Audio ▸ In/Out Sample Rate"
        ),
    ),
    (
        "REAPER",
        N_(
            "File ▸ Project Settings ▸ tick Project sample rate, and in Preferences ▸ Audio ▸ "
            "Device tick Request sample rate with the same rate"
        ),
    ),
    ("FL Studio", N_("Options ▸ Audio settings (F10) ▸ Sample Rate")),
    ("Bitwig Studio", N_("Dashboard ▸ Settings ▸ Audio")),
    ("Digital Performer", N_("the Sample Rate setting in the Control Panel")),
    ("Audacity", N_("Project Sample Rate in the Quality section of Audio Setup ▸ Audio Settings")),
)

#: How each DAW switches time-stretching off for the test-signal clip, as the
#: same guide describes it.
DAW_STRETCH_SETTINGS: tuple[tuple[str, str], ...] = (
    (
        "Pro Tools",
        N_(
            "the track's Elastic Audio selector reads None – Disable Elastic Audio; import with "
            "File ▸ Import rather than by dragging from the desktop"
        ),
    ),
    (
        "Logic Pro",
        N_(
            "Region inspector: untick Flex and set Smart Tempo to Off (Logic 12.2 and earlier: "
            "Flex & Follow = Off); File ▸ Project Settings ▸ Smart Tempo ▸ Set Imported Files "
            "To = Flex Off"
        ),
    ),
    ("GarageBand", N_("audio editor: untick Follow Tempo and Pitch, leave Enable Flex off")),
    ("Cubase / Nuendo", N_("Musical Mode off for the sweep clip (Sample Editor or Pool)")),
    (
        "Fender Studio Pro",
        N_(
            "Track Inspector: Tempo mode = Don't Follow; Event Inspector: Speedup 1, Transpose "
            "and Tune 0"
        ),
    ),
    (
        "Ableton Live",
        N_("Clip View: Warp off; Settings ▸ Record, Warp & Launch: Auto-Warp Long Samples off"),
    ),
    (
        "REAPER",
        N_(
            "Item Properties (F2): Playback rate 1.0 and no stretch markers; do not change the "
            "tempo after importing"
        ),
    ),
    (
        "FL Studio",
        N_(
            "channel settings: Time knob at (none); General settings ▸ Read sample tempo "
            "information off"
        ),
    ),
    ("Bitwig Studio", N_("Inspector: Stretch ▸ Mode = Raw (there is no Off)")),
    (
        "Digital Performer",
        N_(
            "untick Stretch in the Track Settings menu of the sweep track; soundbite Time "
            "Compress/Expand = Don't Time Scale"
        ),
    ),
)


def _daw_lines(table: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(labelled(daw, _(text)) for daw, text in table)


def speed_fix(speed: PlaybackSpeed) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """What to do about a sweep played at the wrong speed: the steps, and
    where each DAW keeps the setting (reference lines under them)."""
    if speed.kind == KIND_SAMPLE_RATE and speed.played_rate_hz:
        return (
            (
                _(
                    "Generate the test signal at the project's sample rate ({rate} Hz): in the "
                    "app's Step 1, or with reverbscope sweep --sample-rate {rate}. Do not rely on "
                    "the DAW converting the file on import (that puts its resampler into the "
                    "measurement). Then measure again."
                ).format(rate=speed.played_rate_hz),
            ),
            (_("Where the project's sample rate is set:"), *_daw_lines(DAW_SAMPLE_RATE_SETTINGS)),
        )
    if speed.kind not in (KIND_SAMPLE_RATE, KIND_TIME_STRETCH):
        # A diagnosis this version does not know (a newer file): the speed
        # error stands, its cause is not claimed, and both settings are named.
        return (
            (
                _(
                    "The cause of the speed error was not recognised ({kind}). Check the "
                    "project's sample rate against the test signal's and switch time-stretching "
                    "off for the clip, then measure again."
                ).format(kind=speed.kind),
            ),
            (),
        )
    return (
        (
            _(
                "Switch time-stretching off for the test-signal clip and keep the tempo "
                "unchanged after import: the clip must last exactly as long as the WAV file. "
                "Then measure again."
            ),
        ),
        (_("Where each DAW switches it off:"), *_daw_lines(DAW_STRETCH_SETTINGS)),
    )


def _playback_speed(result: AnalysisResult) -> HealthCheck | None:
    if _imported(result):
        return None
    title = _("Playback speed")
    speed = result.impulse_response.playback_speed
    if speed is not None:
        steps, details = speed_fix(speed)
        return HealthCheck(
            "playback_speed",
            HealthStatus.INVALID,
            title,
            localize(speed.describe()),
            affects=_EVERYTHING,
            evidence=speed.to_dict(),
            fix=steps,
            details=details,
        )
    if not _has_sweep_definition(result):
        return HealthCheck(
            "playback_speed",
            HealthStatus.UNKNOWN,
            title,
            _("could not be checked: the reference has no sweep definition"),
        )
    return HealthCheck(
        "playback_speed",
        HealthStatus.GOOD,
        title,
        _("the sweep deconvolved as generated; no speed error was found"),
    )


def _direct_sound(result: AnalysisResult) -> HealthCheck:
    ir = result.impulse_response
    title = _("Direct sound")
    margin = ir.pre_peak_margin_db
    evidence: dict[str, Any] = {
        "direct_sound_confidence": ir.direct_sound_confidence,
        "pre_peak_margin_db": margin,
    }
    confidence = ir.direct_sound_confidence
    if confidence == "high":
        return HealthCheck(
            "direct_sound",
            HealthStatus.GOOD,
            title,
            _("identified with high confidence (pre-peak margin {margin:.1f} dB)").format(
                margin=margin if margin is not None else float("nan")
            ),
            evidence=evidence,
        )
    fix: tuple[str, ...] = (
        _(
            "Check that the reference is the sweep that was played; lower the playback level if "
            "the loudspeaker distorts; keep the microphone away from surfaces nearer to it than "
            "the loudspeaker is; then measure again."
        ),
    )
    if confidence == "medium":
        return HealthCheck(
            "direct_sound",
            HealthStatus.WARNING,
            title,
            _(
                "content before the direct sound is only {margin:.1f} dB below it (noise, "
                "pre-ringing or a wrong reference): the delays and levels of reflections may be off"
            ).format(margin=margin if margin is not None else float("nan")),
            affects=(METRIC_REFLECTIONS, METRIC_PLACEMENT),
            evidence=evidence,
            fix=fix,
        )
    if ir.playback_speed is not None:
        reason = _("not identified: the sweep was played at the wrong speed (see Playback speed)")
        fix = ()
    elif margin is None:
        reason = _("there is no content before the direct sound to check the detection against")
    else:
        arrival = next((note for note in ir.notes if "earlier arrival" in note), None)
        if arrival is not None:
            reason = localize(arrival)
        else:
            reason = _(
                "content before the direct sound is only {margin:.1f} dB below it (noise, "
                "pre-ringing or a wrong reference): the recording may not contain the "
                "reference sweep"
            ).format(margin=margin)
    return HealthCheck(
        "direct_sound",
        HealthStatus.INVALID,
        title,
        reason,
        affects=(METRIC_DECAY, METRIC_ENERGY, METRIC_REFLECTIONS, METRIC_PLACEMENT),
        evidence=evidence,
        fix=fix,
    )


def _clipping(result: AnalysisResult) -> HealthCheck:
    title = _("Level")
    clipping = result.clipping
    if clipping is None:
        return HealthCheck("level", HealthStatus.UNKNOWN, title, _imported_reason())
    evidence = clipping.to_dict()
    if clipping.clipped:
        if clipping.peak_dbfs < -0.1:
            reason = _(
                "{runs} flat-topped peaks ({samples} samples) at {peak:.1f} dBFS, the recording's "
                "highest level: it probably clipped before an export or a gain change"
            )
        else:
            reason = _(
                "{runs} flat-topped peaks ({samples} samples) at {peak:.1f} dBFS: the "
                "measurement chain was not linear"
            )
        return HealthCheck(
            "level",
            HealthStatus.INVALID,
            title,
            reason.format(runs=clipping.runs, samples=clipping.samples, peak=clipping.peak_dbfs),
            affects=(
                METRIC_DECAY,
                METRIC_ENERGY,
                METRIC_FREQUENCY_RESPONSE,
                METRIC_NOISE,
                METRIC_REFLECTIONS,
            ),
            evidence=evidence,
            fix=(
                _(
                    "Lower the playback level (the test signal's level or the monitor level) or "
                    "the input gain, and measure again."
                ),
            ),
        )
    if clipping.peak_dbfs > -HEADROOM_DB:
        return HealthCheck(
            "level",
            HealthStatus.WARNING,
            title,
            _(
                "the recording peaks at {peak:.1f} dBFS, within {headroom:g} dB of full scale: "
                "no flat tops were found, but there is no headroom left"
            ).format(peak=clipping.peak_dbfs, headroom=HEADROOM_DB),
            evidence=evidence,
            fix=(_("Lower the playback level or the input gain by about 6 dB and measure again."),),
        )
    return HealthCheck(
        "level",
        HealthStatus.GOOD,
        title,
        _("peak {peak:.1f} dBFS, no flat-topped peaks").format(peak=clipping.peak_dbfs),
        evidence=evidence,
    )


def _distortion(result: AnalysisResult) -> HealthCheck | None:
    if _imported(result):
        return None
    title = _("Distortion")
    ir = result.impulse_response
    if not _has_sweep_definition(result):
        return HealthCheck(
            "distortion",
            HealthStatus.UNKNOWN,
            title,
            _(
                "could not be checked: the harmonic responses cannot be separated without the sweep definition"
            ),
        )
    significant = [a for a in ir.aliased_distortion if a.significant]
    if significant:
        orders = list_join(str(a.order) for a in significant)
        level = max(
            (a.level_db for a in significant if a.level_db is not None), default=float("nan")
        )
        return HealthCheck(
            "distortion",
            HealthStatus.INVALID,
            title,
            _(
                "harmonic {orders} of the sweep folded back below the Nyquist frequency at "
                "{level:.0f} dB re the direct sound: a nonlinearity in the digital domain (a "
                "clipped playback bus or export, or a saturation plug-in) distorted the signal "
                "before the converter, and the folded products imitate a decay"
            ).format(orders=orders, level=level),
            affects=(METRIC_DECAY, METRIC_ENERGY),
            evidence={"aliased_distortion": [a.to_dict() for a in significant]},
            fix=(
                _(
                    "Lower the level in the playback path (the test signal's level, the track "
                    "and master faders), bypass saturation and limiting plug-ins, and measure again."
                ),
            ),
        )
    measured = [h for h in ir.harmonic_distortion if h.level_db is not None]
    evidence = {"harmonic_distortion": [h.to_dict() for h in ir.harmonic_distortion]}
    if measured:
        strongest = max(measured, key=lambda h: h.level_db if h.level_db is not None else -1e9)
        assert strongest.level_db is not None
        if strongest.level_db >= HARMONIC_WARNING_DB:
            return HealthCheck(
                "distortion",
                HealthStatus.WARNING,
                title,
                _(
                    "harmonic {order} of the sweep at {level:.0f} dB re the direct sound: the "
                    "loudspeaker or the chain distorts. The harmonic responses arrive ahead of "
                    "the room response, but their own decays run into it and can lengthen the "
                    "decay of some bands, and the chain is near its limit"
                ).format(order=strongest.order, level=strongest.level_db),
                affects=(METRIC_DECAY,),
                evidence=evidence,
                fix=(_("Lower the playback level by 6 to 10 dB and measure again."),),
            )
        return HealthCheck(
            "distortion",
            HealthStatus.GOOD,
            title,
            _("strongest harmonic {level:.0f} dB re the direct sound (harmonic {order})").format(
                level=strongest.level_db, order=strongest.order
            ),
            evidence=evidence,
        )
    return HealthCheck(
        "distortion",
        HealthStatus.GOOD,
        title,
        _("no harmonic response stands out of the noise"),
        evidence=evidence,
    )


#: Stored (English) device diagnostics: the take's warnings name buffer
#: problems, and the decay's reason names timing problems.
#: The stream's own flags, as older results stored them: a whole warning,
#: never a substring ("no overflow was detected" is not a fault).
_DEVICE_FLAGS = frozenset(
    {"input underflow", "input overflow", "output underflow", "output overflow"}
)
#: The sentences today's producers write (audio/portaudio.py, core/pipeline.py).
_DEVICE_MARKERS = ("buffer problem", "the audio device reported timing problems")
#: The stream ran at another rate than requested: the time scale is wrong.
_DEVICE_RATE_MARKER = ("the audio stream reported ", "instead of the requested")


def _device_fault(warning: str) -> bool:
    """Whether ``warning`` reports a fault of the audio device during the take.

    A refused *separate* loopback recording with device problems is not
    one: its sentence names the loopback, and the microphone take stands.
    """
    text = warning.strip()
    if text in _DEVICE_FLAGS:
        return True
    if any(marker in text for marker in _DEVICE_MARKERS):
        return True
    return text.startswith(_DEVICE_RATE_MARKER[0]) and _DEVICE_RATE_MARKER[1] in text


def _device(result: AnalysisResult) -> HealthCheck | None:
    reported = [w for w in result.warnings if _device_fault(w)]
    if not reported:
        return None
    first = reported[0].strip()
    if first in _DEVICE_FLAGS:
        # An older result stores the bare flag, which localize() cannot
        # translate on its own: say it as the recorder says it now.
        first = (
            "the audio device reported 1 buffer problem(s) during the take "
            f"({first}); the recording may contain dropouts"
        )
    return HealthCheck(
        "device",
        HealthStatus.INVALID,
        _("Audio device"),
        localize(first),
        affects=(METRIC_DECAY, METRIC_ENERGY, METRIC_FREQUENCY_RESPONSE, METRIC_REFLECTIONS),
        evidence={"warnings": reported},
        fix=(
            _(
                "Choose a larger buffer size or a higher latency, close other audio programs, "
                "and measure again."
            ),
        ),
    )


def _dropouts(result: AnalysisResult) -> HealthCheck | None:
    check = result.dropouts
    if check is None:
        return None
    title = _("Dropouts")
    evidence = check.to_dict()
    if not check.dropouts:
        return HealthCheck(
            "dropouts",
            HealthStatus.GOOD,
            title,
            _("no run of frozen or zero samples in the recorded sweep"),
            evidence=evidence,
        )
    longest = max(check.dropouts, key=lambda d: d.duration_ms)
    where = (
        _(" (where the sweep was at {hz:.0f} Hz)").format(hz=longest.sweep_hz)
        if longest.sweep_hz is not None
        else ""
    )
    reason = _(
        "{count} dropout(s) in the recorded sweep, {total:.0f} ms in all, the longest "
        "{longest:.0f} ms at {start:.2f} s{where}: samples were frozen or zero, and the "
        "frequency response is dented where the sweep was interrupted"
    ).format(
        count=len(check.dropouts),
        total=check.total_ms,
        longest=longest.duration_ms,
        start=longest.start_s,
        where=where,
    )
    status = (
        HealthStatus.INVALID
        if len(check.dropouts) >= DROPOUTS_INVALID_COUNT or check.total_ms >= DROPOUTS_INVALID_MS
        else HealthStatus.WARNING
    )
    return HealthCheck(
        "dropouts",
        status,
        title,
        reason,
        # A dropout also leaves a burst in the deconvolved response, which the
        # decays and the energy parameters of the bands below it can read
        # (docs/MEASUREMENT_METHODOLOGY.md, the dropout limit): a warning
        # lists them too.
        affects=(METRIC_FREQUENCY_RESPONSE, METRIC_RESONANCES, METRIC_DECAY, METRIC_ENERGY),
        evidence=evidence,
        fix=(
            _(
                "Choose a larger buffer size or a higher latency, close other audio programs, "
                "check the DAW's disk and CPU meters, and record again."
            ),
        ),
    )


def _needed_db(metric: DecayMetric, margin: float) -> float:
    """The decay range a metric needs: its lower evaluation limit plus the noise margin."""
    return abs(metric.evaluation_range_db[1]) + margin


def _decay_range(result: AnalysisResult) -> HealthCheck:
    title = _("Decay range")
    broadband = result.decay.broadband
    available = broadband.peak_to_noise_db
    margin_value = result.analysis_settings.get("decay_noise_margin_db", 10.0)
    margin = (
        float(margin_value)
        if isinstance(margin_value, int | float) and not isinstance(margin_value, bool)
        else 10.0
    )
    if available is None:
        return HealthCheck(
            "decay_range",
            HealthStatus.UNKNOWN,
            title,
            _("no decay range could be measured on the broadband response"),
        )
    t30 = _needed_db(broadband.t30, margin)
    t20 = _needed_db(broadband.t20, margin)
    edt = _needed_db(broadband.edt, margin)
    evidence = {
        "peak_to_noise_db": available,
        "needed_t30_db": t30,
        "needed_t20_db": t20,
        "needed_edt_db": edt,
    }
    fix = (
        _(
            "A longer sweep raises the range by 3 dB per doubling of its length; a higher "
            "playback level within the chain's headroom, a quieter room (ventilation and fans "
            "off) or the microphone nearer the loudspeaker raise it too."
        ),
    )
    if available >= t30:
        return HealthCheck(
            "decay_range",
            HealthStatus.GOOD,
            title,
            _(
                "{available:.0f} dB above the noise floor: enough for T30 (needs {needed:.0f} dB)"
            ).format(available=available, needed=t30),
            evidence=evidence,
        )
    if available >= t20:
        return HealthCheck(
            "decay_range",
            HealthStatus.WARNING,
            title,
            _(
                "{available:.0f} dB above the noise floor: enough for T20 but not for T30 "
                "(needs {needed:.0f} dB); RT60 is estimated from T20"
            ).format(available=available, needed=t30),
            affects=(METRIC_DECAY,),
            evidence=evidence,
            fix=fix,
        )
    if available >= edt:
        return HealthCheck(
            "decay_range",
            HealthStatus.WARNING,
            title,
            _(
                "{available:.0f} dB above the noise floor: only EDT can be evaluated (T20 needs "
                "{needed:.0f} dB)"
            ).format(available=available, needed=t20),
            affects=(METRIC_DECAY, METRIC_ENERGY),
            evidence=evidence,
            fix=fix,
        )
    return HealthCheck(
        "decay_range",
        HealthStatus.INVALID,
        title,
        _(
            "{available:.0f} dB above the noise floor: no reverberation time can be evaluated "
            "(EDT needs {needed:.0f} dB)"
        ).format(available=available, needed=edt),
        affects=(METRIC_DECAY, METRIC_ENERGY),
        evidence=evidence,
        fix=fix,
    )


def _noise(result: AnalysisResult) -> HealthCheck | None:
    if _imported(result):
        return None
    title = _("Noise floor")
    noise = result.noise
    if noise.rms_dbfs is None:
        # Exact zeros, or a level below the quantisation noise of a 24-bit
        # file: the analysis words both as digital silence.
        if any("digital silence" in note for note in noise.notes):
            return HealthCheck(
                "noise",
                HealthStatus.INVALID,
                title,
                _(
                    "the quiet part of the recording is exact digital silence, which a "
                    "microphone never records: a gate or noise reduction on the track, or the "
                    "test-signal track exported instead of the microphone track"
                ),
                affects=_EVERYTHING,
                evidence={"notes": list(noise.notes)},
                fix=(
                    _(
                        "Export the microphone track with no gate or noise reduction on it, and "
                        "measure again."
                    ),
                ),
            )
        return HealthCheck(
            "noise",
            HealthStatus.WARNING,
            title,
            _(
                "no quiet segment: the recording has no verified quiet part before the sweep or after the decay"
            ),
            affects=(METRIC_NOISE,),
            evidence={"notes": list(noise.notes)},
            fix=(
                _(
                    "Start recording at least one second before playback and keep the silence "
                    "after the sweep: the test file begins and ends with silence for this."
                ),
            ),
        )
    from reverbscope.interpretation.profiles import noise_segment_text

    return HealthCheck(
        "noise",
        HealthStatus.GOOD,
        title,
        _("{rms:.1f} dBFS RMS, measured on the {segment} segment").format(
            rms=noise.rms_dbfs, segment=noise_segment_text(noise.segment_source)
        ),
        evidence={"rms_dbfs": noise.rms_dbfs, "segment_source": noise.segment_source},
    )


def _length(result: AnalysisResult) -> HealthCheck:
    title = _("Recording length")
    ir = result.impulse_response
    evidence = {"valid_length_s": ir.valid_length_s}
    if ir.valid_length_s < SHORT_DECAY_S:
        truncated = any("next sweep pass" in note for note in ir.notes)
        reason = (
            _(
                "only {seconds:.2f} s of decay before the next sweep pass: long reverberation "
                "times cannot be evaluated"
            )
            if truncated
            else _(
                "only {seconds:.2f} s of decay after the direct sound: long reverberation times "
                "cannot be evaluated"
            )
        )
        return HealthCheck(
            "length",
            HealthStatus.WARNING,
            title,
            reason.format(seconds=ir.valid_length_s),
            affects=(METRIC_DECAY,),
            evidence=evidence,
            fix=(
                _(
                    "Export the whole take and keep at least three seconds of silence after the "
                    "sweep (the test file ends with silence for this); record one pass only."
                ),
            ),
        )
    return HealthCheck(
        "length",
        HealthStatus.GOOD,
        title,
        _("{seconds:.2f} s of decay after the direct sound").format(seconds=ir.valid_length_s),
        evidence=evidence,
    )


def _loopback(result: AnalysisResult) -> HealthCheck | None:
    lb = result.impulse_response.loopback
    if lb is None:
        return None
    title = _("Loopback")
    evidence = lb.to_dict(include_curves=False)
    if lb.compensation_applied:
        delay = (
            _(" (path delay {delay:.2f} ms)").format(delay=lb.path_delay_ms)
            if lb.path_delay_ms is not None
            else ""
        )
        return HealthCheck(
            "loopback",
            HealthStatus.GOOD,
            title,
            _(
                "compensation applied: the frequency response is relative to the interface return{delay}"
            ).format(delay=delay),
            evidence=evidence,
        )
    return HealthCheck(
        "loopback",
        HealthStatus.WARNING,
        title,
        localize(lb.reason) if lb.reason else _("compensation was not applied"),
        affects=(METRIC_FREQUENCY_RESPONSE,),
        evidence=evidence,
        fix=(
            _(
                "The loopback must be the interface's electrical return, recorded in the same "
                "pass as the microphone; export both channels from one take."
            ),
        ),
    )


def _any_valid(*metrics: DecayMetric | EnergyMetric) -> bool:
    return any(metric.validity is Validity.VALID for metric in metrics)


def _unavailable(result: AnalysisResult) -> tuple[str, ...]:
    """Metric groups the result reports no number for."""
    groups: list[str] = []
    bands = (result.decay.broadband, *result.decay.bands)
    if not any(_any_valid(band.edt, band.t20, band.t30) for band in bands):
        groups.append(METRIC_DECAY)
    if not any(_any_valid(band.c50, band.c80, band.d50, band.centre_time) for band in bands):
        groups.append(METRIC_ENERGY)
    if result.noise.rms_dbfs is None:
        groups.append(METRIC_NOISE)
    return tuple(groups)


def failure_guidance(exc: BaseException) -> tuple[str, ...]:
    """What to do after an analysis that failed, when the cause is known.

    The pipeline attaches the sweep speed it measured (``playback_speed``) to
    the error it raises for a sweep played at the wrong speed; the steps are
    the same as for a result that carries it.
    """
    speed = getattr(exc, "playback_speed", None)
    if isinstance(speed, PlaybackSpeed):
        steps, details = speed_fix(speed)
        return (*steps, *details)
    return ()


def affects_text(groups: tuple[str, ...]) -> str:
    """``groups`` as a list in the interface language."""
    return list_join(metric_group_text(group) for group in groups)


__all__ = [
    "DAW_SAMPLE_RATE_SETTINGS",
    "DAW_STRETCH_SETTINGS",
    "METRIC_GROUPS",
    "HealthCheck",
    "HealthReport",
    "HealthStatus",
    "affects_text",
    "assess",
    "failure_guidance",
    "metric_group_text",
    "speed_fix",
    "status_word",
]
