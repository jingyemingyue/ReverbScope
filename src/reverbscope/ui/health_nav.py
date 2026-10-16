"""Which analysis view a health check is about.

Routing only: the check's id, or the metric groups it already names. Nothing
here adds a diagnosis the health report did not compute.
"""

from __future__ import annotations

from reverbscope.health import (
    METRIC_DECAY,
    METRIC_ENERGY,
    METRIC_FREQUENCY_RESPONSE,
    METRIC_NOISE,
    METRIC_PLACEMENT,
    METRIC_REFLECTIONS,
    METRIC_RESONANCES,
    HealthCheck,
)
from reverbscope.i18n import _

_BY_ID = {
    "reference": "fr",
    "sweep": "fr",
    "playback_speed": "fr",
    "direct_sound": "etc",
    "level": "etc",
    "distortion": "fr",
    "device": "etc",
    "dropouts": "etc",
    "decay_range": "decay",
    "noise": "noise",
    "length": "etc",
    "loopback": "fr",
}

_BY_METRIC = {
    METRIC_FREQUENCY_RESPONSE: "fr",
    METRIC_DECAY: "decay",
    METRIC_ENERGY: "etc",
    METRIC_NOISE: "noise",
    METRIC_REFLECTIONS: "etc",
    METRIC_PLACEMENT: "room",
    METRIC_RESONANCES: "report",
}


def view_for_check(check: HealthCheck) -> str:
    """The view id a problem check opens, or ``""`` when none fits."""
    found = _BY_ID.get(check.id, "")
    if found:
        return found
    for group in check.affects:
        mapped = _BY_METRIC.get(group, "")
        if mapped:
            return mapped
    return ""


def view_title(view_id: str) -> str:
    """The analysis view's own title, for a health-check button."""
    titles = {
        "fr": _("Frequency response"),
        "decay": _("Decay"),
        "etc": _("Impulse response"),
        "noise": _("Noise"),
        "room": _("Room"),
        "report": _("Full report"),
        "overview": _("Overview"),
        "spectrogram": _("Spectrogram"),
        "waterfall": _("Waterfall"),
    }
    return titles.get(view_id, view_id)
