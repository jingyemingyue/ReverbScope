"""The analysis pipeline shared by the CLI, the GUI and the Python API.

recording + reference sweep
    -> channel selection and validation
    -> deconvolution (whole recording, no manual trimming)
    -> impulse response location (sweep passes, recording start check,
       excitation band, harmonic distortion indicators)
    -> linearity checks (flat-topped peaks, folded/aliased distortion products)
    -> decay analysis (broadband + octave bands, on h_full with a fixed lead-in;
       bands outside the excitation band withheld; all metrics unreliable when
       the direct sound is unverified, the recording clips, it contains
       aliased distortion or the device reported timing problems)
    -> frequency response (gated from the direct sound, with a lead-in)
    -> background noise (a quiet segment of the recording, verified quiet)
    -> early reflections
    -> potential low-frequency resonances
    -> placement geometry (only what the supplied tape measurements make
       identifiable; nothing horizontal is ever derived)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from scipy.signal import resample_poly

from roomscope.core.decay import analyze_decay, decay_lead_in_s
from roomscope.core.deconvolution import (
    PASS_LEVEL_DB,
    LocatedImpulseResponse,
    confidence_label,
    deconvolve,
    harmonic_distortion_levels,
    locate_impulse_response,
)
from roomscope.core.frequency_response import frequency_response
from roomscope.core.linearity import aliased_distortion_levels, detect_clipping
from roomscope.core.loopback import (
    LOOPBACK_FR_REFERENCE,
    assess_loopback,
    compensate,
    make_loopback_result,
)
from roomscope.core.noise import analyze_noise, quiet_segment_candidates, sweep_level_dbfs
from roomscope.core.placement import estimate_placement
from roomscope.core.playback_speed import diagnose_playback_speed
from roomscope.core.reflections import detect_early_reflections
from roomscope.core.resonance import detect_potential_resonances
from roomscope.core.sweep import (
    REFERENCE_SILENCE_THRESHOLD_DB,
    active_region,
    design_spectral_inverse,
    estimate_reference_band_hz,
    excitation_band_hz,
    frequency_at_sweep_time,
    inverse_filter,
)
from roomscope.errors import (
    AnalysisError,
    ConfigurationError,
    InvalidAudioError,
    SampleRateMismatchError,
)
from roomscope.i18n import _, diag
from roomscope.models.audio import AudioSignal, FloatArray
from roomscope.models.configuration import AnalysisSettings, SweepSettings
from roomscope.models.result import (
    EXCITATION_SOURCE_DECLARED,
    EXCITATION_SOURCE_ESTIMATED,
    EXCITATION_SOURCE_SETTINGS,
    EXCITATION_SOURCE_UNKNOWN,
    AliasedDistortion,
    AnalysisResult,
    ClippingCheck,
    DecayResult,
    ExcitationBand,
    HarmonicDistortion,
    ImpulseResponseResult,
    LoopbackResult,
    NoiseResult,
    PlacementLength,
    PlacementResult,
    PlaybackSpeed,
    Validity,
)
from roomscope.version import __version__

SILENCE_THRESHOLD_DBFS = -80.0
#: Periods of the lowest excited frequency analysed before the direct sound
#: for the frequency response (see :func:`frequency_response_lead_in_s`).
FREQUENCY_RESPONSE_LEAD_IN_PERIODS = 10.0


@dataclass(frozen=True)
class Reference:
    """The excitation signal that was played.

    Either ``settings`` (preferred: the sweep is regenerated exactly, at any
    sample rate) or ``signal`` (an arbitrary mono reference at
    ``sample_rate``, inverted by regularised spectral division).
    """

    settings: SweepSettings | None = None
    signal: FloatArray | None = None
    sample_rate: int | None = None

    def __post_init__(self) -> None:
        if self.settings is None and self.signal is None:
            raise ConfigurationError("a reference needs sweep settings or a reference signal")
        if self.signal is not None and self.sample_rate is None:
            raise ConfigurationError("a reference signal needs its sample rate")

    @classmethod
    def from_settings(cls, settings: SweepSettings) -> Reference:
        return cls(settings=settings)

    @classmethod
    def from_signal(cls, signal: FloatArray, sample_rate: int) -> Reference:
        mono = signal if signal.ndim == 1 else np.ascontiguousarray(signal[:, 0])
        return cls(signal=np.asarray(mono, dtype=np.float64), sample_rate=sample_rate)


#: How far (s) the recording may start after the sweep began, beyond the
#: sweep's fade-in, before the analysis is refused (latency jitter of a DAW
#: export). Frequencies swept in the missing part are removed from the
#: excitation band.
RECORDING_START_TOLERANCE_S = 0.010
#: Report trimmed reference silences longer than this (s).
REFERENCE_TRIM_NOTE_S = 0.010


@dataclass(frozen=True)
class _PreparedReference:
    inverse: FloatArray
    #: Length of the (trimmed) sweep the inverse belongs to.
    reference_length: int
    sweep_settings: SweepSettings | None
    warnings: tuple[str, ...]
    excitation_band: ExcitationBand
    #: ``L`` of the sweep (s) when the sweep definition is known.
    sweep_rate_s: float | None
    #: The trimmed reference signal (signal references only).
    trimmed_signal: FloatArray | None
    #: Samples removed before / after the active part of a reference signal.
    lead_trim: int = 0
    tail_trim: int = 0


def _prepare_reference(reference: Reference, sample_rate: int) -> _PreparedReference:
    warnings: list[str] = []
    if reference.settings is not None:
        settings = reference.settings
        if settings.sample_rate != sample_rate:
            try:
                settings = settings.with_sample_rate(sample_rate)
            except ConfigurationError as exc:
                raise SampleRateMismatchError(
                    _(
                        "recording is at {sample_rate} Hz but the sweep cannot be regenerated "
                        "at that rate: {error}"
                    ).format(sample_rate=sample_rate, error=exc)
                ) from exc
            warnings.append(
                diag(
                    "reference sweep regenerated at the recording sample rate ({sample_rate} Hz); "
                    "it was defined at {defined_rate} Hz",
                    sample_rate=sample_rate,
                    defined_rate=reference.settings.sample_rate,
                )
            )
        low, high = excitation_band_hz(settings)
        return _PreparedReference(
            inverse=inverse_filter(settings),
            reference_length=settings.sweep_samples,
            sweep_settings=settings,
            warnings=tuple(warnings),
            excitation_band=ExcitationBand(
                low_hz=low, high_hz=high, source=EXCITATION_SOURCE_SETTINGS
            ),
            sweep_rate_s=settings.sweep_rate,
            trimmed_signal=None,
        )
    assert reference.signal is not None and reference.sample_rate is not None
    signal = reference.signal
    if reference.sample_rate != sample_rate:
        gcd = int(np.gcd(sample_rate, reference.sample_rate))
        signal = np.asarray(
            resample_poly(signal, sample_rate // gcd, reference.sample_rate // gcd),
            dtype=np.float64,
        )
        warnings.append(
            diag(
                "reference signal resampled from {from_rate} Hz to {to_rate} Hz",
                from_rate=reference.sample_rate,
                to_rate=sample_rate,
            )
        )
    try:
        first, stop = active_region(signal)
    except ConfigurationError as exc:
        raise InvalidAudioError(
            _("reference signal cannot be used: {error}").format(error=exc)
        ) from exc
    lead, tail = first, signal.shape[0] - stop
    trimmed = np.ascontiguousarray(signal[first:stop])
    if lead / sample_rate > REFERENCE_TRIM_NOTE_S or tail / sample_rate > REFERENCE_TRIM_NOTE_S:
        warnings.append(
            diag(
                "the reference audio starts with {lead_s:.2f} s and ends with {tail_s:.2f} s of "
                "near-silence (below {threshold_db:g} dB re its peak); it was removed so that "
                "the reference is the sweep itself, and sweep positions refer to the sweep, "
                "not to the start of the file",
                lead_s=lead / sample_rate,
                tail_s=tail / sample_rate,
                threshold_db=REFERENCE_SILENCE_THRESHOLD_DB,
            )
        )
    warnings.append(
        diag(
            "reference given as an audio file without a RoomScope sweep definition; "
            "using regularised spectral division instead of the analytic inverse filter, "
            "and the excitation band is estimated from the reference spectrum"
        )
    )
    try:
        design = design_spectral_inverse(trimmed, sample_rate)
    except ConfigurationError as exc:
        raise InvalidAudioError(
            _("reference signal cannot be used: {error}").format(error=exc)
        ) from exc
    return _PreparedReference(
        inverse=design.inverse,
        reference_length=trimmed.shape[0],
        sweep_settings=None,
        warnings=tuple(warnings),
        excitation_band=ExcitationBand(
            low_hz=design.band_low_hz,
            high_hz=design.band_high_hz,
            source=EXCITATION_SOURCE_ESTIMATED,
            note=diag(
                "the reference covers about {low_hz:.0f}-{high_hz:.0f} Hz (-3 dB); the outer "
                "1/3 octave at each end is used for the regularisation roll-off and excluded",
                low_hz=design.reference_low_hz,
                high_hz=design.reference_high_hz,
            ),
        ),
        sweep_rate_s=None,
        trimmed_signal=trimmed,
        lead_trim=lead,
        tail_trim=tail,
    )


def _check_recording_start(
    prepared: _PreparedReference, missing: int, sample_rate: int
) -> tuple[ExcitationBand, str | None]:
    """Refuse a recording that starts inside the sweep; narrow the band for small gaps.

    ``missing`` is the number of sweep samples before the start of the recording.
    """
    band = prepared.excitation_band
    if missing <= 0:
        return band, None
    missing_s = missing / sample_rate
    settings = prepared.sweep_settings
    fade_in_s = settings.fade_in_s if settings is not None else 0.0
    tolerance = round((fade_in_s + RECORDING_START_TOLERANCE_S) * sample_rate)
    if settings is not None:
        lost_hz = frequency_at_sweep_time(settings, missing_s)
        if missing > tolerance:
            raise InvalidAudioError(
                _(
                    "the recording starts about {missing_s:.2f} s after the sweep began, so "
                    "frequencies below about {lost_hz:.0f} Hz were not recorded. Start the "
                    "recording before playback (the test file begins with silence for this "
                    "purpose) and export the whole take"
                ).format(missing_s=missing_s, lost_hz=lost_hz)
            )
        if lost_hz <= band.low_hz:
            return band, None
        new_low = lost_hz
    else:
        if missing > tolerance:
            raise InvalidAudioError(
                _(
                    "the recording starts about {missing_s:.2f} s after the reference sweep "
                    "began, so the first part of the sweep (for a rising sweep: its lowest "
                    "frequencies) was not recorded. Start the recording before playback and "
                    "export the whole take"
                ).format(missing_s=missing_s)
            )
        assert prepared.trimmed_signal is not None
        recorded_part = prepared.trimmed_signal[missing:]
        try:
            new_low = estimate_reference_band_hz(recorded_part, sample_rate)[0]
        except ConfigurationError:
            new_low = band.low_hz
        if new_low <= band.low_hz:
            return band, None
    if new_low >= band.high_hz:
        raise InvalidAudioError(
            _("the recording starts after the swept range; no part of the sweep can be analysed")
        )
    note = diag(
        "the recording starts {missing_ms:.0f} ms after the sweep began; the excitation "
        "band now starts at {new_low_hz:.0f} Hz instead of {old_low_hz:.0f} Hz",
        missing_ms=missing_s * 1000.0,
        new_low_hz=new_low,
        old_low_hz=band.low_hz,
    )
    return (
        ExcitationBand(low_hz=new_low, high_hz=band.high_hz, source=band.source, note=note),
        note,
    )


def _validate_recording(mono: FloatArray, sample_rate: int) -> tuple[ClippingCheck, list[str]]:
    """Refuse an unusable recording and report flat-topped (clipped) peaks."""
    warnings: list[str] = []
    peak = float(np.max(np.abs(mono)))
    if peak <= 0.0 or 20.0 * np.log10(peak) < SILENCE_THRESHOLD_DBFS:
        # diag(): on the loopback path this message is stored (LoopbackResult.reason).
        raise InvalidAudioError(
            diag(
                "recording is silent (peak below {threshold_dbfs:g} dBFS); check the input "
                "routing and, on macOS, that the app has microphone access (System Settings > "
                "Privacy & Security > Microphone)",
                threshold_dbfs=SILENCE_THRESHOLD_DBFS,
            )
        )
    clipping = detect_clipping(mono)
    if clipping.clipped:
        if clipping.peak_dbfs < -0.1:
            warnings.append(
                diag(
                    "recording has {runs} flat-topped peaks ({samples} samples) at "
                    "{peak_dbfs:.1f} dBFS, its highest level: probable clipping before an "
                    "export or a gain change, because the flat tops are below full scale; "
                    "lower the playback or input level and measure again",
                    runs=clipping.runs,
                    samples=clipping.samples,
                    peak_dbfs=clipping.peak_dbfs,
                )
            )
        else:
            warnings.append(
                diag(
                    "recording has {runs} flat-topped peaks ({samples} samples) at "
                    "{peak_dbfs:.1f} dBFS, its highest level: probable clipping; lower the "
                    "playback or input level and measure again",
                    runs=clipping.runs,
                    samples=clipping.samples,
                    peak_dbfs=clipping.peak_dbfs,
                )
            )
    if mono.shape[0] < sample_rate:
        raise InvalidAudioError(diag("recording is shorter than one second"))
    return clipping, warnings


def _segment_around_pass(
    h_full: FloatArray,
    located: LocatedImpulseResponse,
    sample_rate: int,
    lead_in_s: float,
) -> tuple[FloatArray, int]:
    """``h_full`` around the analysed pass and the direct sound's index in it.

    The segment starts ``lead_in_s`` before the direct sound (limited by the
    start of ``h_full`` and by an earlier sweep pass) and ends where the
    located impulse response ends, so that time-reversed band filters and the
    frequency response see the whole response of the direct sound whatever
    ``ir_pre_delay_ms`` is.
    """
    peak = located.peak_index
    start = max(0, peak - round(lead_in_s * sample_rate))
    earlier = [p for p in located.pass_peak_indices if p < peak]
    if earlier:
        start = max(start, earlier[-1] + 1)
    stop = peak + (located.samples.shape[0] - located.direct_index)
    return np.asarray(h_full[start:stop], dtype=np.float64), peak - start


def _analyze_decay_of_pass(
    h_full: FloatArray,
    located: LocatedImpulseResponse,
    sample_rate: int,
    settings: AnalysisSettings,
    excitation_band: ExcitationBand,
) -> DecayResult:
    """Decay analysis on ``h_full`` around the analysed pass."""
    segment, direct_index = _segment_around_pass(
        h_full, located, sample_rate, decay_lead_in_s(settings)
    )
    return analyze_decay(
        segment,
        sample_rate,
        settings,
        direct_index=direct_index,
        excitation_band=excitation_band,
    )


def frequency_response_lead_in_s(
    excitation_band: ExcitationBand, settings: AnalysisSettings
) -> float:
    """Time kept before the direct sound for the frequency response (s).

    The deconvolved direct sound is a band-limited pulse whose pre-ringing is
    part of its low-frequency content: analysing only ``ir_pre_delay_ms``
    before it costs about 1.2 dB at 31.5 Hz and 0.9 dB at 63 Hz on a loopback
    of the default sweep. Ten periods of the lowest excited frequency are
    kept, which is where the low-frequency response stops changing (measured:
    within 0.03 dB of the value at a 1.5 s lead-in).
    """
    return max(
        settings.ir_pre_delay_ms / 1000.0,
        FREQUENCY_RESPONSE_LEAD_IN_PERIODS / max(excitation_band.low_hz, 1.0),
    )


def _decay_unreliable_reasons(
    confidence: str,
    margin_db: float | None,
    clipped: bool,
    aliased: tuple[AliasedDistortion, ...] = (),
    playback_speed: PlaybackSpeed | None = None,
    *,
    device_timing_problems: bool = False,
) -> list[str]:
    """Measurement-level reasons why no decay metric may be reported as valid."""
    reasons: list[str] = []
    if device_timing_problems:
        reasons.append(
            diag(
                "the audio device reported timing problems in this take, so its decay and energy "
                "metrics are unreliable. Check the stream settings and repeat the measurement"
            )
        )
    if playback_speed is not None:
        reasons.append(
            diag(
                "the sweep was played at {speed_percent:.1f} % of the speed it was generated "
                "at, so the deconvolved response is not the room's impulse response",
                speed_percent=playback_speed.speed_ratio * 100.0,
            )
        )
    if confidence == "low":
        if margin_db is None:
            reasons.append(
                diag(
                    "direct-sound detection confidence is low (pre-peak margin not checkable): "
                    "the recording may not contain the reference sweep"
                )
            )
        else:
            reasons.append(
                diag(
                    "direct-sound detection confidence is low (pre-peak margin "
                    "{margin_db:.1f} dB): the recording may not contain the reference sweep",
                    margin_db=margin_db,
                )
            )
    if clipped:
        reasons.append(
            diag(
                "the recording clips, so the measurement chain was not linear and the "
                "deconvolved response is not the room's impulse response"
            )
        )
    significant = [a for a in aliased if a.significant]
    if significant:
        orders = ", ".join(str(a.order) for a in significant)
        level = max(a.level_db or -math.inf for a in significant)
        reasons.append(
            diag(
                "aliased distortion (folded harmonic {orders} at {level_db:.0f} dB re the direct "
                "sound) spreads over the impulse response after the direct sound and imitates "
                "a decay",
                orders=orders,
                level_db=level,
            )
        )
    return reasons


#: ``AudioSignal.source`` of takes RoomScope played itself (Standalone Mode
#: and the demo backend). No DAW sits between the generated sweep and the
#: output there, so a speed estimate off 1.0 is estimation bias on a noisy or
#: very reverberant take, not a sample-rate mismatch or a time-stretch.
SELF_PLAYED_SOURCES = frozenset({"standalone", "fake"})


def _playback_speed(
    mono: FloatArray, sample_rate: int, reference: Reference, source: str | None
) -> PlaybackSpeed | None:
    """Diagnose a sweep played at the wrong speed (needs the sweep definition).

    A diagnosis only: if it cannot be computed, the analysis goes on without it.
    Takes RoomScope played itself are not checked (:data:`SELF_PLAYED_SOURCES`).
    """
    if reference.settings is None or source in SELF_PLAYED_SOURCES:
        return None
    try:
        return diagnose_playback_speed(mono, sample_rate, reference.settings)
    except (ValueError, FloatingPointError, np.linalg.LinAlgError):
        return None


def _explain_playback_speed(
    exc: InvalidAudioError,
    mono: FloatArray,
    sample_rate: int,
    reference: Reference,
    source: str | None,
) -> None:
    """Append a wrong sweep speed, when there is one, to ``exc``'s message.

    A sweep played faster than generated is shorter than the reference and
    seems to start late; the speed is the cause the user can fix. The
    exception keeps its type and attributes.
    """
    speed = _playback_speed(mono, sample_rate, reference, source)
    if speed is not None and exc.args:
        exc.args = (f"{exc.args[0]}. However, {speed.describe()}", *exc.args[1:])


def _select_mic_and_loopback(
    recording: AudioSignal,
    settings: AnalysisSettings,
    loopback: AudioSignal | None,
) -> tuple[FloatArray, int, str | None, FloatArray | None, int | None]:
    """Return ``(mic, mic_channel, warning, loopback_samples, loopback_channel)``.

    ``loopback`` is a separate file; ``settings.loopback_channel`` is a 0-based
    channel of ``recording``. They must not name the same samples as the
    microphone. A two-channel DAW export uses the channel setting.
    """
    lb_channel = settings.loopback_channel
    if loopback is not None and recording.sample_rate != loopback.sample_rate:
        raise SampleRateMismatchError(
            _(
                "the loopback file and the recording have different sample rates; "
                "export both from the same take"
            )
        )
    if lb_channel is not None and lb_channel >= recording.n_channels:
        raise InvalidAudioError(
            _(
                "loopback_channel {channel} does not exist (recording has {count} channel(s))"
            ).format(channel=lb_channel, count=recording.n_channels)
        )
    if lb_channel is not None and settings.channel is not None and lb_channel == settings.channel:
        raise ConfigurationError(_("loopback_channel must differ from the microphone channel"))

    warning: str | None
    if settings.channel is None and lb_channel is not None and recording.n_channels > 1:
        rms = np.sqrt(np.mean(recording.samples.astype(np.float64) ** 2, axis=0))
        scores = rms.copy()
        scores[lb_channel] = -1.0
        channel = int(np.argmax(scores))
        warning = diag(
            "recording has {count} channels; channel {channel} (highest RMS excluding loopback "
            "channel {loopback_channel}) was analysed",
            count=recording.n_channels,
            channel=channel,
            loopback_channel=lb_channel,
        )
        mono = recording.channel(channel)
    else:
        mono, channel, warning = recording.select_channel(settings.channel)

    lb_samples: FloatArray | None = None
    reported_channel: int | None = None
    if loopback is not None:
        if loopback.n_channels == 1:
            lb_samples = loopback.channel(0)
        elif lb_channel is not None and lb_channel < loopback.n_channels:
            lb_samples = loopback.channel(lb_channel)
            reported_channel = lb_channel
        else:
            lb_samples = loopback.channel(0)
        reported_channel = reported_channel if reported_channel is not None else None
        tol = round(RECORDING_START_TOLERANCE_S * recording.sample_rate)
        if abs(lb_samples.shape[0] - mono.shape[0]) > tol:
            raise InvalidAudioError(
                _(
                    "the loopback file and the recording differ in length by more than "
                    "{tolerance_ms:.0f} ms; export both from the same take"
                ).format(tolerance_ms=RECORDING_START_TOLERANCE_S * 1000.0)
            )
        if lb_samples.shape[0] < mono.shape[0]:
            lb_samples = np.pad(lb_samples, (0, mono.shape[0] - lb_samples.shape[0]))
        elif lb_samples.shape[0] > mono.shape[0]:
            lb_samples = np.asarray(lb_samples[: mono.shape[0]], dtype=np.float64)
    elif lb_channel is not None:
        lb_samples = recording.channel(lb_channel)
        reported_channel = lb_channel
    return mono, channel, warning, lb_samples, reported_channel


def _locate_pass(
    h_full: FloatArray,
    *,
    recording_length: int,
    prepared: _PreparedReference,
    settings: AnalysisSettings,
    sample_rate: int,
) -> LocatedImpulseResponse:
    fade_in_s = prepared.sweep_settings.fade_in_s if prepared.sweep_settings is not None else 0.0
    return locate_impulse_response(
        h_full,
        recording_length=recording_length,
        reference_length=prepared.reference_length,
        sample_rate=sample_rate,
        pre_delay_ms=settings.ir_pre_delay_ms,
        max_length_s=settings.ir_max_length_s,
        sweep_rate_s=prepared.sweep_rate_s,
        start_tolerance_samples=round((fade_in_s + RECORDING_START_TOLERANCE_S) * sample_rate),
    )


def _placement_against_loopback_bound(
    placement: PlacementResult,
    loopback: LoopbackResult,
    distance_m: float | None,
) -> PlacementResult:
    """Mark placement unreliable when the tape is longer than the path-delay bound."""
    bound = loopback.distance_upper_bound_m
    if (
        not loopback.compensation_applied
        or bound is None
        or distance_m is None
        or distance_m <= bound
    ):
        return placement
    from dataclasses import replace

    reason = diag(
        "the tape-measured loudspeaker distance ({distance_m:.2f} m) exceeds the "
        "loopback path-delay bound ({bound_m:.2f} m); the tape cannot be longer than "
        "what sound had time to travel",
        distance_m=distance_m,
        bound_m=bound,
    )

    def mark(length: PlacementLength) -> PlacementLength:
        joined = "; ".join(part for part in (length.reason, reason) if part)
        if length.validity is Validity.VALID:
            return replace(length, validity=Validity.UNRELIABLE, reason=joined)
        return replace(length, reason=joined or reason)

    return replace(
        placement,
        source_height_m=mark(placement.source_height_m),
        ceiling_height_m=mark(placement.ceiling_height_m),
        horizontal_separation_m=mark(placement.horizontal_separation_m),
        notes=(*placement.notes, reason),
    )


def analyze(
    recording: AudioSignal,
    reference: Reference,
    settings: AnalysisSettings | None = None,
    *,
    loopback: AudioSignal | None = None,
) -> AnalysisResult:
    """Run the analysis chain and return an :class:`AnalysisResult`.

    ``loopback`` is an optional separate electrical-return recording. A channel
    of ``recording`` can be used instead via ``settings.loopback_channel``.
    """
    settings = settings or AnalysisSettings()
    sample_rate = recording.sample_rate
    warnings: list[str] = list(recording.device_warnings)

    mono, channel, channel_warning, lb_samples, lb_channel = _select_mic_and_loopback(
        recording, settings, loopback
    )
    if channel_warning:
        warnings.append(channel_warning)
    clipping, validation_warnings = _validate_recording(mono, sample_rate)
    warnings.extend(validation_warnings)

    prepared = _prepare_reference(reference, sample_rate)
    warnings.extend(prepared.warnings)

    try:
        h_full = deconvolve(mono, prepared.inverse)
    except InvalidAudioError as exc:
        _explain_playback_speed(exc, mono, sample_rate, reference, recording.source)
        raise
    located = _locate_pass(
        h_full,
        recording_length=mono.shape[0],
        prepared=prepared,
        settings=settings,
        sample_rate=sample_rate,
    )
    loopback_result: LoopbackResult | None = None
    if lb_samples is not None:
        try:
            if loopback is not None and loopback.device_warnings:
                warnings.extend(loopback.device_warnings)
                raise AnalysisError(
                    diag(
                        "the separate loopback recording has device timing problems; "
                        "loopback compensation was not applied"
                    )
                )
            lb_clipping, _lb_notes = _validate_recording(lb_samples, sample_rate)
            h_lb = deconvolve(lb_samples, prepared.inverse)
            lb_located = _locate_pass(
                h_lb,
                recording_length=lb_samples.shape[0],
                prepared=prepared,
                settings=settings,
                sample_rate=sample_rate,
            )
            assessment = assess_loopback(lb_located, h_lb, sample_rate, clipped=lb_clipping.clipped)
        except (InvalidAudioError, AnalysisError) as exc:
            loopback_result = LoopbackResult(
                channel=lb_channel,
                compensation_applied=False,
                reason=str(exc),
            )
        else:
            mic_peak = located.peak_index
            if assessment.accepted and assessment.fir is not None:
                h_full = compensate(
                    h_full,
                    assessment.fir,
                    sample_rate,
                    prepared.excitation_band,
                    fir_peak_index=assessment.fir_peak_index,
                )
                located = _locate_pass(
                    h_full,
                    recording_length=mono.shape[0],
                    prepared=prepared,
                    settings=settings,
                    sample_rate=sample_rate,
                )
            loopback_result = make_loopback_result(
                channel=lb_channel,
                assessment=assessment,
                sample_rate=sample_rate,
                reference_length=prepared.reference_length,
                mic_peak_index=mic_peak,
                temperature_c=settings.placement_temperature_c,
                compensation_applied=bool(assessment.accepted and assessment.fir is not None),
            )
        if loopback_result.compensation_applied:
            warnings.append(
                diag(
                    "loopback compensation applied: the frequency response is relative to "
                    "the interface return"
                )
            )
        elif loopback_result.reason:
            warnings.append(loopback_result.reason)

    ir = located.samples
    ir_notes: list[str] = []
    # The excitation band is what later stages (decay, frequency response,
    # resonances) must respect: impulse.excitation_band / result.excitation_band.
    try:
        band, start_note = _check_recording_start(
            prepared, -located.sweep_start_raw_index, sample_rate
        )
    except InvalidAudioError as exc:
        _explain_playback_speed(exc, mono, sample_rate, reference, recording.source)
        raise
    if start_note:
        ir_notes.append(start_note)
    if located.sweep_passes > 1:
        order = located.pass_peak_indices.index(located.peak_index) + 1
        ir_notes.append(
            diag(
                "the recording contains {passes} sweep passes (pulses within {pass_level_db:g} dB "
                "of the strongest); pass {order}, starting at {start_s:.2f} s, was analysed and "
                "the others were ignored. Record a single pass for a clean measurement",
                passes=located.sweep_passes,
                pass_level_db=PASS_LEVEL_DB,
                order=order,
                start_s=located.sweep_start_index_in_recording / sample_rate,
            )
        )
    if located.truncated_by_next_pass:
        ir_notes.append(
            diag(
                "the impulse response ends where the next sweep pass starts "
                "({length_s:.2f} s after the direct sound)",
                length_s=located.valid_length_samples / sample_rate,
            )
        )
    if located.valid_length_samples / sample_rate < 1.0:
        ir_notes.append(
            diag(
                "only {length_s:.2f} s of decay were recorded after the sweep; long "
                "reverberation times cannot be evaluated",
                length_s=located.valid_length_samples / sample_rate,
            )
        )
    confidence = confidence_label(located.pre_peak_margin_db)
    if located.pre_peak_margin_db is None:
        # confidence_label(None) is always "low".
        ir_notes.append(
            diag(
                "there is no content before the direct sound to check the detection against; "
                "direct-sound detection confidence is low"
            )
        )
    elif confidence == "medium":
        ir_notes.append(
            diag(
                "content before the direct sound is only {margin_db:.1f} dB below it (noise, "
                "pre-ringing or a wrong reference); direct-sound detection confidence is medium",
                margin_db=located.pre_peak_margin_db,
            )
        )
    elif confidence != "high":
        ir_notes.append(
            diag(
                "content before the direct sound is only {margin_db:.1f} dB below it (noise, "
                "pre-ringing or a wrong reference); direct-sound detection confidence is low",
                margin_db=located.pre_peak_margin_db,
            )
        )
    # A sweep played at the wrong speed (a DAW sample-rate mismatch or
    # time-stretch) is one cause of an unidentifiable direct sound that the
    # user can fix; the check costs one short-time spectrum. Only a failed
    # detection is checked: a sweep played even 2 % off leaves a pre-peak
    # margin of a few dB (low), and a medium margin means the generated sweep
    # did deconvolve the recording.
    playback_speed = (
        _playback_speed(mono, sample_rate, reference, recording.source)
        if confidence == "low"
        else None
    )
    if playback_speed is not None:
        ir_notes.append(playback_speed.describe())
    warnings.extend(ir_notes)

    harmonics: tuple[HarmonicDistortion, ...] = ()
    aliased: tuple[AliasedDistortion, ...] = ()
    if prepared.sweep_settings is not None:
        harmonics = harmonic_distortion_levels(
            h_full, located, sample_rate=sample_rate, excitation_band=band
        )
        # Folded (aliased) products land *after* the direct sound, where the
        # harmonic windows and the pre-peak margin cannot see them.
        aliased = aliased_distortion_levels(
            mono,
            h_full,
            sample_rate=sample_rate,
            settings=prepared.sweep_settings,
            excitation_band=band,
            peak_index=located.peak_index,
            reference_length=prepared.reference_length,
        )
        significant = [a for a in aliased if a.significant]
        if significant:
            orders = ", ".join(str(a.order) for a in significant)
            level = max(a.level_db or -math.inf for a in significant)
            note = diag(
                "harmonic {orders} of the sweep was folded back below the Nyquist frequency "
                "({level_db:.0f} dB re the direct sound): a nonlinearity in the digital domain (a "
                "playback bus or export that clipped, or a saturation plug-in without "
                "oversampling) distorted the signal before the converter. The folded products "
                "land after the direct sound and imitate a long decay, so the decay metrics "
                "cannot be trusted. Lower the level in the playback path and measure again",
                orders=orders,
                level_db=level,
            )
            ir_notes.append(note)
            warnings.append(note)

    impulse = ImpulseResponseResult(
        sample_rate=sample_rate,
        samples=ir,
        direct_sound_index=located.direct_index,
        pre_delay_samples=located.pre_delay_samples,
        peak_value=located.peak_value,
        valid_length_s=located.valid_length_samples / sample_rate,
        pre_peak_margin_db=located.pre_peak_margin_db,
        direct_sound_confidence=confidence,
        sweep_start_in_recording_s=located.sweep_start_index_in_recording / sample_rate,
        notes=tuple(ir_notes),
        excitation_band=band,
        sweep_passes=located.sweep_passes,
        first_sweep_start_in_recording_s=located.first_sweep_start_index_in_recording / sample_rate,
        harmonic_distortion=harmonics,
        aliased_distortion=aliased,
        loopback=loopback_result,
        playback_speed=playback_speed,
    )

    decay = _analyze_decay_of_pass(h_full, located, sample_rate, settings, band)
    unreliable = _decay_unreliable_reasons(
        confidence,
        located.pre_peak_margin_db,
        clipping.clipped,
        aliased,
        playback_speed,
        device_timing_problems=bool(recording.device_warnings),
    )
    if unreliable:
        decay = decay.with_all_unreliable("; ".join(unreliable))
    warnings.extend(decay.notes)

    # The frequency response and the resonance search run on h_full with a
    # lead-in, so that the pre-ringing of the band-limited direct sound (its
    # low-frequency content) is kept whatever ir_pre_delay_ms is.
    fr_segment, fr_direct = _segment_around_pass(
        h_full, located, sample_rate, frequency_response_lead_in_s(band, settings)
    )
    fr_reference = (
        LOOPBACK_FR_REFERENCE
        if loopback_result is not None and loopback_result.compensation_applied
        else None
    )
    response = frequency_response(
        fr_segment,
        sample_rate,
        direct_index=fr_direct,
        window_s=settings.fr_window_s,
        smoothing_fraction=settings.fr_smoothing_fraction,
        excitation_band=band,
        reference=fr_reference,
    )
    # A gate hides exactly the long decays the resonance search looks for, so
    # that search always uses the ungated response.
    ungated = (
        response
        if not response.gated
        else frequency_response(
            fr_segment,
            sample_rate,
            direct_index=fr_direct,
            smoothing_fraction=0,
            excitation_band=band,
        )
    )
    if response.gated:
        warnings.append(
            diag(
                "the frequency response is gated to {window_ms:.0f} ms after the direct sound, "
                "so its resolution is {resolution_hz:.1f} Hz; the resonance search uses the "
                "ungated response",
                window_ms=response.window_s * 1000.0,
                resolution_hz=response.resolution_hz,
            )
        )

    last_pass = located.pass_peak_indices[-1] if located.pass_peak_indices else located.peak_index
    candidates = quiet_segment_candidates(
        recording_length=mono.shape[0],
        sample_rate=sample_rate,
        # Before the *first* sweep pass and after the *last* one, so that no
        # other pass can be measured as background noise.
        first_sweep_start_index=located.first_sweep_start_index_in_recording,
        last_sweep_end_index=last_pass
        - (prepared.reference_length - 1)
        + prepared.reference_length,
        min_segment_s=settings.noise_min_segment_s,
    )
    noise = analyze_noise(
        mono,
        sample_rate,
        candidates[0] if candidates else None,
        octave_bands_hz=settings.octave_bands_hz,
        min_segment_s=settings.noise_min_segment_s,
        sweep_level_dbfs=sweep_level_dbfs(
            mono,
            sample_rate,
            located.sweep_start_index_in_recording,
            prepared.reference_length,
        ),
        fallbacks=candidates[1:],
    )
    reflections = detect_early_reflections(
        ir,
        sample_rate,
        located.direct_index,
        min_delay_ms=settings.reflections_min_delay_ms,
        max_delay_ms=settings.reflections_max_delay_ms,
        threshold_db=settings.reflections_threshold_db,
        prominence_db=settings.reflections_prominence_db,
        direct_sound_confidence=confidence,
    )
    placement = estimate_placement(
        reflections,
        distance_m=settings.placement_distance_m,
        mic_height_m=settings.placement_mic_height_m,
        temperature_c=settings.placement_temperature_c,
    )
    if loopback_result is not None:
        placement = _placement_against_loopback_bound(
            placement, loopback_result, settings.placement_distance_m
        )
    resonances = detect_potential_resonances(
        fr_segment,
        sample_rate,
        ungated,
        max_hz=settings.resonance_max_hz,
        min_prominence_db=settings.resonance_min_prominence_db,
        direct_index=fr_direct,
        excitation_band=band,
    )
    sweep_dict = prepared.sweep_settings.to_dict() if prepared.sweep_settings is not None else {}
    analysis_dict = settings.to_dict()
    analysis_dict["channel_analysed"] = channel
    return AnalysisResult(
        created_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
        sample_rate=sample_rate,
        sweep_settings=sweep_dict,
        analysis_settings=analysis_dict,
        impulse_response=impulse,
        decay=decay,
        frequency_response=response,
        noise=noise,
        reflections=reflections,
        resonances=resonances,
        clipping=clipping,
        placement=placement,
        warnings=tuple(warnings),
        roomscope_version=__version__,
    )


def _blank_noise(*, note: str) -> NoiseResult:
    return NoiseResult(
        segment_source=None,
        segment_start_s=None,
        segment_duration_s=None,
        rms_dbfs=None,
        peak_dbfs=None,
        band_levels_dbfs=(),
        psd_frequencies_hz=None,
        psd_db=None,
        notes=(note,),
    )


def _mark_decay_not_computed(decay: DecayResult, reason: str) -> DecayResult:
    from dataclasses import replace

    from roomscope.models.result import BandDecay, DecayMetric, EnergyMetric, Validity

    def blank(metric: DecayMetric) -> DecayMetric:
        return replace(metric, seconds=None, validity=Validity.NOT_COMPUTED, reason=reason)

    def blank_energy(metric: EnergyMetric) -> EnergyMetric:
        return replace(metric, value=None, validity=Validity.NOT_COMPUTED, reason=reason)

    def blank_band(band: BandDecay) -> BandDecay:
        return replace(
            band,
            edt=blank(band.edt),
            t20=blank(band.t20),
            t30=blank(band.t30),
            c50=blank_energy(band.c50),
            c80=blank_energy(band.c80),
            d50=blank_energy(band.d50),
            centre_time=blank_energy(band.centre_time),
            rt60_estimate_s=None,
            rt60_basis=None,
            curvature_percent=None,
        )

    return replace(
        decay,
        broadband=blank_band(decay.broadband),
        bands=tuple(blank_band(b) for b in decay.bands),
        notes=(*decay.notes, reason),
    )


#: An imported impulse response must have its strongest sample at least this
#: far above the content before it (the "low" direct-sound confidence limit).
IMPORTED_IR_MIN_MARGIN_DB = 10.0


def analyze_impulse_response(
    ir: AudioSignal,
    settings: AnalysisSettings | None = None,
    *,
    excitation_band: tuple[float, float] | None = None,
) -> AnalysisResult:
    """Analyse an impulse-response WAV from another tool (no deconvolution).

    Distortion indicators, sweep-position checks and the noise section are
    skipped. ``excitation_band`` is what the caller declares; without it every
    band metric is :attr:`~roomscope.models.result.Validity.NOT_COMPUTED`.

    A file whose strongest sample does not stand at least
    ``IMPORTED_IR_MIN_MARGIN_DB`` above the content before it (a sweep, a
    recording, noise, or an IR whose direct sound is weaker than a later
    arrival) is refused with :class:`AnalysisError` instead of being
    analysed as if it were an impulse response. The content right before the
    peak is excluded for max(2 ms, 2 / high_hz) so that the rise of a
    band-limited direct sound does not count. A file that starts at its peak
    (no pre-roll) cannot be checked this way; it is analysed with
    direct-sound confidence "low".
    """
    from roomscope.core.deconvolution import confidence_label, locate_impulse_response
    from roomscope.core.frequency_response import frequency_response
    from roomscope.core.placement import estimate_placement
    from roomscope.core.reflections import detect_early_reflections
    from roomscope.core.resonance import detect_potential_resonances

    settings = settings or AnalysisSettings()
    warnings: list[str] = [
        *ir.device_warnings,
        diag(
            "impulse response imported; deconvolution, sweep-position checks and "
            "distortion indicators were skipped"
        ),
    ]
    mono, channel, channel_warning = ir.select_channel(settings.channel)
    if channel_warning:
        warnings.append(channel_warning)
    sample_rate = ir.sample_rate
    if mono.shape[0] < round(0.05 * sample_rate):
        raise InvalidAudioError(_("impulse response is shorter than 50 ms"))

    if excitation_band is not None:
        low, high = excitation_band
        if not (low > 0.0 and high > low):
            raise ConfigurationError(
                _("excitation_band must be a (low_hz, high_hz) pair with high > low > 0")
            )
    # A band-limited direct sound rises over about two periods of its upper
    # band edge before it peaks (a sub-woofer IR low-passed at 80 Hz takes
    # ~25 ms); that rise must not count as "content before the direct sound".
    near_ms = 2.0 if excitation_band is None else max(2.0, 2000.0 / float(excitation_band[1]))
    located = locate_impulse_response(
        np.asarray(mono, dtype=np.float64),
        recording_length=int(mono.shape[0]),
        reference_length=1,
        sample_rate=sample_rate,
        pre_delay_ms=settings.ir_pre_delay_ms,
        max_length_s=settings.ir_max_length_s,
        sweep_rate_s=None,
        margin_near_ms=near_ms,
    )
    margin = located.pre_peak_margin_db
    if margin is not None and margin < IMPORTED_IR_MIN_MARGIN_DB:
        raise AnalysisError(
            _(
                "this file cannot be analysed as an impulse response: its strongest sample is "
                "only {margin_db:.1f} dB above the content before it (at least "
                "{required_db:g} dB is required). It may be a recording (a recording of the "
                "test sweep is analysed with `roomscope analyze`), or an IR whose direct sound "
                "is weaker than a later arrival, which RoomScope cannot use as time zero. For "
                "a band-limited IR, declare its band with --band"
            ).format(margin_db=margin, required_db=IMPORTED_IR_MIN_MARGIN_DB)
        )
    declared: ExcitationBand | None
    if excitation_band is None:
        declared = ExcitationBand(
            low_hz=20.0,
            high_hz=min(20000.0, sample_rate / 2.0),
            source=EXCITATION_SOURCE_UNKNOWN,
            note=diag("excitation band was not declared; band metrics are not computed"),
        )
    else:
        low, high = excitation_band
        declared = ExcitationBand(
            low_hz=float(low), high_hz=float(high), source=EXCITATION_SOURCE_DECLARED
        )

    confidence = confidence_label(located.pre_peak_margin_db)
    impulse = ImpulseResponseResult(
        sample_rate=sample_rate,
        samples=located.samples,
        direct_sound_index=located.direct_index,
        pre_delay_samples=located.pre_delay_samples,
        peak_value=located.peak_value,
        valid_length_s=located.valid_length_samples / sample_rate,
        pre_peak_margin_db=located.pre_peak_margin_db,
        direct_sound_confidence=confidence,
        sweep_start_in_recording_s=0.0,
        notes=tuple(warnings),
        excitation_band=declared,
        sweep_passes=1,
        first_sweep_start_in_recording_s=0.0,
    )
    decay = _analyze_decay_of_pass(
        np.asarray(mono, dtype=np.float64), located, sample_rate, settings, declared
    )
    if declared.source == EXCITATION_SOURCE_UNKNOWN:
        decay = _mark_decay_not_computed(
            decay, diag("excitation band unknown (imported impulse response; declare --band)")
        )
    if ir.device_warnings:
        decay = decay.with_all_unreliable(
            "; ".join(
                _decay_unreliable_reasons(confidence, margin, False, device_timing_problems=True)
            )
        )
        warnings.extend(decay.notes)
    fr_segment, fr_direct = _segment_around_pass(
        np.asarray(mono, dtype=np.float64),
        located,
        sample_rate,
        frequency_response_lead_in_s(declared, settings),
    )
    response = frequency_response(
        fr_segment,
        sample_rate,
        direct_index=fr_direct,
        window_s=settings.fr_window_s,
        smoothing_fraction=settings.fr_smoothing_fraction,
        excitation_band=declared if declared.source != EXCITATION_SOURCE_UNKNOWN else None,
    )
    ungated = (
        response
        if not response.gated
        else frequency_response(
            fr_segment,
            sample_rate,
            direct_index=fr_direct,
            smoothing_fraction=0,
            excitation_band=declared if declared.source != EXCITATION_SOURCE_UNKNOWN else None,
        )
    )
    reflections = detect_early_reflections(
        located.samples,
        sample_rate,
        located.direct_index,
        min_delay_ms=settings.reflections_min_delay_ms,
        max_delay_ms=settings.reflections_max_delay_ms,
        threshold_db=settings.reflections_threshold_db,
        prominence_db=settings.reflections_prominence_db,
        direct_sound_confidence=confidence,
    )
    placement = estimate_placement(
        reflections,
        distance_m=settings.placement_distance_m,
        mic_height_m=settings.placement_mic_height_m,
        temperature_c=settings.placement_temperature_c,
    )
    resonances = detect_potential_resonances(
        fr_segment,
        sample_rate,
        ungated,
        max_hz=settings.resonance_max_hz,
        min_prominence_db=settings.resonance_min_prominence_db,
        direct_index=fr_direct,
        excitation_band=declared if declared.source != EXCITATION_SOURCE_UNKNOWN else None,
    )
    analysis_dict = settings.to_dict()
    analysis_dict["channel_analysed"] = channel
    return AnalysisResult(
        created_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
        sample_rate=sample_rate,
        sweep_settings={},
        analysis_settings=analysis_dict,
        impulse_response=impulse,
        decay=decay,
        frequency_response=response,
        noise=_blank_noise(note=diag("no recording segment exists (imported impulse response)")),
        reflections=reflections,
        resonances=resonances,
        clipping=None,
        placement=placement,
        warnings=tuple(warnings),
        roomscope_version=__version__,
    )


def synthetic_recording(
    settings: SweepSettings,
    room_ir: FloatArray,
    *,
    noise_rms: float = 0.0,
    gain: float = 1.0,
    seed: int | None = 0,
) -> AudioSignal:
    """Convolve the measurement signal with ``room_ir`` and add white noise.

    Used by the tests to prove the round trip without a real room; it is not
    used by the analysis itself.
    """
    from scipy.signal import fftconvolve

    from roomscope.core.sweep import measurement_signal

    excitation = measurement_signal(settings)
    recorded = np.asarray(fftconvolve(excitation, room_ir, mode="full"), dtype=np.float64) * gain
    if noise_rms > 0.0:
        rng = np.random.default_rng(seed)
        recorded = recorded + rng.normal(0.0, noise_rms, recorded.shape[0])
    return AudioSignal(samples=recorded, sample_rate=settings.sample_rate, source="synthetic")


__all__ = ["Reference", "analyze", "analyze_impulse_response", "synthetic_recording"]
