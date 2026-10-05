"""Display words for stored values: validity, finding severity and topic,
comparison metric ids and match status.

Result and comparison files keep these as stable English machine values; the
GUI and the text reports show them through these functions, in the active
language.
"""

from __future__ import annotations

from reverbscope.i18n import _
from reverbscope.models.result import Validity


def validity_word(validity: Validity) -> str:
    """Translated word for a metric validity."""
    words = {
        Validity.VALID: _("valid"),
        Validity.UNRELIABLE: _("unreliable"),
        Validity.INSUFFICIENT_RANGE: _("insufficient range"),
        Validity.NOT_COMPUTED: _("not computed"),
        Validity.OUTSIDE_EXCITATION: _("outside the sweep's range"),
        Validity.NOT_COMPARABLE: _("not comparable"),
    }
    return words.get(validity, str(validity))


def severity_text(severity: str) -> str:
    """Translated finding severity (``warning``, ``notice``, ``info``)."""
    return {"warning": _("warning"), "notice": _("notice"), "info": _("info")}.get(
        severity, severity
    )


def topic_text(topic: str) -> str:
    """Translated finding topic."""
    return {
        "reverberation": _("reverberation"),
        "clarity": _("clarity"),
        "noise": _("noise"),
        "early_reflections": _("early reflections"),
        "low_frequency": _("low frequency"),
        "measurement": _("measurement"),
        "comparison": _("comparison"),
    }.get(topic, topic)


def metric_label(name: str, unit: str = "") -> str:
    """A readable, translated name for a comparison metric id ("band.63 Hz.t20")."""
    fixed = {
        "noise.rms_dbfs": _("Background noise, RMS"),
        "placement.source_height_m": _("Loudspeaker height"),
        "placement.ceiling_height_m": _("Plane above the devices"),
        "placement.horizontal_separation_m": _("Horizontal separation"),
        "loopback.path_delay_ms": _("Loopback path delay"),
    }
    text = fixed.get(name)
    if text is None:
        parts = name.split(".")
        if parts[0] == "broadband":
            where, rest = _("Broadband"), parts[1:]
        elif parts[0] == "band" and len(parts) >= 2:
            where, rest = parts[1], parts[2:]
        else:
            where, rest = name, []
        metric = rest[0] if rest else ""
        what = {
            "rt60_estimate": _("RT60 estimate"),
            "edt": "EDT",
            "t20": "T20",
            "t30": "T30",
            "c50": "C50",
            "c80": "C80",
            "d50": "D50",
            "centre_time": _("Centre time"),
        }.get(metric, metric)
        text = f"{where} {what}".strip()
    return f"{text} ({unit})" if unit else text


def status_text(status: str) -> str:
    """Translated reflection / resonance match status."""
    return {
        "matched": _("matched"),
        "appeared": _("appeared"),
        "disappeared": _("disappeared"),
    }.get(status, status)


def accuracy_class_text(klass: str) -> str:
    """Translated ISO 3382-2 accuracy class (``survey`` ... ``below_survey``)."""
    return {
        "survey": _("survey"),
        "engineering": _("engineering"),
        "precision": _("precision"),
        "below_survey": _("below survey"),
    }.get(klass, klass)
