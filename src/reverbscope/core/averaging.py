"""Spatial average of reverberation-time values (SHOULD, ARCHITECTURE_V1 §5.3.4).

Averages EDT, T20 and T30 per band over the VALID metrics only. Decay curves
are never averaged. The output names the ISO 3382-2 accuracy class that the
numbers of source positions, microphone positions and source–microphone
combinations reach.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from reverbscope.errors import ConfigurationError
from reverbscope.i18n import N_, diag
from reverbscope.models.result import AnalysisResult, DecayMetric, Validity

# ISO 3382-2:2008, 4.3.1, Table 1 "Minimum numbers of positions and
# measurements" (source–microphone combinations; source positions; microphone
# positions). Read from the standard's own text in the publisher's preview
# pages on 2026-09-24 (MEASUREMENT_METHODOLOGY.md §3a, reference [10]); v0.4.0
# carried an unsourced transcription with 3 / 6 microphone positions for
# engineering / precision (#15). Footnote a (an engineering result used as a
# correction term needs one source and three microphone positions) and the
# rotating-boom footnote are not implemented. The class is a label, not a claim
# of compliance: the standard also sets position spacing, distances from
# surfaces and the other clause 4 conditions, which ReverbScope does not check.
#: The accuracy class names as shown to users; results store the English
#: ids ("survey", ..., "below_survey") and front ends translate them.
ACCURACY_CLASS_WORDS = (N_("survey"), N_("engineering"), N_("precision"), N_("below survey"))
ISO_3382_2_TABLE1 = {
    "survey": {"n_source": 1, "n_microphone": 2, "n_combinations": 2},
    "engineering": {"n_source": 2, "n_microphone": 2, "n_combinations": 6},
    "precision": {"n_source": 2, "n_microphone": 3, "n_combinations": 12},
}
ISO_3382_2_TABLE1_SOURCE = diag(
    "ISO 3382-2:2008, 4.3.1, Table 1, read from the standard's preview pages "
    "(cdn.standards.iteh.ai sample of ISO 3382-2:2008) on 2026-09-24; footnotes not implemented"
)


@dataclass(frozen=True)
class AveragedMetric:
    """Arithmetic mean of one VALID decay metric across sessions."""

    name: str
    seconds: float | None
    count: int
    spread_s: float | None
    contributing: tuple[str, ...]
    validity: Validity
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "seconds": self.seconds,
            "count": self.count,
            "spread_s": self.spread_s,
            "contributing": list(self.contributing),
            "validity": str(self.validity),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AveragedBand:
    band_label: str
    edt: AveragedMetric
    t20: AveragedMetric
    t30: AveragedMetric
    rt60_estimate_s: float | None
    rt60_basis: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "band_label": self.band_label,
            "edt": self.edt.to_dict(),
            "t20": self.t20.to_dict(),
            "t30": self.t30.to_dict(),
            "rt60_estimate_s": self.rt60_estimate_s,
            "rt60_basis": self.rt60_basis,
        }


@dataclass(frozen=True)
class AveragedDecay:
    """Spatial average of T values. No decay curve is stored."""

    bands: tuple[AveragedBand, ...]
    n_sessions: int
    n_source_positions: int
    n_microphone_positions: int
    iso_3382_2_class: str
    notes: tuple[str, ...] = ()
    #: Distinct source–microphone combinations measured (Table 1's first row).
    n_combinations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_sessions": self.n_sessions,
            "n_source_positions": self.n_source_positions,
            "n_microphone_positions": self.n_microphone_positions,
            "n_source_microphone_combinations": self.n_combinations,
            "iso_3382_2_class": self.iso_3382_2_class,
            "notes": list(self.notes),
            "bands": [band.to_dict() for band in self.bands],
            "iso_3382_2_table1": ISO_3382_2_TABLE1,
            "confirmation_status": ISO_3382_2_TABLE1_SOURCE,
        }


def iso_3382_2_class(n_source: int, n_microphone: int, n_combinations: int | None = None) -> str:
    """Name the ISO 3382-2 Table 1 class reached by the counts.

    Every row of the table must be met: source positions, microphone
    positions and source–microphone combinations. ``n_combinations``
    defaults to ``n_source * n_microphone`` (every source measured at every
    microphone position) and can never exceed that product.
    """
    grid = n_source * n_microphone
    combinations = grid if n_combinations is None else min(int(n_combinations), grid)
    for name in ("precision", "engineering", "survey"):
        row = ISO_3382_2_TABLE1[name]
        if (
            n_source >= row["n_source"]
            and n_microphone >= row["n_microphone"]
            and combinations >= row["n_combinations"]
        ):
            return name
    return "below_survey"


def average_decay(
    results: Sequence[AnalysisResult],
    *,
    n_source_positions: int | None = None,
    n_microphone_positions: int | None = None,
    n_combinations: int | None = None,
    session_labels: Sequence[str] | None = None,
) -> AveragedDecay:
    """Arithmetic mean of VALID EDT / T20 / T30 per band.

    ``n_source_positions`` defaults to 1 (ReverbScope measures one source).
    ``n_microphone_positions`` defaults to the number of results, i.e. it
    assumes every result was taken at a different microphone position; a
    caller that knows the positions (``reverbscope project average``) passes
    the number of distinct ones. ``n_combinations`` (distinct
    source–microphone combinations) defaults to the smaller of the number of
    results and ``n_source_positions * n_microphone_positions``: repeated
    takes of one combination do not count twice.
    """
    if not results:
        raise ConfigurationError("average_decay needs at least one AnalysisResult")
    labels = (
        list(session_labels)
        if session_labels is not None and len(session_labels) == len(results)
        else [f"session-{index}" for index in range(len(results))]
    )
    n_source = 1 if n_source_positions is None else int(n_source_positions)
    n_mic = len(results) if n_microphone_positions is None else int(n_microphone_positions)
    if n_source < 1 or n_mic < 1:
        raise ConfigurationError("source and microphone position counts must be >= 1")
    grid = n_source * n_mic
    combos = min(len(results), grid) if n_combinations is None else int(n_combinations)
    if combos < 1 or combos > min(grid, len(results)):
        raise ConfigurationError(
            "source-microphone combinations must be between 1 and the smaller of "
            "sources x microphone positions and the number of results"
        )
    klass = iso_3382_2_class(n_source, n_mic, combos)

    band_labels = _band_labels(results)
    bands = tuple(_average_band(results, labels, band_label) for band_label in band_labels)
    # The table source is spelled out in the template (it must equal
    # ISO_3382_2_TABLE1_SOURCE) so that no English sentence hides in a parameter.
    notes = [
        diag("Decay curves are never averaged; only VALID T values enter the mean."),
        diag(
            "ISO 3382-2 class {klass}: {n_source} source position(s), {n_mic} microphone "
            "position(s), {combos} source-microphone combination(s) against "
            "ISO 3382-2:2008, 4.3.1, Table 1, read from the standard's preview pages "
            "(cdn.standards.iteh.ai sample of ISO 3382-2:2008) on 2026-09-24; footnotes not "
            "implemented. The class is a label; the other clause 4 "
            "conditions (position spacing, distances from surfaces) are not checked.",
            klass=klass,
            n_source=n_source,
            n_mic=n_mic,
            combos=combos,
        ),
    ]
    return AveragedDecay(
        bands=bands,
        n_sessions=len(results),
        n_source_positions=n_source,
        n_microphone_positions=n_mic,
        iso_3382_2_class=klass,
        notes=tuple(notes),
        n_combinations=combos,
    )


def _band_labels(results: Sequence[AnalysisResult]) -> list[str]:
    seen: list[str] = []
    for result in results:
        for band in (result.decay.broadband, *result.decay.bands):
            if band.band_label not in seen:
                seen.append(band.band_label)
    return seen


def _average_band(
    results: Sequence[AnalysisResult], labels: Sequence[str], band_label: str
) -> AveragedBand:
    edt = _average_metric(results, labels, band_label, "edt")
    t20 = _average_metric(results, labels, band_label, "t20")
    t30 = _average_metric(results, labels, band_label, "t30")
    if t30.seconds is not None:
        rt60, basis = t30.seconds, "T30"
    elif t20.seconds is not None:
        rt60, basis = t20.seconds, "T20"
    else:
        rt60, basis = None, None
    return AveragedBand(
        band_label=band_label,
        edt=edt,
        t20=t20,
        t30=t30,
        rt60_estimate_s=rt60,
        rt60_basis=basis,
    )


def _average_metric(
    results: Sequence[AnalysisResult],
    labels: Sequence[str],
    band_label: str,
    attr: str,
) -> AveragedMetric:
    values: list[float] = []
    contributing: list[str] = []
    for result, label in zip(results, labels, strict=True):
        band = _band(result, band_label)
        if band is None:
            continue
        metric: DecayMetric = getattr(band, attr)
        if metric.validity is Validity.VALID and metric.seconds is not None:
            values.append(float(metric.seconds))
            contributing.append(label)
    name = f"{band_label}.{attr}"
    if not values:
        return AveragedMetric(
            name=name,
            seconds=None,
            count=0,
            spread_s=None,
            contributing=(),
            validity=Validity.NOT_COMPUTED,
            reason=diag("no VALID values to average"),
        )
    mean = statistics.fmean(values)
    spread = max(values) - min(values) if len(values) > 1 else 0.0
    return AveragedMetric(
        name=name,
        seconds=mean,
        count=len(values),
        spread_s=spread,
        contributing=tuple(contributing),
        validity=Validity.VALID,
    )


def _band(result: AnalysisResult, band_label: str) -> Any:
    if result.decay.broadband.band_label == band_label:
        return result.decay.broadband
    for band in result.decay.bands:
        if band.band_label == band_label:
            return band
    return None
