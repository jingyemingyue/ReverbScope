"""Analysis result models.

Every metric carries its unit in the field name (``_s``, ``_hz``, ``_db``,
``_dbfs``, ``_ms``) and a :class:`Validity` so that front ends can never show a
number without knowing whether it is trustworthy. Curves are kept as NumPy
arrays in memory; :meth:`AnalysisResult.to_dict` converts them for JSON export.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

import numpy as np
import numpy.typing as npt

from roomscope.i18n import N_, diag

FloatArray = npt.NDArray[np.float64]

RESULT_SCHEMA_VERSION = 1


class Validity(StrEnum):
    """Whether a metric may be shown as a measured value."""

    VALID = "valid"
    INSUFFICIENT_RANGE = "insufficient_decay_range"
    UNRELIABLE = "unreliable"
    NOT_COMPUTED = "not_computed"
    #: The band lies (partly) outside the frequency range the excitation
    #: covered; the band contains only leakage and noise, so nothing is reported.
    OUTSIDE_EXCITATION = "outside_excitation_range"
    #: A comparison delta that cannot be formed (one or both sides missing a
    #: VALID number, or the two sessions are not comparable).
    NOT_COMPARABLE = "not_comparable"


def _array_to_list(values: FloatArray | None, decimals: int = 4) -> list[float] | None:
    if values is None:
        return None
    return [float(v) for v in np.round(values, decimals)]


def _join_reasons(existing: str | None, reason: str) -> str:
    if not existing:
        return reason
    if reason in existing:
        return existing
    return f"{existing}; {reason}"


@dataclass(frozen=True)
class DecayMetric:
    """One reverberation-time estimate (EDT, T20 or T30) extrapolated to 60 dB."""

    name: str
    seconds: float | None
    validity: Validity
    #: Evaluation range on the Schroeder curve (dB, e.g. (-5, -25) for T20).
    evaluation_range_db: tuple[float, float]
    #: Degree of non-linearity of the fit, xi = 1000 * (1 - r^2) in permille
    #: (ISO 3382-2:2008, Annex B).
    nonlinearity_permille: float | None = None
    reason: str | None = None

    def marked_unreliable(self, reason: str) -> DecayMetric:
        """This metric marked UNRELIABLE with ``reason``.

        A VALID metric keeps its number and becomes UNRELIABLE; an UNRELIABLE
        one gets the reason appended; metrics without a number
        (insufficient range, outside the excitation, not computed) are
        returned unchanged because their status is already stronger.
        """
        if self.validity not in (Validity.VALID, Validity.UNRELIABLE):
            return self
        return replace(
            self,
            validity=Validity.UNRELIABLE,
            reason=_join_reasons(
                self.reason if self.validity is Validity.UNRELIABLE else None, reason
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "seconds": self.seconds,
            "validity": str(self.validity),
            "evaluation_range_db": list(self.evaluation_range_db),
            "nonlinearity_permille": self.nonlinearity_permille,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EnergyMetric:
    """One early/late energy parameter (C50, C80, D50 or centre time).

    ``value`` is in ``unit`` (``dB``, ``%`` or ``s``). It is ``None`` unless
    the validity is :attr:`Validity.VALID` or :attr:`Validity.UNRELIABLE`.
    """

    name: str
    value: float | None
    unit: str
    validity: Validity
    reason: str | None = None

    def marked_unreliable(self, reason: str) -> EnergyMetric:
        """This metric marked UNRELIABLE with ``reason``.

        Same rule as :meth:`DecayMetric.marked_unreliable`: a number that was
        VALID is kept and marked UNRELIABLE; a metric that already has no
        number is left as it is.
        """
        if self.validity not in (Validity.VALID, Validity.UNRELIABLE):
            return self
        return replace(
            self,
            validity=Validity.UNRELIABLE,
            reason=_join_reasons(
                self.reason if self.validity is Validity.UNRELIABLE else None, reason
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "validity": str(self.validity),
            "reason": self.reason,
        }


def _not_computed_energy(name: str, unit: str) -> EnergyMetric:
    """An energy parameter an older result file did not store."""
    return EnergyMetric(name=name, value=None, unit=unit, validity=Validity.NOT_COMPUTED)


#: Time origin of all decay times (``edc_time_s``, ``onset_time_s``,
#: ``truncation_time_s``).
DECAY_TIME_ORIGIN = diag("direct sound (time 0 = the detected broadband direct sound)")


@dataclass(frozen=True)
class BandDecay:
    """Decay analysis of one frequency band (or the broadband IR).

    All times share one origin, :data:`DECAY_TIME_ORIGIN`: 0 s is the
    broadband direct sound (or the start of the impulse response when the
    analysis was run without a known direct sound). Band values that cannot be
    measured (e.g. a band outside the excitation range) are ``None``.
    """

    band_label: str
    #: Nominal mid-band frequency (the label value, e.g. 63.0); ``None`` for broadband.
    center_hz: float | None
    #: Band edges (IEC 61260-1 base-10, around :attr:`mid_band_hz`).
    low_hz: float | None
    high_hz: float | None
    #: Level of the noise floor relative to the loudest 20 ms block after the onset (dB).
    noise_floor_db: float | None
    #: Dynamic range available for decay evaluation (dB above the noise floor).
    peak_to_noise_db: float | None
    #: Truncation point of the Schroeder integration (s after the direct sound).
    truncation_time_s: float | None
    edt: DecayMetric
    t20: DecayMetric
    t30: DecayMetric
    #: Estimated RT60 and which metric it is based on ("T30" preferred, then
    #: "T20"); only ever taken from a VALID metric.
    rt60_estimate_s: float | None
    rt60_basis: str | None
    #: Curvature C = 100 * (T30 / T20 - 1) in percent (ISO 3382-2:2008,
    #: Annex B); computed only when both T20 and T30 are VALID.
    curvature_percent: float | None
    #: Bandwidth-time product B*T of the band filter; low values mean the filter
    #: ringing dominates (Jacobsen & Rindel 1987).
    filter_bt_product: float | None
    filter_warning: str | None
    #: Decimated Schroeder decay curve for display and export (time in s after
    #: the direct sound; a band curve starts slightly before 0 because the
    #: time-reversed band filter moves the direct sound's energy earlier).
    edc_time_s: FloatArray = field(repr=False)
    edc_db: FloatArray = field(repr=False)
    #: Start of the Schroeder integration (s after the direct sound, usually
    #: slightly negative): where the squared response first rises to within
    #: 20 dB of its maximum.
    onset_time_s: float | None = None
    #: Exact IEC 61260-1 mid-band frequency the band filter is centred on.
    mid_band_hz: float | None = None
    #: Why values of this band are withheld or unreliable (non-straight decay,
    #: implausible noise truncation, outside the excitation range, ...).
    warnings: tuple[str, ...] = ()
    #: Early/late energy at 50 ms (speech clarity), same truncation as the decay.
    c50: EnergyMetric = field(default_factory=lambda: _not_computed_energy("C50", "dB"))
    #: Early/late energy at 80 ms (music clarity).
    c80: EnergyMetric = field(default_factory=lambda: _not_computed_energy("C80", "dB"))
    #: Share of energy in the first 50 ms, in percent.
    d50: EnergyMetric = field(default_factory=lambda: _not_computed_energy("D50", "%"))
    #: Energy-weighted centre time, in seconds.
    centre_time: EnergyMetric = field(default_factory=lambda: _not_computed_energy("Ts", "s"))

    def with_all_unreliable(self, reason: str) -> BandDecay:
        """All metrics marked UNRELIABLE with ``reason``; no RT60 estimate and
        no curvature are kept (they would rest on unreliable metrics)."""
        return replace(
            self,
            edt=self.edt.marked_unreliable(reason),
            t20=self.t20.marked_unreliable(reason),
            t30=self.t30.marked_unreliable(reason),
            c50=self.c50.marked_unreliable(reason),
            c80=self.c80.marked_unreliable(reason),
            d50=self.d50.marked_unreliable(reason),
            centre_time=self.centre_time.marked_unreliable(reason),
            rt60_estimate_s=None,
            rt60_basis=None,
            curvature_percent=None,
        )

    def to_dict(self, include_curves: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "band_label": self.band_label,
            "center_hz": self.center_hz,
            "mid_band_hz": self.mid_band_hz,
            "low_hz": self.low_hz,
            "high_hz": self.high_hz,
            "noise_floor_db": self.noise_floor_db,
            "peak_to_noise_db": self.peak_to_noise_db,
            "onset_time_s": self.onset_time_s,
            "truncation_time_s": self.truncation_time_s,
            "edt": self.edt.to_dict(),
            "t20": self.t20.to_dict(),
            "t30": self.t30.to_dict(),
            "rt60_estimate_s": self.rt60_estimate_s,
            "rt60_basis": self.rt60_basis,
            "curvature_percent": self.curvature_percent,
            "filter_bt_product": self.filter_bt_product,
            "filter_warning": self.filter_warning,
            "warnings": list(self.warnings),
            "c50": self.c50.to_dict(),
            "c80": self.c80.to_dict(),
            "d50": self.d50.to_dict(),
            "centre_time": self.centre_time.to_dict(),
        }
        if include_curves:
            data["edc_time_s"] = _array_to_list(self.edc_time_s)
            data["edc_db"] = _array_to_list(self.edc_db, 2)
        return data


@dataclass(frozen=True)
class DecayResult:
    method: str
    broadband: BandDecay
    bands: tuple[BandDecay, ...]
    #: Result-level notes (bands outside the excitation, band warnings,
    #: reasons for marking every metric unreliable).
    notes: tuple[str, ...] = ()
    time_origin: str = DECAY_TIME_ORIGIN

    def with_all_unreliable(self, reason: str) -> DecayResult:
        """Every decay metric (broadband and bands) marked UNRELIABLE with
        ``reason``, e.g. when the direct sound could not be verified or the
        recording clips. ``reason`` is also added to :attr:`notes`."""
        return replace(
            self,
            broadband=self.broadband.with_all_unreliable(reason),
            bands=tuple(b.with_all_unreliable(reason) for b in self.bands),
            notes=(
                *self.notes,
                diag("all decay metrics are marked unreliable: {reason}", reason=reason),
            ),
        )

    def to_dict(self, include_curves: bool = True) -> dict[str, Any]:
        return {
            "method": self.method,
            "time_origin": self.time_origin,
            "broadband": self.broadband.to_dict(include_curves),
            "bands": [b.to_dict(include_curves) for b in self.bands],
            "notes": list(self.notes),
        }


#: ``ExcitationBand.source`` when the band follows from the sweep definition.
EXCITATION_SOURCE_SETTINGS = N_("sweep settings")
#: ``ExcitationBand.source`` when the band was estimated from a reference WAV.
EXCITATION_SOURCE_ESTIMATED = N_("estimated from reference audio")
#: ``ExcitationBand.source`` when the caller declared the band (imported IR).
EXCITATION_SOURCE_DECLARED = N_("declared by the user")
#: ``ExcitationBand.source`` when an imported IR has no declared band.
EXCITATION_SOURCE_UNKNOWN = N_("unknown")


@dataclass(frozen=True)
class ExcitationBand:
    """Frequency range in which the measurement was fully excited.

    Outside ``[low_hz, high_hz]`` the deconvolved impulse response contains
    only fade/regularisation roll-off, filter-skirt leakage and noise, so no
    metric may be reported as a measured value there. ``source`` is
    :data:`EXCITATION_SOURCE_SETTINGS` (derived from the sweep definition) or
    :data:`EXCITATION_SOURCE_ESTIMATED` (estimated from the reference audio).
    See ``core/sweep.py`` for how each is derived.
    """

    low_hz: float
    high_hz: float
    source: str
    note: str | None = None

    def contains(self, low_hz: float, high_hz: float) -> bool:
        """True when ``[low_hz, high_hz]`` lies completely inside the band."""
        return self.low_hz <= low_hz and high_hz <= self.high_hz

    def to_dict(self) -> dict[str, Any]:
        return {
            "low_hz": self.low_hz,
            "high_hz": self.high_hz,
            "source": self.source,
            "note": self.note,
        }


@dataclass(frozen=True)
class HarmonicDistortion:
    """Level of the k-th harmonic response separated by the ESS method (Farina 2000).

    The k-th harmonic response precedes the linear impulse response by
    ``offset_s = L * ln(k)``. ``level_db`` is the energy of that response
    relative to the linear response, both taken with the same short window and
    compared over ``band_hz`` (the part of the excitation band where the
    harmonic and the linear response overlap). It is a broadband indicator of
    loudspeaker/chain distortion, not a calibrated THD figure. ``level_db`` is
    ``None`` when the response is not at least ``DETECTION_MARGIN_DB`` above
    ``floor_db`` (the same measure for harmonic-free content before the direct
    sound) or cannot be measured; ``reason`` then says why.
    """

    order: int
    offset_s: float
    level_db: float | None
    floor_db: float | None
    band_hz: tuple[float, float] | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "offset_s": self.offset_s,
            "level_db": self.level_db,
            "floor_db": self.floor_db,
            "band_hz": list(self.band_hz) if self.band_hz is not None else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ClippingCheck:
    """Flat-top (plateau) test of the recording.

    Clipping is recognised by runs of samples at the file's *own* maximum
    magnitude, not by an absolute threshold: a recording that clipped and was
    then attenuated plateaus below full scale, and a clean recording
    normalised to 0 dBFS has no plateau at all. ``peak_dbfs`` is the level
    those plateaus sit at.
    """

    peak_dbfs: float
    #: Number of flat-topped runs found.
    runs: int
    #: Total number of samples in them.
    samples: int
    clipped: bool
    #: Quantisation step of the file (``None`` for float data); the plateau
    #: tolerance follows it so that a dithered export is still recognised.
    quantisation_step: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "peak_dbfs": self.peak_dbfs,
            "runs": self.runs,
            "samples": self.samples,
            "clipped": self.clipped,
            "quantisation_step": self.quantisation_step,
        }


@dataclass(frozen=True)
class AliasedDistortion:
    """Level of a *folded* (aliased) harmonic product, dB re the linear response.

    A nonlinearity in the digital domain folds the k-th harmonic back to
    ``|k*f(t) - m*fs|``. Unlike the alias-free harmonics of
    :class:`HarmonicDistortion`, these products land *after* the direct sound
    and imitate a long decay, so a significant one makes every decay metric
    unreliable. ``level_db`` is ``None`` when the product cannot be told from
    ``floor_db`` (the same measure for content before its expected position)
    or cannot be measured at all; ``reason`` then says why.
    """

    order: int
    #: Frequency range of the folded trajectory that was analysed (Hz).
    band_hz: tuple[float, float] | None
    level_db: float | None
    floor_db: float | None
    #: True when the product is both measurable and strong enough to matter.
    significant: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "band_hz": list(self.band_hz) if self.band_hz is not None else None,
            "level_db": self.level_db,
            "floor_db": self.floor_db,
            "significant": self.significant,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LoopbackResult:
    """Optional electrical reference-channel compensation (populated in 0.3).

    ``None`` on :attr:`ImpulseResponseResult.loopback` means no loopback was
    used. A present object with ``compensation_applied`` false means a channel
    was offered and refused.
    """

    channel: int | None
    compensation_applied: bool
    reason: str | None = None
    latency_samples: int | None = None
    path_delay_ms: float | None = None
    distance_upper_bound_m: float | None = None
    interface_response_hz: FloatArray | None = field(default=None, repr=False)
    interface_response_db: FloatArray | None = field(default=None, repr=False)
    notes: tuple[str, ...] = ()

    def to_dict(self, include_curves: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "channel": self.channel,
            "compensation_applied": self.compensation_applied,
            "reason": self.reason,
            "latency_samples": self.latency_samples,
            "path_delay_ms": self.path_delay_ms,
            "distance_upper_bound_m": self.distance_upper_bound_m,
            "notes": list(self.notes),
        }
        if include_curves:
            data["interface_response_hz"] = _array_to_list(self.interface_response_hz, 3)
            data["interface_response_db"] = _array_to_list(self.interface_response_db, 2)
        return data


#: Kinds of :class:`PlaybackSpeed` (see ``roomscope.core.playback_speed``).
KIND_SAMPLE_RATE = "sample_rate_mismatch"
KIND_TIME_STRETCH = "time_stretch"


@dataclass(frozen=True)
class PlaybackSpeed:
    """The sweep speed measured in a recording, relative to the generated sweep."""

    #: Speed the sweep was played at relative to the generated sweep: the
    #: generated ``L`` over the ``L`` measured in the recording (1.0: as
    #: generated; 0.919: a 48 kHz file played at 44.1 kHz, 8.1 % slow).
    speed_ratio: float
    #: :data:`KIND_SAMPLE_RATE` or :data:`KIND_TIME_STRETCH`.
    kind: str
    #: Sample rate the sweep file was generated at (Hz).
    generated_rate_hz: int
    #: For a sample-rate mismatch: the common rate the file was played at (Hz).
    played_rate_hz: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "speed_ratio": self.speed_ratio,
            "kind": self.kind,
            "generated_rate_hz": self.generated_rate_hz,
            "played_rate_hz": self.played_rate_hz,
        }

    def describe(self) -> str:
        """One English sentence for the result notes."""
        if self.kind == KIND_SAMPLE_RATE and self.played_rate_hz is not None:
            return diag(
                "the sweep in the recording runs at {percent:.1f} % of the "
                "speed it was generated at: a file generated at {generated_hz} Hz was "
                "played at {played_hz} Hz without sample-rate conversion (a DAW project "
                "at another sample rate that did not convert the file on import). Generate the "
                "sweep at the project's sample rate, or let the DAW convert it on import, and "
                "measure again",
                percent=self.speed_ratio * 100.0,
                generated_hz=self.generated_rate_hz,
                played_hz=self.played_rate_hz,
            )
        return diag(
            "the sweep in the recording runs at {percent:.1f} % of the speed "
            "it was generated at: the DAW time-stretched it (Warp, Flex Time, Follow Tempo, "
            "elastic audio or a stretch mode). Switch time-stretching off for the sweep clip "
            "and measure again",
            percent=self.speed_ratio * 100.0,
        )


@dataclass(frozen=True)
class ImpulseResponseResult:
    sample_rate: int
    #: Impulse response samples (linear amplitude, relative units). The first
    #: sample is ``pre_delay_samples`` before the detected direct sound. The
    #: inverse filter is normalised so that the in-band magnitude of a perfect
    #: loopback is 1 (0 dB).
    samples: FloatArray = field(repr=False)
    direct_sound_index: int
    pre_delay_samples: int
    #: Signed value of the strongest sample (the direct-sound peak). Its size
    #: depends on the excited bandwidth relative to the sample rate and on the
    #: sub-sample position of the direct sound (up to about -3 dB for a
    #: half-sample offset), so it is *not* a measure of the chain gain; use the
    #: frequency response for levels.
    peak_value: float
    #: Length of IR that is fully supported by the recording (s): up to the end
    #: of the recording or the start of the next sweep pass, whichever is first.
    valid_length_s: float
    #: Ratio (dB) between the direct-sound peak and the strongest content in the
    #: pre-peak window, excluding the windows of the harmonic pre-responses when
    #: the sweep is known. It reflects noise, pre-ringing and ambiguity caused by
    #: a wrong reference. ``None`` when there is no content before the direct
    #: sound to check. High is good.
    pre_peak_margin_db: float | None
    direct_sound_confidence: str
    #: Estimated start of the analysed sweep pass in the recording (s).
    sweep_start_in_recording_s: float
    notes: tuple[str, ...] = ()
    #: Frequency range that the excitation actually covered.
    excitation_band: ExcitationBand | None = None
    #: Number of sweep passes found in the recording (the strongest is analysed).
    sweep_passes: int = 1
    #: Start of the first sweep pass in the recording (s); equals
    #: ``sweep_start_in_recording_s`` for a single pass. ``None`` if unknown.
    first_sweep_start_in_recording_s: float | None = None
    #: Harmonic distortion indicators for k = 2..5 (empty when the sweep
    #: definition is unknown).
    harmonic_distortion: tuple[HarmonicDistortion, ...] = ()
    #: Folded (aliased) distortion products, which land *after* the direct
    #: sound (empty when the sweep definition is unknown).
    aliased_distortion: tuple[AliasedDistortion, ...] = ()
    #: Electrical reference channel used to compensate the interface (``None``
    #: when the measurement had no loopback).
    loopback: LoopbackResult | None = None
    #: The sweep was not played at the speed it was generated at (a DAW
    #: sample-rate mismatch or time-stretch). Only checked, and only set, when
    #: direct-sound detection confidence is low.
    playback_speed: PlaybackSpeed | None = None

    @property
    def direct_sound_time_s(self) -> float:
        return self.direct_sound_index / self.sample_rate

    def to_dict(self, include_curves: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "sample_rate": self.sample_rate,
            "length_samples": int(self.samples.shape[0]),
            "direct_sound_index": self.direct_sound_index,
            "direct_sound_time_s": self.direct_sound_time_s,
            "pre_delay_samples": self.pre_delay_samples,
            "peak_value": self.peak_value,
            "valid_length_s": self.valid_length_s,
            "pre_peak_margin_db": self.pre_peak_margin_db,
            "direct_sound_confidence": self.direct_sound_confidence,
            "sweep_start_in_recording_s": self.sweep_start_in_recording_s,
            "first_sweep_start_in_recording_s": self.first_sweep_start_in_recording_s,
            "sweep_passes": self.sweep_passes,
            "excitation_band": (
                self.excitation_band.to_dict() if self.excitation_band is not None else None
            ),
            "harmonic_distortion": [h.to_dict() for h in self.harmonic_distortion],
            "aliased_distortion": [a.to_dict() for a in self.aliased_distortion],
            "loopback": self.loopback.to_dict() if self.loopback is not None else None,
            "playback_speed": (
                self.playback_speed.to_dict() if self.playback_speed is not None else None
            ),
            "notes": list(self.notes),
        }
        if include_curves:
            data["samples"] = _array_to_list(self.samples, 8)
        return data


@dataclass(frozen=True)
class FrequencyResponseResult:
    """Magnitude response of the impulse response (relative dB).

    The analysed segment runs from :attr:`lead_in_s` before the direct sound
    to :attr:`window_s` after it. Outside :attr:`excitation_band` the curve is
    roll-off, leakage and noise, not a measured response.
    """

    frequencies_hz: FloatArray = field(repr=False)
    #: Unsmoothed magnitude (dB, relative). Always preserved.
    magnitude_db_raw: FloatArray = field(repr=False)
    #: Smoothed magnitude (dB, relative) or ``None`` when smoothing is disabled.
    magnitude_db_smoothed: FloatArray | None = field(repr=False)
    smoothing_fraction: int
    #: Analysed time after the direct sound (s); the gate length when gated.
    window_s: float
    #: Analysed time before the direct sound (s): the pre-ringing of the
    #: band-limited direct sound belongs to its low-frequency content.
    lead_in_s: float = 0.0
    #: True frequency resolution, 1 / (lead_in_s + window_s) in Hz. Zero
    #: padding interpolates between these; it does not add resolution.
    resolution_hz: float = float("inf")
    #: Distance between exported points (Hz), i.e. sample_rate / FFT length.
    bin_spacing_hz: float = float("inf")
    #: True when a gate (``window_s``) was applied to the impulse response.
    gated: bool = False
    #: Frequency range the excitation actually covered.
    excitation_band: ExcitationBand | None = None
    reference: str = diag("relative dB (0 dB = flat loopback of the reference sweep)")

    def to_dict(self, include_curves: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "smoothing_fraction": self.smoothing_fraction,
            "window_s": self.window_s,
            "lead_in_s": self.lead_in_s,
            "resolution_hz": self.resolution_hz,
            "bin_spacing_hz": self.bin_spacing_hz,
            "gated": self.gated,
            "excitation_band": (
                self.excitation_band.to_dict() if self.excitation_band is not None else None
            ),
            "reference": self.reference,
            "points": int(self.frequencies_hz.shape[0]),
        }
        if include_curves:
            data["frequencies_hz"] = _array_to_list(self.frequencies_hz, 3)
            data["magnitude_db_raw"] = _array_to_list(self.magnitude_db_raw, 2)
            data["magnitude_db_smoothed"] = _array_to_list(self.magnitude_db_smoothed, 2)
        return data


@dataclass(frozen=True)
class HumCandidate:
    """Mains-hum evidence for one base frequency (50 or 60 Hz).

    ``harmonics`` lists every harmonic of ``base_hz`` that stands out of the
    noise PSD, including those shared with the other mains base (multiples of
    300 Hz). Only ``distinct_harmonics_hz`` - the harmonics that belong to
    this base alone - decide ``detected``, and at most one of the two bases is
    ever reported as detected (``note`` says when the other one was dropped).
    """

    base_hz: float
    #: (frequency_hz, prominence_db) for each detected harmonic.
    harmonics: tuple[tuple[float, float], ...]
    strongest_prominence_db: float | None
    detected: bool
    #: Harmonics that are not multiples of 300 Hz, i.e. that this base
    #: explains and the other mains base does not.
    distinct_harmonics_hz: tuple[float, ...] = ()
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_hz": self.base_hz,
            "harmonics": [list(h) for h in self.harmonics],
            "distinct_harmonics_hz": list(self.distinct_harmonics_hz),
            "strongest_prominence_db": self.strongest_prominence_db,
            "detected": self.detected,
            "note": self.note,
        }


#: Reference of :attr:`NoiseResult.psd_db`.
PSD_REFERENCE = diag(
    "dB re (full-scale sine RMS)^2 per Hz: the power spectral density is scaled so that "
    "10*log10 of its integral is the reported AES17 RMS level in dBFS"
)


@dataclass(frozen=True)
class NoiseResult:
    """Background-noise levels of a verified quiet segment.

    Every level is ``None`` when it cannot be measured (no quiet segment,
    digital silence, or a level below the file's quantisation floor); the
    reason is then in :attr:`notes`. Levels are never fabricated for a segment
    that holds no acoustic noise.
    """

    #: Where the quiet segment came from ("pre-sweep", "tail") or None.
    segment_source: str | None
    segment_start_s: float | None
    segment_duration_s: float | None
    #: RMS level in dBFS (AES17 convention: a full-scale sine reads 0 dBFS).
    rms_dbfs: float | None
    peak_dbfs: float | None
    #: (center_hz, level_dbfs) per octave band, from a single filter pass with
    #: the start transient discarded; the level is ``None`` when the band
    #: cannot be measured (segment too short, or below the level floor).
    band_levels_dbfs: tuple[tuple[float, float | None], ...]
    psd_frequencies_hz: FloatArray | None = field(repr=False)
    #: Power spectral density in dB, see :data:`PSD_REFERENCE`.
    psd_db: FloatArray | None = field(repr=False)
    hum: tuple[HumCandidate, ...] = ()
    calibration: str = diag("uncalibrated: levels are dBFS, not dB SPL")
    psd_reference: str = PSD_REFERENCE
    notes: tuple[str, ...] = ()

    def to_dict(self, include_curves: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "segment_source": self.segment_source,
            "segment_start_s": self.segment_start_s,
            "segment_duration_s": self.segment_duration_s,
            "rms_dbfs": self.rms_dbfs,
            "peak_dbfs": self.peak_dbfs,
            "band_levels_dbfs": [list(b) for b in self.band_levels_dbfs],
            "hum": [h.to_dict() for h in self.hum],
            "calibration": self.calibration,
            "psd_reference": self.psd_reference,
            "notes": list(self.notes),
        }
        if include_curves:
            data["psd_frequencies_hz"] = _array_to_list(self.psd_frequencies_hz, 3)
            data["psd_db"] = _array_to_list(self.psd_db, 2)
        return data


@dataclass(frozen=True)
class Reflection:
    delay_ms: float
    relative_db: float

    def to_dict(self) -> dict[str, Any]:
        return {"delay_ms": self.delay_ms, "relative_db": self.relative_db}


@dataclass(frozen=True)
class ReflectionsResult:
    direct_sound_time_s: float
    direct_sound_confidence: str
    #: Requested search window after the direct sound (ms).
    window_ms: tuple[float, float]
    threshold_db: float
    reflections: tuple[Reflection, ...]
    notes: tuple[str, ...] = ()
    #: Window that was actually analysed (ms): the requested one limited by
    #: the impulse response that was available after the direct sound.
    analysed_window_ms: tuple[float, float] | None = None
    #: True when the impulse response ended before ``window_ms[1]``, so later
    #: reflections could not be seen.
    window_truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "direct_sound_time_s": self.direct_sound_time_s,
            "direct_sound_confidence": self.direct_sound_confidence,
            "window_ms": list(self.window_ms),
            "analysed_window_ms": (
                list(self.analysed_window_ms) if self.analysed_window_ms is not None else None
            ),
            "window_truncated": self.window_truncated,
            "threshold_db": self.threshold_db,
            "reflections": [r.to_dict() for r in self.reflections],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ResonanceCandidate:
    """A response peak that may be a resonance, with its decay evidence.

    All three decay figures are the same measurement (time for the
    time-reversed 1/3-octave band envelope to fall 20 dB), so they may be
    compared directly.
    """

    frequency_hz: float
    level_above_baseline_db: float
    #: Time for the narrow-band envelope to fall 20 dB (s), or None.
    narrowband_decay_20db_s: float | None
    #: Same measure for the analysis filter alone (its ringing), for comparison.
    filter_ringing_20db_s: float | None
    #: True only when the measured decay is clearly longer than *both* the
    #: filter ringing and the surroundings.
    decay_distinguishable: bool
    #: Same measure for the neighbouring 1/3-octave bands (median), i.e. how
    #: long the surroundings of this frequency ring. ``None`` when too few
    #: neighbouring bands could be measured.
    surroundings_decay_20db_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frequency_hz": self.frequency_hz,
            "level_above_baseline_db": self.level_above_baseline_db,
            "narrowband_decay_20db_s": self.narrowband_decay_20db_s,
            "filter_ringing_20db_s": self.filter_ringing_20db_s,
            "surroundings_decay_20db_s": self.surroundings_decay_20db_s,
            "decay_distinguishable": self.decay_distinguishable,
        }


@dataclass(frozen=True)
class ResonanceResult:
    max_frequency_hz: float
    candidates: tuple[ResonanceCandidate, ...]
    notes: tuple[str, ...] = ()
    #: Frequency range that was actually searched (Hz): ``max_frequency_hz``
    #: narrowed to the excited and resolvable part.
    searched_range_hz: tuple[float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_frequency_hz": self.max_frequency_hz,
            "searched_range_hz": (
                list(self.searched_range_hz) if self.searched_range_hz is not None else None
            ),
            "candidates": [c.to_dict() for c in self.candidates],
            "notes": list(self.notes),
        }


#: Provenance of the speed of sound used by the placement geometry. Emitted in
#: the JSON so that an exported result says which relation produced its metres.
SPEED_OF_SOUND_REFERENCE = diag(
    "c = 331.3 * sqrt(1 + T/273.15) m/s (adiabatic ideal-gas relation for dry air; "
    "343.2 m/s at 20 C, numerically equal to the ISO 9613-1 form c = 343.2 * sqrt(T/293.15))"
)

#: What RoomScope refuses to infer, and why, emitted verbatim in the JSON so
#: that an exported result carries its own justification rather than relying on
#: the reader having opened docs/MEASUREMENT_METHODOLOGY.md.
PLACEMENT_COORDINATES_WITHHELD = diag(
    "No coordinate, room length, room width or wall distance is reported. One "
    "omnidirectional microphone at one position measures path lengths, not directions, "
    "and the deconvolved time origin contains the interface round-trip latency, so there "
    "is no absolute time of flight: the four independent arrival equations constrain six "
    "unknowns, a deficit of three without a tape-measured loudspeaker-to-microphone "
    "distance and two with it. The remaining freedom is the direction of the "
    "loudspeaker-to-microphone vector, and every direction reproduces the measured "
    "arrival times exactly. Only quantities invariant over that family are reported: the "
    "product of the two perpendicular distances to a plane, and the vertical axis once "
    "one perpendicular distance is supplied by the user."
)

#: Why :attr:`PlacementLength.input_uncertainty_m` is not the total uncertainty.
PLACEMENT_UNCERTAINTY_EXCLUDES = diag(
    "propagated from the stated tape-measure, temperature and peak-location uncertainties "
    "only; it excludes model error (that the reflector is flat, rigid and large compared "
    "with the wavelength, that the arrival is a first-order specular reflection, and that "
    "the user measured to the plane that actually reflected), which is usually larger"
)


@dataclass(frozen=True)
class PlacementLength:
    """A distance derived from the reflection geometry, or a refusal to give one.

    ``metres`` is ``None`` for every :class:`Validity` other than
    :attr:`Validity.VALID`; ``reason`` then says which input was missing or
    which gate refused, in the user's terms.
    """

    metres: float | None
    validity: Validity
    reason: str | None = None
    #: 1-sigma propagated from the *stated input* uncertainties only. Read it
    #: with :data:`PLACEMENT_UNCERTAINTY_EXCLUDES`, which ``to_dict`` emits
    #: alongside it: it is not the total uncertainty of the metres.
    input_uncertainty_m: float | None = None
    #: Every competing value when more than one reflection could be the plane
    #: the user measured from. RoomScope does not pick one.
    alternatives_m: tuple[float, ...] = ()
    #: The CLI flag that would supply the missing input, when one is missing.
    missing_input: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "metres": self.metres,
            "validity": str(self.validity),
            "reason": self.reason,
            "input_uncertainty_m": self.input_uncertainty_m,
            "uncertainty_excludes": (
                PLACEMENT_UNCERTAINTY_EXCLUDES if self.input_uncertainty_m is not None else None
            ),
            "alternatives_m": list(self.alternatives_m),
            "missing_input": self.missing_input,
        }


@dataclass(frozen=True)
class BoundaryCandidate:
    """One detected early reflection re-expressed as geometry.

    ``delay_ms`` and ``relative_db`` are copied from the :class:`Reflection`
    this was built from. Everything below ``excess_path_m`` needs the
    loudspeaker-to-microphone distance and is ``None`` without it.

    The geometric fields describe *a flat first-order reflector*. A candidate
    that is a merged pair of arrivals, a second-order path or a statistical
    peak of the dense early tail is none of those things, and then the numbers
    are the product of nothing: read :attr:`interpretable_as_plane` first.
    """

    delay_ms: float
    relative_db: float
    #: ``c * delay``: how much further this arrival travelled than the direct
    #: sound. Needs only the temperature, so it is always present.
    excess_path_m: float
    #: ``d + excess``: the image-source path length (m).
    mirror_path_m: float | None = None
    #: ``s*r``, the product of the perpendicular distances of loudspeaker and
    #: microphone from the reflecting plane (m^2), exact for a flat first-order
    #: reflector: ``s*r = c*delta*(2d + c*delta)/4``.
    product_m2: float | None = None
    #: ``sqrt(s*r)``: the geometric mean of those two distances. The nearer of
    #: the two is at most this, the farther at least this.
    geometric_mean_m: float | None = None
    #: Exact two-sided bracket on the *arithmetic* mean ``(s+r)/2``, from
    #: ``0 <= (s-r)^2 <= d^2``. The lower end equals
    #: :attr:`geometric_mean_m` (AM >= GM). A bound, not an interval estimate.
    mean_distance_bracket_m: tuple[float, float] | None = None
    #: ``20*log10(d/L)``: what a lossless point source mirrored in a rigid
    #: plane would read at this path length (dB re the direct sound).
    specular_ceiling_db: float | None = None
    #: ``"lower_plane"`` or ``"upper_plane"``; ``None`` when this candidate was
    #: not attributed to either. No wall is ever named.
    surface: str | None = None
    #: ``False`` when a gate showed this arrival is not treated as a reflection
    #: from a flat plane, so the geometric fields above must not be quoted.
    #: ``None`` when it was never tested (the tier did not allow it) -- which
    #: is not the same as passing.
    interpretable_as_plane: bool | None = None
    #: Why this candidate was not treated as a plane reflection, in its own
    #: numbers. Never says a surface is absent or fine.
    excluded_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "delay_ms": self.delay_ms,
            "relative_db": self.relative_db,
            "excess_path_m": self.excess_path_m,
            "mirror_path_m": self.mirror_path_m,
            "product_m2": self.product_m2,
            "geometric_mean_m": self.geometric_mean_m,
            "mean_distance_bracket_m": (
                list(self.mean_distance_bracket_m)
                if self.mean_distance_bracket_m is not None
                else None
            ),
            "specular_ceiling_db": self.specular_ceiling_db,
            "surface": self.surface,
            "interpretable_as_plane": self.interpretable_as_plane,
            "excluded_reason": self.excluded_reason,
        }


@dataclass(frozen=True)
class PlacementResult:
    """Vertical geometry derived from the early reflections and a tape measure.

    ``tier`` says how much the supplied inputs allowed:

    * 0 -- temperature only: every candidate carries its excess path in metres.
    * 1 -- and the loudspeaker-to-microphone distance: the per-candidate
      product of perpendicular distances and its bounds.
    * 2 -- and the microphone height: the vertical axis is solved.

    Nothing horizontal is ever reported; see
    :data:`PLACEMENT_COORDINATES_WITHHELD`.
    """

    tier: int
    candidates: tuple[BoundaryCandidate, ...]
    #: Loudspeaker height above the same plane the user measured from.
    source_height_m: PlacementLength
    #: Height of the upper plane above that same plane.
    ceiling_height_m: PlacementLength
    #: Horizontal loudspeaker-to-microphone separation.
    horizontal_separation_m: PlacementLength
    speed_of_sound_m_s: float
    temperature_c: float
    #: True when no temperature was supplied and 20 C was assumed.
    temperature_assumed: bool
    distance_m: float | None = None
    mic_height_m: float | None = None
    #: Copied from :class:`ReflectionsResult` because the geometry inherits the
    #: search window: a plane outside it cannot be found, which is not the same
    #: as it not being there.
    analysed_window_ms: tuple[float, float] | None = None
    window_truncated: bool = False
    notes: tuple[str, ...] = ()
    speed_of_sound_reference: str = SPEED_OF_SOUND_REFERENCE
    coordinates_withheld: str = PLACEMENT_COORDINATES_WITHHELD

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "distance_m": self.distance_m,
            "mic_height_m": self.mic_height_m,
            "temperature_c": self.temperature_c,
            "temperature_assumed": self.temperature_assumed,
            "speed_of_sound_m_s": self.speed_of_sound_m_s,
            "speed_of_sound_reference": self.speed_of_sound_reference,
            "source_height_m": self.source_height_m.to_dict(),
            "ceiling_height_m": self.ceiling_height_m.to_dict(),
            "horizontal_separation_m": self.horizontal_separation_m.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
            "analysed_window_ms": (
                list(self.analysed_window_ms) if self.analysed_window_ms is not None else None
            ),
            "window_truncated": self.window_truncated,
            "coordinates_withheld": self.coordinates_withheld,
            "notes": list(self.notes),
        }


#: Welch PSD of the impulse response (AES17 density), same scaling as noise.
SPECTRUM_METHOD = diag(
    "Welch (1967) periodogram, Hann window, density scaling; "
    "10*log10(2*psd) so the integral matches AES17 RMS dBFS"
)
SPECTRUM_SOURCE = "impulse_response"


@dataclass(frozen=True)
class SpectrumResult:
    """Power spectrum of the deconvolved impulse response.

    Distinct from :class:`FrequencyResponseResult` (gated FFT magnitude of the
    IR) and from :class:`NoiseResult` (Welch PSD of a quiet recording segment).
    This is the energy spectrum of RoomScope's own IR, the product of the
    sweep path.
    """

    frequencies_hz: FloatArray = field(repr=False)
    level_db: FloatArray = field(repr=False)
    peak_hz: float | None
    peak_db: float | None
    nperseg: int
    method: str = SPECTRUM_METHOD
    source: str = SPECTRUM_SOURCE
    reference: str = PSD_REFERENCE

    def to_dict(self, include_curves: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "peak_hz": self.peak_hz,
            "peak_db": self.peak_db,
            "nperseg": self.nperseg,
            "method": self.method,
            "source": self.source,
            "reference": self.reference,
            "points": int(self.frequencies_hz.shape[0]),
        }
        if include_curves:
            data["frequencies_hz"] = _array_to_list(self.frequencies_hz, 3)
            data["level_db"] = _array_to_list(self.level_db, 2)
        return data


@dataclass(frozen=True)
class RoomScan:
    """An imported lidar / photogrammetry scan used as a room-model overlay.

    Coordinates are the file's, treated as metres. RoomScope does not align
    them to the microphone and does not claim a lidar was attached.
    """

    format: str
    source_name: str
    points_m: FloatArray = field(repr=False)
    faces: tuple[tuple[int, int, int], ...] = ()
    bounds_min_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounds_max_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    point_count: int = 0
    format_reference: str = ""
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "source_name": self.source_name,
            "points_m": [list(map(float, row)) for row in self.points_m],
            "faces": [list(face) for face in self.faces],
            "bounds_min_m": list(self.bounds_min_m),
            "bounds_max_m": list(self.bounds_max_m),
            "point_count": self.point_count,
            "format_reference": self.format_reference,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class AnalysisResult:
    """Complete output of :func:`roomscope.core.pipeline.analyze`."""

    created_at: str
    sample_rate: int
    sweep_settings: dict[str, Any]
    analysis_settings: dict[str, Any]
    impulse_response: ImpulseResponseResult
    decay: DecayResult
    frequency_response: FrequencyResponseResult
    noise: NoiseResult
    reflections: ReflectionsResult
    resonances: ResonanceResult
    warnings: tuple[str, ...] = ()
    #: Flat-top test of the analysed channel (``None`` when not run).
    clipping: ClippingCheck | None = None
    #: Vertical geometry from the early reflections (``None`` when the
    #: placement inputs were not supplied and no tier could be produced).
    placement: PlacementResult | None = None
    #: Welch spectrum of the impulse response (always computed on a new analysis).
    spectrum: SpectrumResult | None = None
    #: Optional imported PLY/OBJ scan; overlay only, never a hardware PASS.
    room_scan: RoomScan | None = None
    schema_version: int = RESULT_SCHEMA_VERSION
    roomscope_version: str = ""

    @property
    def excitation_band(self) -> ExcitationBand | None:
        """Shortcut to :attr:`ImpulseResponseResult.excitation_band`."""
        return self.impulse_response.excitation_band

    def to_dict(self, include_curves: bool = True) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "roomscope_version": self.roomscope_version,
            "created_at": self.created_at,
            "sample_rate": self.sample_rate,
            "sweep_settings": self.sweep_settings,
            "analysis_settings": self.analysis_settings,
            "impulse_response": self.impulse_response.to_dict(include_curves=False),
            "decay": self.decay.to_dict(include_curves),
            "frequency_response": self.frequency_response.to_dict(include_curves),
            "noise": self.noise.to_dict(include_curves),
            "reflections": self.reflections.to_dict(),
            "resonances": self.resonances.to_dict(),
            "clipping": self.clipping.to_dict() if self.clipping is not None else None,
            "placement": self.placement.to_dict() if self.placement is not None else None,
            "spectrum": self.spectrum.to_dict(include_curves)
            if self.spectrum is not None
            else None,
            "room_scan": self.room_scan.to_dict() if self.room_scan is not None else None,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisResult:
        from roomscope.models.result_load import analysis_result_from_dict

        return analysis_result_from_dict(data)
