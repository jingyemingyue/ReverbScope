"""Display words for stored values: validity, finding severity and topic,
comparison metric ids and match status.

Result and comparison files keep these as stable English machine values; the
GUI and the text reports show them through these functions, in the active
language.
"""

from __future__ import annotations

from roomscope.i18n import N_, _
from roomscope.models.result import Validity

#: The English word for each validity: what :func:`validity_word` translates,
#: and what a stored comparison reason says ("baseline insufficient range"),
#: so that :func:`~roomscope.i18n.localize` can show it translated too.
VALIDITY_WORDS: dict[Validity, str] = {
    Validity.VALID: N_("valid"),
    Validity.UNRELIABLE: N_("unreliable"),
    Validity.INSUFFICIENT_RANGE: N_("insufficient range"),
    Validity.NOT_COMPUTED: N_("not computed"),
    Validity.OUTSIDE_EXCITATION: N_("outside the sweep's range"),
    Validity.NOT_COMPARABLE: N_("not comparable"),
}


def validity_word(validity: Validity) -> str:
    """Translated word for a metric validity."""
    word = VALIDITY_WORDS.get(validity)
    return _(word) if word is not None else str(validity)


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


def signed_number(value: float, digits: int) -> str:
    """``value`` with its sign at ``digits`` decimals: ``+0.0``, never ``-0.0``.

    A change that rounds to zero (a difference of -1e-12 s) is no change.
    """
    return f"{round(value, digits) + 0.0:+.{digits}f}"


def frequency_text(hz: float) -> str:
    """1000 -> ``1 kHz``, 31.5 -> ``31.5 Hz``."""
    # 999.5 Hz and up round to 1000 at three digits: "1 kHz", not "1e+03 Hz".
    return f"{hz / 1000:.3g} kHz" if hz >= 999.5 else f"{hz:.3g} Hz"


def noise_band_hz(name: str) -> float | None:
    """The centre of a noise band metric id (``noise.band.31.5Hz`` -> 31.5)."""
    band = name.removeprefix("noise.band.")
    if band == name or not band.endswith("Hz"):
        return None
    try:
        return float(band[:-2])
    except ValueError:
        return None


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
    noise_hz = noise_band_hz(name)
    if text is None and noise_hz is not None:
        text = _("Background noise, {band}").format(band=frequency_text(noise_hz))
    if text is None:
        metrics = {
            "rt60_estimate": _("RT60 estimate"),
            "edt": "EDT",
            "t20": "T20",
            "t30": "T30",
            "c50": "C50",
            "c80": "C80",
            "d50": "D50",
            "centre_time": _("Centre time"),
        }
        scope, _dot, metric = name.rpartition(".")
        if metric not in metrics:
            # "band.63 Hz" (a band missing on one side) has no metric part.
            scope, metric = name, ""
        if scope == "broadband":
            where = _("Broadband")
        elif scope.startswith("band."):
            # Split from the right: a label such as "31.5 Hz" has a dot too.
            where = scope.removeprefix("band.")
        else:
            where = scope
        text = f"{where} {metrics.get(metric, metric)}".strip()
    return f"{text} ({unit})" if unit else text


def surface_text(surface: str | None) -> str:
    """Translated name of a placement surface id (``lower_plane`` / ``upper_plane``)."""
    names = {
        "lower_plane": _("Reference plane"),
        "upper_plane": _("Plane above the devices"),
    }
    return names.get(surface or "", surface or "")


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
