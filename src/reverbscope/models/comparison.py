"""Comparison of two analysis results.

A comparison is derived from two :class:`AnalysisResult` objects and never
changes either. Findings are not stored here; they are re-derived on load.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

import numpy as np

from reverbscope.errors import SessionError
from reverbscope.models.loadutil import (
    build_record,
    drop_unknown,
    read_schema_version,
    record_payload,
)
from reverbscope.models.result import FloatArray, Validity
from reverbscope.version import __version__

COMPARISON_SCHEMA_VERSION = 1

#: ISO 3382-1 just-noticeable difference for reverberation time, about 5 %
#: (clause not verified against the standard text; quoted, never used to call
#: a change "significant" from a single pair of positions).
T_JND_PERCENT = 5.0


def _array_to_list(values: FloatArray | None, decimals: int = 4) -> list[float] | None:
    if values is None:
        return None
    return [float(v) for v in np.round(values, decimals)]


@dataclass(frozen=True)
class CompareSettings:
    """Thresholds for :func:`reverbscope.core.compare.compare`.

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
            raise SessionError(f"unknown comparison validity {validity!r}") from exc
        return build_record(cls, payload, kind="metric delta")


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
        return build_record(cls, payload, kind="reflection match")


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
                frequencies_hz=np.asarray(freq, dtype=np.float64),
                difference_db=np.asarray(diff, dtype=np.float64),
                band_mad_db=tuple((str(a), float(b)) for a, b in mad),
                smoothing_fraction=int(payload.get("smoothing_fraction", 0)),
                reference=str(payload.get("reference", "")),
            )
        except (TypeError, ValueError) as exc:
            raise SessionError(f"invalid frequency-response delta in file: {exc}") from exc


@dataclass(frozen=True)
class ComparisonResult:
    """Output of :func:`reverbscope.core.compare.compare`."""

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
    reverbscope_version: str = field(default_factory=lambda: __version__)
    schema_version: int = COMPARISON_SCHEMA_VERSION
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "reverbscope_version": self.reverbscope_version,
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
            raise SessionError("comparison data must be a JSON object")
        version = read_schema_version(data, COMPARISON_SCHEMA_VERSION, "comparison")
        payload = drop_unknown(data, {f.name for f in fields(cls)}, kind="comparison")
        try:
            return cls._from_payload(payload, version)
        except (TypeError, ValueError, IndexError, KeyError) as exc:
            raise SessionError(f"invalid comparison file: {exc}") from exc

    @classmethod
    def _from_payload(cls, payload: dict[str, Any], version: int) -> ComparisonResult:
        common = payload.get("common_band")
        common_band = None if common is None else (float(common[0]), float(common[1]))
        notes = payload.get("notes") or ()
        return cls(
            comparable=bool(payload.get("comparable", False)),
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
            reverbscope_version=str(payload.get("reverbscope_version", "")),
            schema_version=version,
            settings=dict(payload.get("settings") or {}),
        )
