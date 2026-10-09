"""What a recording profile wants, in words.

A profile's thresholds are class attributes and its reasoning lives in its
finding sentences; this module says them up front, before a measurement,
so a user can choose a profile knowing what it will and will not judge.
Everything comes from the profile object: a third-party profile from an
entry point is explained from the same attributes.

Thresholds are engineering choices for one kind of recording, stated in
``docs/MEASUREMENT_METHODOLOGY.md`` §8; none is a grade or an ISO limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reverbscope.i18n import _, current_locale
from reverbscope.interpretation.profiles import ProfileBase, profile_title
from reverbscope.interpretation.registry import available_profiles, get_profile


@dataclass(frozen=True)
class ProfileExplanation:
    """One profile explained in the interface language."""

    name: str
    title: str
    description: str
    #: What the profile watches for, one sentence each.
    wants: tuple[str, ...]
    #: What it does not judge.
    skips: tuple[str, ...]
    #: The numbers behind the sentences (units in the keys).
    thresholds: dict[str, Any]
    locale: str = "en"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "wants": list(self.wants),
            "skips": list(self.skips),
            "thresholds": self.thresholds,
            "locale": self.locale,
        }


def profile_description(name: str) -> str:
    """The profile's one-line description in the interface language.

    The built-in descriptions are translated here; a third-party profile
    shows its own English text.
    """
    texts = {
        "generic": _("General observations, not tied to a specific instrument or voice."),
        "vocal": _("Close-miked lead or backing vocals."),
        "voiceover": _("Voice-over, narration and audiobook."),
        "acoustic_guitar": _("Acoustic guitar, single microphone or close pair."),
        "drums": _("Drums, close mics (kick, snare, toms) with or without overheads."),
        "room_mic": _("Room microphone or ambient pickup: the room is the instrument."),
        "choir": _("Choir or small ensemble, one or more microphones."),
    }
    if name in texts:
        return texts[name]
    try:
        return str(getattr(get_profile(name), "description", "") or "")
    except Exception:  # an entry-point profile that fails to load
        return ""


def explain_profile(name: str) -> ProfileExplanation:
    """``name`` explained from its thresholds; raises for an unknown profile."""
    profile = get_profile(name)
    title = profile_title(name)
    wants: list[str] = []
    skips: list[str] = []
    long_s = float(getattr(profile, "long_decay_s", ProfileBase.long_decay_s))
    very_long_s = float(getattr(profile, "very_long_decay_s", ProfileBase.very_long_decay_s))
    wants.append(
        _(
            "Reverberation: an RT60 up to {long:.1f} s passes without comment; above it the "
            "decay is noticeable, above {very_long:.1f} s it is long (a warning)."
        ).format(long=long_s, very_long=very_long_s)
    )
    reflection_db = float(
        getattr(profile, "strong_reflection_db", ProfileBase.strong_reflection_db)
    )
    window_ms = float(
        getattr(profile, "strong_reflection_window_ms", ProfileBase.strong_reflection_window_ms)
    )
    wants.append(
        _(
            "Early reflections: a reflection at or above {level:.0f} dB relative to the direct "
            "sound within {window:.0f} ms is strong."
        ).format(level=reflection_db, window=window_ms)
    )
    metric = getattr(profile, "clarity_metric", ProfileBase.clarity_metric)
    low = getattr(profile, "clarity_low_db", None)
    high = getattr(profile, "clarity_high_db", None)
    thresholds: dict[str, Any] = {
        "long_decay_s": long_s,
        "very_long_decay_s": very_long_s,
        "strong_reflection_db": reflection_db,
        "strong_reflection_window_ms": window_ms,
        "clarity_metric": None if metric is None else str(metric).upper(),
        "clarity_low_db": low,
        "clarity_high_db": high,
    }
    if metric is None:
        skips.append(_("Clarity (C50 / C80) is not judged: this kind of recording wants the room."))
    else:
        label = str(metric).upper()
        if low is not None:
            wants.append(
                _(
                    "Clarity: a {metric} below {low:+.0f} dB is not clear enough for this "
                    "recording."
                ).format(metric=label, low=float(low))
            )
        if high is not None:
            wants.append(
                _(
                    "Clarity: a {metric} above {high:+.0f} dB means the room is too dry for this use."
                ).format(metric=label, high=float(high))
            )
        if low is None and high is None:
            wants.append(
                _("Clarity: {metric} is reported without a threshold.").format(metric=label)
            )
    margin = float(getattr(profile, "quiet_noise_margin_db", ProfileBase.quiet_noise_margin_db))
    thresholds["quiet_noise_margin_db"] = margin
    if bool(getattr(profile, "judges_noise", True)):
        wants.append(
            _(
                "Noise: the noise floor matters once the direct sound is less than {margin:.0f} dB "
                "above it (levels are dBFS, not dB SPL)."
            ).format(margin=margin)
        )
    else:
        skips.append(_("The noise floor is measured but not commented on for this recording."))
    low_max = float(getattr(profile, "low_band_max_hz", ProfileBase.low_band_max_hz))
    ratio = float(getattr(profile, "slow_low_ratio", ProfileBase.slow_low_ratio))
    mid_min = float(getattr(profile, "mid_band_min_hz", ProfileBase.mid_band_min_hz))
    mid_max = float(getattr(profile, "mid_band_max_hz", ProfileBase.mid_band_max_hz))
    thresholds.update(
        {
            "low_band_max_hz": low_max,
            "slow_low_ratio": ratio,
            "mid_band_min_hz": mid_min,
            "mid_band_max_hz": mid_max,
        }
    )
    wants.append(
        _(
            "Low end: bands up to {low:.0f} Hz decaying more than {ratio:.1f} times slower than "
            "the {mid_min:.0f}–{mid_max:.0f} Hz bands is an imbalance; a resonance is named "
            "only when its decay is distinguishable."
        ).format(low=low_max, ratio=ratio, mid_min=mid_min, mid_max=mid_max)
    )
    wants.append(
        _(
            "Every profile checks the measurement first: direct-sound confidence, clipping and "
            "an insufficient decay range are reported before any advice."
        )
    )
    return ProfileExplanation(
        name=name,
        title=title,
        description=profile_description(name),
        wants=tuple(wants),
        skips=tuple(skips),
        thresholds=thresholds,
        locale=current_locale(),
    )


def explain_all() -> list[ProfileExplanation]:
    """Every available profile, in the registry's order; one that fails to
    load is left out (the registry already warned)."""
    out = []
    for name in available_profiles():
        try:
            out.append(explain_profile(name))
        except Exception:
            continue
    return out


__all__ = ["ProfileExplanation", "explain_all", "explain_profile", "profile_description"]
