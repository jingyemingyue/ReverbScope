"""Rows of the decay and energy tables (Overview view), shared with no chart code."""

from __future__ import annotations

from reverbscope.i18n import _
from reverbscope.interpretation.profiles import band_text
from reverbscope.models.result import AnalysisResult, EnergyMetric, Validity


def decay_table_rows(result: AnalysisResult) -> list[tuple[str, str, str, str, str]]:
    """Rows (band, EDT, T20, T30, RT60 estimate) for a table widget."""

    def fmt(metric_seconds: float | None, validity: Validity) -> str:
        if validity is Validity.VALID and metric_seconds is not None:
            return f"{metric_seconds:.2f} s"
        if validity is Validity.UNRELIABLE and metric_seconds is not None:
            return f"({metric_seconds:.2f} s)"
        if validity is Validity.INSUFFICIENT_RANGE:
            return _("insufficient range")
        return _("n/a")

    rows: list[tuple[str, str, str, str, str]] = []
    for band in (result.decay.broadband, *result.decay.bands):
        rt = (
            f"{band.rt60_estimate_s:.2f} s ({band.rt60_basis})"
            if band.rt60_estimate_s is not None
            else "-"
        )
        rows.append(
            (
                band_text(band.band_label),
                fmt(band.edt.seconds, band.edt.validity),
                fmt(band.t20.seconds, band.t20.validity),
                fmt(band.t30.seconds, band.t30.validity),
                rt,
            )
        )
    return rows


def energy_table_rows(result: AnalysisResult) -> list[tuple[str, str, str, str, str]]:
    """Rows (band, C50, C80, D50, centre time). Ratios, not a room score."""

    def fmt(metric: EnergyMetric) -> str:
        if metric.value is None:
            if metric.validity is Validity.INSUFFICIENT_RANGE:
                return _("insufficient range")
            return _("n/a")
        if metric.unit == "dB":
            text = f"{metric.value:+.1f} dB"
        elif metric.unit == "%":
            text = f"{metric.value:.0f} %"
        else:
            text = f"{metric.value * 1000:.0f} ms"
        if metric.validity is Validity.VALID:
            return text
        if metric.validity is Validity.UNRELIABLE:
            return f"({text})"
        if metric.validity is Validity.INSUFFICIENT_RANGE:
            return _("insufficient range")
        return _("n/a")

    rows: list[tuple[str, str, str, str, str]] = []
    for band in (result.decay.broadband, *result.decay.bands):
        rows.append(
            (
                band_text(band.band_label),
                fmt(band.c50),
                fmt(band.c80),
                fmt(band.d50),
                fmt(band.centre_time),
            )
        )
    return rows
