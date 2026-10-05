"""Comparison of two analysis results.

A comparison is derived from two :class:`AnalysisResult` objects and never
changes either. Findings are not stored here; they are re-derived on load.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any

import numpy as np

from roomscope.errors import SessionError
from roomscope.i18n import _
from roomscope.models.loadutil import (
    build_record,
    drop_unknown,
    read_flag,
    read_schema_version,
    record_name,
    record_payload,
)
from roomscope.models.result import FloatArray, Validity
from roomscope.version import __version__

COMPARISON_SCHEMA_VERSION = 1

#: ISO 3382-1 just-noticeable difference for reverberation time, about 5 %
#: (clause not verified against the standard text; quoted, never used to call
#: a change "significant" from a single pair of positions).
T_JND_PERCENT = 5.0

#: Units on a ratio scale, where a change in percent of a positive baseline
#: means something. In percent of a level in dB (or of D50, itself a
#: percentage) it does not, and it flips sign with a negative baseline: C50
#: going from -2 to -1 dB, or a loopback path delay from -0.50 to -0.25 ms,
#: read -50 %.
PERCENT_UNITS = frozenset({"s", "ms", "m"})


def percent_applies(unit: str, baseline: float | None) -> bool:
    """Whether a change of a ``unit`` value can be given in percent of ``baseline``."""
    return unit in PERCENT_UNITS and baseline is not None and baseline > 0.0


#: How each note that refuses a pair begins (see ``_common_band`` and the
#: narrow-band check in :func:`roomscope.core.compare.compare`). A new
#: comparison lists its refusal first; one saved by 0.5.0b1 or earlier lists
#: it after the sweep and ISO notes, so a reader looks for these.
REFUSAL_NOTE_PREFIXES: tuple[str, ...] = (
    "one or both results have no excitation band",
    "the excitation bands do not overlap",
    "common excitation band ",
)


def _array_to_list(values: FloatArray | None, decimals: int = 4) -> list[float] | None:
    if values is None:
        return None
    return [float(v) for v in np.round(values, decimals)]


def _curve(values: Any) -> FloatArray:
    """A curve read from a file. A single number would load as a 0-d array
    that ``to_dict`` cannot turn back into a list."""
    curve = np.asarray(values, dtype=np.float64)
    if curve.ndim != 1:
        raise TypeError(_("expected a list of numbers"))
    return curve


@dataclass(frozen=True)
class CompareSettings:
    """Thresholds for :func:`roomscope.core.compare.compare`.

    Defaults are the constants in ARCHITECTURE_V1.md §5.3.2 and
    MEASUREMENT_METHODOLOGY.md §11.
    """

    min_common_band_octaves: float = 1.0
    reflection_match_ms: float = 0.5
    resonance_match_octaves: float = 1.0 / 6.0
    same_input_gain: bool = False
    log_grid_points_per_octave: int = 24

    def __post_init__(self) -> None:
        if self.min_common_band_octaves <= 0.0:
            raise ValueError("min_common_band_octaves must be > 0")
        if self.reflection_match_ms <= 0.0:
            raise ValueError("reflection_match_ms must be > 0")
        if self.resonance_match_octaves <= 0.0:
            raise ValueError("resonance_match_octaves must be > 0")
        if self.log_grid_points_per_octave < 1:
            raise ValueError("log_grid_points_per_octave must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_common_band_octaves": self.min_common_band_octaves,
            "reflection_match_ms": self.reflection_match_ms,
            "resonance_match_octaves": self.resonance_match_octaves,
            "same_input_gain": self.same_input_gain,
            "log_grid_points_per_octave": self.log_grid_points_per_octave,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompareSettings:
        payload = record_payload(data, {f.name for f in fields(cls)}, kind="compare settings")
        return build_record(cls, payload, kind="compare settings")


@dataclass(frozen=True)
class MetricDelta:
    """One compared scalar, with a validity that is independent of either side."""

    name: str
    baseline: float | None
    candidate: float | None
    validity: Validity
    reason: str | None = None
    #: Candidate minus baseline, in seconds, when the metric is a time.
    delta_s: float | None = None
    delta_percent: float | None = None
    #: Candidate minus baseline in the metric's own unit (always filled when
    #: both sides have a number, including for times).
    delta: float | None = None
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "baseline": self.baseline,
            "candidate": self.candidate,
            "delta_s": self.delta_s,
            "delta_percent": self.delta_percent,
            "delta": self.delta,
            "unit": self.unit,
            "validity": str(self.validity),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricDelta:
        payload = record_payload(data, {f.name for f in fields(cls)}, kind="metric delta")
        validity = payload.get("validity", Validity.NOT_COMPARABLE)
        try:
            payload["validity"] = Validity(str(validity))
        except ValueError as exc:
            raise SessionError(_("unknown validity {value}").format(value=repr(validity))) from exc
        record = build_record(cls, payload, kind="metric delta")
        if record.delta_percent is not None and not percent_applies(record.unit, record.baseline):
            # Files written by 0.5.0b1 and earlier gave a percent for every
            # unit, which ``show`` would print ("C50 (dB) ... +3.4 %").
            record = replace(record, delta_percent=None)
        return record


@dataclass(frozen=True)
class ReflectionMatch:
    """Two early reflections matched by delay, or a one-sided appearance."""

    status: str
    baseline_delay_ms: float | None = None
    candidate_delay_ms: float | None = None
    baseline_relative_db: float | None = None
    candidate_relative_db: float | None = None
    delay_delta_ms: float | None = None
    level_delta_db: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "baseline_delay_ms": self.baseline_delay_ms,
            "candidate_delay_ms": self.candidate_delay_ms,
            "baseline_relative_db": self.baseline_relative_db,
            "candidate_relative_db": self.candidate_relative_db,
            "delay_delta_ms": self.delay_delta_ms,
            "level_delta_db": self.level_delta_db,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReflectionMatch:
        payload = record_payload(data, {f.name for f in fields(cls)}, kind="reflection match")
        record = build_record(cls, payload, kind="reflection match")
        # The report prints the delay and level of the side(s) the status
        # names; any other status is shown with the baseline's.
        sides = {"matched": ("baseline", "candidate"), "appeared": ("candidate",)}
        for side in sides.get(record.status, ("baseline",)):
            for name in (f"{side}_delay_ms", f"{side}_relative_db"):
                if getattr(record, name) is None:
                    raise SessionError(
                        _("invalid {kind} in file: {error}").format(
                            kind=record_name("reflection match"),
                            error=_("{field} must not be null").format(field=name),
                        )
                    )
        return record


@dataclass(frozen=True)
class ResonanceMatch:
    """Two resonance candidates matched within a fraction of an octave."""

    status: str
    baseline_hz: float | None = None
    candidate_hz: float | None = None
    baseline_decay_distinguishable: bool | None = None
    candidate_decay_distinguishable: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "baseline_hz": self.baseline_hz,
            "candidate_hz": self.candidate_hz,
            "baseline_decay_distinguishable": self.baseline_decay_distinguishable,
            "candidate_decay_distinguishable": self.candidate_decay_distinguishable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResonanceMatch:
        payload = record_payload(data, {f.name for f in fields(cls)}, kind="resonance match")
        return build_record(cls, payload, kind="resonance match")


@dataclass(frozen=True)
class FrequencyResponseDelta:
    """Difference of two smoothed magnitude curves on a shared log grid."""

    frequencies_hz: FloatArray = field(repr=False)
    difference_db: FloatArray = field(repr=False)
    band_mad_db: tuple[tuple[str, float], ...] = ()
    smoothing_fraction: int = 0
    reference: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "frequencies_hz": _array_to_list(self.frequencies_hz, 3),
            "difference_db": _array_to_list(self.difference_db, 2),
            "band_mad_db": [list(item) for item in self.band_mad_db],
            "smoothing_fraction": self.smoothing_fraction,
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FrequencyResponseDelta | None:
        if data is None:
            return None
        payload = record_payload(
            data, {f.name for f in fields(cls)}, kind="frequency-response delta"
        )
        freq = payload.get("frequencies_hz") or []
        diff = payload.get("difference_db") or []
        mad = payload.get("band_mad_db") or ()
        try:
            return cls(
                frequencies_hz=_curve(freq),
                difference_db=_curve(diff),
                band_mad_db=tuple((str(a), float(b)) for a, b in mad),
                smoothing_fraction=int(payload.get("smoothing_fraction", 0)),
                reference=str(payload.get("reference", "")),
            )
        except (TypeError, ValueError, OverflowError) as exc:  # Overflow: int(Infinity)
            raise SessionError(
                _("invalid {kind} in file: {error}").format(
                    kind=record_name("frequency-response delta"), error=exc
                )
            ) from exc


@dataclass(frozen=True)
class ComparisonResult:
    """Output of :func:`roomscope.core.compare.compare`."""

    comparable: bool
    common_band: tuple[float, float] | None
    notes: tuple[str, ...] = ()
    decay: tuple[MetricDelta, ...] = ()
    frequency_response: FrequencyResponseDelta | None = None
    reflections: tuple[ReflectionMatch, ...] = ()
    noise: tuple[MetricDelta, ...] = ()
    resonances: tuple[ResonanceMatch, ...] = ()
    placement: tuple[MetricDelta, ...] = ()
    loopback: tuple[MetricDelta, ...] = ()
    baseline_created_at: str = ""
    candidate_created_at: str = ""
    baseline_session: str | None = None
    candidate_session: str | None = None
    roomscope_version: str = field(default_factory=lambda: __version__)
    schema_version: int = COMPARISON_SCHEMA_VERSION
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "roomscope_version": self.roomscope_version,
            "comparable": self.comparable,
            "common_band": list(self.common_band) if self.common_band is not None else None,
            "notes": list(self.notes),
            "decay": [item.to_dict() for item in self.decay],
            "frequency_response": (
                self.frequency_response.to_dict() if self.frequency_response is not None else None
            ),
            "reflections": [item.to_dict() for item in self.reflections],
            "noise": [item.to_dict() for item in self.noise],
            "resonances": [item.to_dict() for item in self.resonances],
            "placement": [item.to_dict() for item in self.placement],
            "loopback": [item.to_dict() for item in self.loopback],
            "baseline_created_at": self.baseline_created_at,
            "candidate_created_at": self.candidate_created_at,
            "baseline_session": self.baseline_session,
            "candidate_session": self.candidate_session,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComparisonResult:
        if not isinstance(data, dict):
            raise SessionError(
                _("{kind} must be a JSON object").format(kind=record_name("comparison"))
            )
        version = read_schema_version(data, COMPARISON_SCHEMA_VERSION, "comparison")
        payload = drop_unknown(data, {f.name for f in fields(cls)}, kind="comparison")
        try:
            return cls._from_payload(payload, version)
        except (TypeError, ValueError, IndexError, KeyError, OverflowError) as exc:
            # OverflowError: float() of an integer with hundreds of digits.
            raise SessionError(
                _("invalid {kind} in file: {error}").format(
                    kind=record_name("comparison"), error=exc
                )
            ) from exc

    @classmethod
    def _from_payload(cls, payload: dict[str, Any], version: int) -> ComparisonResult:
        common = payload.get("common_band")
        common_band = None if common is None else (float(common[0]), float(common[1]))
        notes = payload.get("notes") or ()
        return cls(
            comparable=read_flag(payload.get("comparable", False), "comparable"),
            common_band=common_band,
            notes=tuple(str(n) for n in notes),
            decay=tuple(MetricDelta.from_dict(item) for item in payload.get("decay") or ()),
            frequency_response=FrequencyResponseDelta.from_dict(payload.get("frequency_response")),
            reflections=tuple(
                ReflectionMatch.from_dict(item) for item in payload.get("reflections") or ()
            ),
            noise=tuple(MetricDelta.from_dict(item) for item in payload.get("noise") or ()),
            resonances=tuple(
                ResonanceMatch.from_dict(item) for item in payload.get("resonances") or ()
            ),
            placement=tuple(MetricDelta.from_dict(item) for item in payload.get("placement") or ()),
            loopback=tuple(MetricDelta.from_dict(item) for item in payload.get("loopback") or ()),
            baseline_created_at=str(payload.get("baseline_created_at", "")),
            candidate_created_at=str(payload.get("candidate_created_at", "")),
            baseline_session=payload.get("baseline_session"),
            candidate_session=payload.get("candidate_session"),
            roomscope_version=str(payload.get("roomscope_version", "")),
            schema_version=version,
            settings=dict(payload.get("settings") or {}),
        )
