"""Verdicts on a comparison: did moving the microphone, or the treatment, help?

Reads a :class:`~reverbscope.models.comparison.ComparisonResult`, the
recording profile's thresholds and, when the two results are at hand, their
measurement health, and says for each aspect of the recording whether the
candidate is a *meaningful improvement*, a *meaningful degradation*,
*probably insignificant*, *not comparable*, or whether the evidence is
*insufficient*. Nothing here changes the comparison or either result.

"Meaningful" is measured against the profile's own thresholds (what counts
as a long decay, a strong reflection, a clear or a too-dry room for that
kind of recording) and against the measurement's own spread, never against
statistical significance, which one pair of positions cannot establish
(``docs/MEASUREMENT_METHODOLOGY.md`` §11). A change that is real but has no
consequence for the recording (both takes short for a vocal booth) is
*probably insignificant* for that profile, and the reason says so. A
shorter decay is an improvement only above the profile's thresholds; a
room-microphone profile also judges a room that became too dry through its
clarity bound.

The just-noticeable differences quoted here (5 % for T, 1 dB for C80) are
the ones ISO 3382-1 lists; the table was not verified against the standard
text, and the 1 dB limit is applied to C50 as well. The 3 dB limits for the
noise floor and for a reflection's level are ReverbScope's own (a factor of
two in power). The decay's own spread, the larger of the two takes'
|T30 - T20|, stands in for a single-take uncertainty that ISO 3382-2 only
gives for several positions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from reverbscope.i18n import _, current_locale, localize, pgettext
from reverbscope.interpretation.profiles import decay_length_text, get_profile
from reverbscope.models.comparison import T_JND_PERCENT, ComparisonResult, MetricDelta
from reverbscope.models.result import AnalysisResult, Validity


class Verdict(StrEnum):
    IMPROVEMENT = "meaningful_improvement"
    DEGRADATION = "meaningful_degradation"
    INSIGNIFICANT = "probably_insignificant"
    NOT_COMPARABLE = "not_comparable"
    INSUFFICIENT = "insufficient_evidence"


#: Just-noticeable difference for a clarity index (ISO 3382-1 lists 1 dB for
#: C80; applied to C50 too). Table not verified against the standard text.
CLARITY_JND_DB = 1.0
#: A noise floor that moved by less than this is called unchanged: a factor
#: of two in power. ReverbScope's own limit.
NOISE_MEANINGFUL_DB = 3.0
#: A reflection whose level moved by less than this is called unchanged.
#: ReverbScope's own limit.
REFLECTION_MEANINGFUL_DB = 3.0

ASPECT_REVERBERATION = "reverberation"
ASPECT_CLARITY = "clarity"
ASPECT_REFLECTIONS = "early_reflections"
ASPECT_NOISE = "noise"
ASPECT_LOW_END = "low_end"

#: Stored notes of a comparison that say a topic was not compared.
_REFLECTIONS_NOT_COMPARED = "early reflections are not compared unless"
_RESONANCES_NOT_COMPARED = "low-frequency resonances are not compared"
#: Stored notes that name a condition the two takes do not share.
_CONDITION_NOTES = ("sample rates differ", "sweep durations differ", "sweep levels differ")


@dataclass(frozen=True)
class AspectVerdict:
    """The verdict on one aspect of the recording."""

    #: Stable identifier (``ASPECT_*``).
    aspect: str
    verdict: Verdict
    #: The aspect's name in the interface language.
    title: str
    #: Why, in the interface language.
    reason: str
    #: The numbers the verdict rests on (units in the keys).
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "aspect": self.aspect,
            "verdict": str(self.verdict),
            "title": self.title,
            "reason": self.reason,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ComparisonVerdict:
    """The verdicts of one comparison under one recording profile."""

    profile: str
    aspects: tuple[AspectVerdict, ...]
    #: Conditions the takes do not share, or that temper every verdict, in
    #: the interface language.
    conditions: tuple[str, ...] = ()
    locale: str = "en"

    def count(self, verdict: Verdict) -> int:
        return sum(1 for aspect in self.aspects if aspect.verdict is verdict)

    def headline(self) -> str:
        """One sentence: how many aspects improved, degraded, and so on."""
        return _(
            "{better} improved, {worse} degraded, {same} probably insignificant, "
            "{not_comparable} not comparable, {insufficient} with insufficient evidence"
        ).format(
            better=self.count(Verdict.IMPROVEMENT),
            worse=self.count(Verdict.DEGRADATION),
            same=self.count(Verdict.INSIGNIFICANT),
            not_comparable=self.count(Verdict.NOT_COMPARABLE),
            insufficient=self.count(Verdict.INSUFFICIENT),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "locale": self.locale,
            "headline": self.headline(),
            "aspects": [aspect.to_dict() for aspect in self.aspects],
            "conditions": list(self.conditions),
        }


def verdict_word(verdict: Verdict | str) -> str:
    """The verdict in the interface language."""
    words = {
        Verdict.IMPROVEMENT: pgettext("verdict", "meaningful improvement"),
        Verdict.DEGRADATION: pgettext("verdict", "meaningful degradation"),
        Verdict.INSIGNIFICANT: pgettext("verdict", "probably insignificant"),
        Verdict.NOT_COMPARABLE: pgettext("verdict", "not comparable"),
        Verdict.INSUFFICIENT: pgettext("verdict", "insufficient evidence"),
    }
    try:
        return words[Verdict(verdict)]
    except ValueError:
        return str(verdict)


def verdict_chip(verdict: Verdict | str) -> str:
    """A short form for a chip or a column."""
    words = {
        Verdict.IMPROVEMENT: pgettext("verdict chip", "improved"),
        Verdict.DEGRADATION: pgettext("verdict chip", "degraded"),
        Verdict.INSIGNIFICANT: pgettext("verdict chip", "unchanged"),
        Verdict.NOT_COMPARABLE: pgettext("verdict chip", "not comparable"),
        Verdict.INSUFFICIENT: pgettext("verdict chip", "insufficient"),
    }
    try:
        return words[Verdict(verdict)]
    except ValueError:
        return str(verdict)


def aspect_text(aspect: str) -> str:
    names = {
        ASPECT_REVERBERATION: pgettext("aspect", "Reverberation"),
        ASPECT_CLARITY: pgettext("aspect", "Clarity"),
        ASPECT_REFLECTIONS: pgettext("aspect", "Early reflections"),
        ASPECT_NOISE: pgettext("aspect", "Noise floor"),
        ASPECT_LOW_END: pgettext("aspect", "Low end"),
    }
    return names.get(aspect, aspect)


def judge_comparison(
    comparison: ComparisonResult,
    profile_name: str = "generic",
    *,
    baseline: AnalysisResult | None = None,
    candidate: AnalysisResult | None = None,
) -> ComparisonVerdict:
    """The verdicts of ``comparison`` under ``profile_name``.

    With ``baseline`` and ``candidate`` (the results the comparison was made
    from) the measurement health of each side is a condition: a side whose
    health is invalid leaves every aspect with insufficient evidence.
    """
    profile = get_profile(profile_name)
    conditions = _shared_conditions(comparison)
    invalid = _invalid_sides(baseline, candidate, conditions)
    conditions.append(_single_pair_caveat())
    if not comparison.comparable:
        reason = _("the two sessions cannot be compared: {note}").format(
            note=localize(_refusal(comparison))
        )
        refused = tuple(
            AspectVerdict(aspect, Verdict.NOT_COMPARABLE, aspect_text(aspect), reason)
            for aspect in _aspects_of(profile)
        )
        return ComparisonVerdict(profile_name, refused, tuple(conditions), current_locale())
    aspects: list[AspectVerdict | None] = [
        _reverberation(comparison, profile),
        _clarity(comparison, profile),
        _reflections(comparison, profile),
        _noise(comparison),
        _low_end(comparison),
    ]
    judged = []
    for aspect in aspects:
        if aspect is None:
            continue
        if invalid and aspect.verdict is not Verdict.NOT_COMPARABLE:
            aspect = AspectVerdict(
                aspect.aspect,
                Verdict.INSUFFICIENT,
                aspect.title,
                _(
                    "the {side} measurement is invalid ({checks}); no verdict is drawn from it"
                ).format(side=invalid[0][0], checks=invalid[0][1]),
                aspect.evidence,
            )
        judged.append(aspect)
    return ComparisonVerdict(profile_name, tuple(judged), tuple(conditions), current_locale())


# --- conditions ----------------------------------------------------------------------


def _refusal(comparison: ComparisonResult) -> str:
    from reverbscope.models.comparison import REFUSAL_NOTE_PREFIXES

    for note in comparison.notes:
        if note.startswith(REFUSAL_NOTE_PREFIXES):
            return note
    return comparison.notes[0] if comparison.notes else ""


def _shared_conditions(comparison: ComparisonResult) -> list[str]:
    """The conditions the two takes do not share, from the comparison's notes."""
    return [localize(note) for note in comparison.notes if note.startswith(_CONDITION_NOTES)]


def _single_pair_caveat() -> str:
    return _(
        "One pair of positions: a verdict is about these two takes, not about the room in "
        "general, and no change is statistically significant on this evidence."
    )


def _invalid_sides(
    baseline: AnalysisResult | None,
    candidate: AnalysisResult | None,
    conditions: list[str],
) -> list[tuple[str, str]]:
    """``(side, checks)`` for each side whose measurement health is invalid;
    a side with warnings, or whose health is unknown, is named in ``conditions``."""
    from reverbscope.health import HealthStatus, assess

    invalid: list[tuple[str, str]] = []
    for side, result in (
        (pgettext("comparison side", "baseline"), baseline),
        (pgettext("comparison side", "candidate"), candidate),
    ):
        if result is None:
            continue
        report = assess(result)
        if report.overall is HealthStatus.GOOD:
            continue
        titles = ", ".join(check.title for check in report.problems) or report.overall
        if report.overall is HealthStatus.INVALID:
            invalid.append((side, titles))
            conditions.append(
                _("The {side} measurement is invalid: {checks}.").format(side=side, checks=titles)
            )
        elif report.overall is HealthStatus.WARNING:
            conditions.append(
                _("The {side} measurement has health warnings: {checks}.").format(
                    side=side, checks=titles
                )
            )
        else:
            # An imported impulse response: nothing is wrong, nothing was checked.
            conditions.append(
                _("The {side} measurement's health is unknown: {checks}.").format(
                    side=side, checks=titles
                )
            )
    return invalid


def _aspects_of(profile: object) -> list[str]:
    aspects = [ASPECT_REVERBERATION]
    if getattr(profile, "clarity_metric", "c50") is not None:
        aspects.append(ASPECT_CLARITY)
    aspects += [ASPECT_REFLECTIONS, ASPECT_NOISE, ASPECT_LOW_END]
    return aspects


# --- the aspects ---------------------------------------------------------------------


def _delta(comparison: ComparisonResult, name: str) -> MetricDelta | None:
    return next((item for item in comparison.decay if item.name == name), None)


def _not_comparable(aspect: str, delta: MetricDelta | None, missing: str) -> AspectVerdict:
    reason = localize(delta.reason) if delta is not None and delta.reason else missing
    return AspectVerdict(aspect, Verdict.NOT_COMPARABLE, aspect_text(aspect), reason)


def _decay_label(profile: object, seconds: float) -> str:
    if seconds >= float(getattr(profile, "very_long_decay_s", 1.0)):
        return "long"
    if seconds >= float(getattr(profile, "long_decay_s", 0.6)):
        return "noticeable"
    return "short"


_LABEL_RANK = {"short": 0, "noticeable": 1, "long": 2}


def _reverberation(comparison: ComparisonResult, profile: object) -> AspectVerdict:
    aspect = ASPECT_REVERBERATION
    rt = _delta(comparison, "broadband.rt60_estimate")
    if (
        rt is None
        or rt.validity is not Validity.VALID
        or rt.baseline is None
        or rt.candidate is None
        or rt.baseline <= 0.0
    ):
        return _not_comparable(aspect, rt, _("the broadband RT60 is not comparable"))
    change = rt.candidate - rt.baseline
    percent = 100.0 * change / rt.baseline
    # The measurement's own spread: how far T20 and T30 disagree within one
    # take, on whichever side disagrees more.
    spread = max(_t_spread(comparison, "broadband"), 0.0)
    jnd_s = T_JND_PERCENT / 100.0 * rt.baseline
    before = _decay_label(profile, rt.baseline)
    after = _decay_label(profile, rt.candidate)
    evidence = {
        "baseline_s": rt.baseline,
        "candidate_s": rt.candidate,
        "delta_s": change,
        "delta_percent": percent,
        "jnd_percent": T_JND_PERCENT,
        "own_spread_s": spread,
        "baseline_label": before,
        "candidate_label": after,
        "long_decay_s": getattr(profile, "long_decay_s", None),
        "very_long_decay_s": getattr(profile, "very_long_decay_s", None),
    }
    title = aspect_text(aspect)
    if abs(change) <= max(jnd_s, spread):
        if abs(change) <= jnd_s:
            reason = _(
                "RT60 {baseline:.2f} s to {candidate:.2f} s ({percent:+.1f} %): within the "
                "just-noticeable difference of about {jnd:g} %"
            ).format(
                baseline=rt.baseline, candidate=rt.candidate, percent=percent, jnd=T_JND_PERCENT
            )
        else:
            reason = _(
                "RT60 {baseline:.2f} s to {candidate:.2f} s ({percent:+.1f} %): smaller than the "
                "{spread:.2f} s by which T20 and T30 disagree within one take"
            ).format(baseline=rt.baseline, candidate=rt.candidate, percent=percent, spread=spread)
        return AspectVerdict(aspect, Verdict.INSIGNIFICANT, title, reason, evidence)
    if before == "short" and after == "short":
        reason = _(
            "RT60 {baseline:.2f} s to {candidate:.2f} s ({percent:+.1f} %): a real change, but "
            "both takes are short for a {profile} recording (below {limit:.1f} s), so it does "
            "not matter for the recording"
        ).format(
            baseline=rt.baseline,
            candidate=rt.candidate,
            percent=percent,
            profile=_profile_title(profile),
            limit=float(getattr(profile, "long_decay_s", 0.6)),
        )
        return AspectVerdict(aspect, Verdict.INSIGNIFICANT, title, reason, evidence)
    if _LABEL_RANK[after] < _LABEL_RANK[before]:
        reason = _(
            "RT60 {baseline:.2f} s to {candidate:.2f} s ({percent:+.1f} %): from '{before}' to "
            "'{after}' against this profile's decay thresholds"
        ).format(
            baseline=rt.baseline,
            candidate=rt.candidate,
            percent=percent,
            before=decay_length_text(before),
            after=decay_length_text(after),
        )
        return AspectVerdict(aspect, Verdict.IMPROVEMENT, title, reason, evidence)
    if _LABEL_RANK[after] > _LABEL_RANK[before]:
        reason = _(
            "RT60 {baseline:.2f} s to {candidate:.2f} s ({percent:+.1f} %): from '{before}' to "
            "'{after}' against this profile's decay thresholds"
        ).format(
            baseline=rt.baseline,
            candidate=rt.candidate,
            percent=percent,
            before=decay_length_text(before),
            after=decay_length_text(after),
        )
        return AspectVerdict(aspect, Verdict.DEGRADATION, title, reason, evidence)
    # Same label, both noticeable or both long: the direction counts.
    verdict = Verdict.IMPROVEMENT if change < 0.0 else Verdict.DEGRADATION
    reason = _(
        "RT60 {baseline:.2f} s to {candidate:.2f} s ({percent:+.1f} %): {direction}, and still "
        "'{label}' for this profile"
    ).format(
        baseline=rt.baseline,
        candidate=rt.candidate,
        percent=percent,
        direction=pgettext("decay", "shorter") if change < 0.0 else pgettext("decay", "longer"),
        label=decay_length_text(after),
    )
    return AspectVerdict(aspect, verdict, title, reason, evidence)


def _t_spread(comparison: ComparisonResult, prefix: str) -> float:
    """The larger |T30 - T20| of the two takes (s), 0 when one is missing."""
    t20 = _delta(comparison, f"{prefix}.t20")
    t30 = _delta(comparison, f"{prefix}.t30")
    if t20 is None or t30 is None:
        return 0.0
    spreads = []
    for side in ("baseline", "candidate"):
        a = getattr(t20, side)
        b = getattr(t30, side)
        if a is not None and b is not None:
            spreads.append(abs(float(b) - float(a)))
    return max(spreads) if spreads else 0.0


def _profile_title(profile: object) -> str:
    from reverbscope.interpretation.profiles import profile_title

    return profile_title(str(getattr(profile, "name", "generic")))


def _clarity(comparison: ComparisonResult, profile: object) -> AspectVerdict | None:
    metric = getattr(profile, "clarity_metric", "c50")
    if metric is None:
        return None
    aspect = ASPECT_CLARITY
    delta = _delta(comparison, f"broadband.{metric}")
    label = str(metric).upper()
    if (
        delta is None
        or delta.validity is not Validity.VALID
        or delta.baseline is None
        or delta.candidate is None
    ):
        return _not_comparable(aspect, delta, _("{metric} is not comparable").format(metric=label))
    low = getattr(profile, "clarity_low_db", None)
    high = getattr(profile, "clarity_high_db", None)
    lo = -math.inf if low is None else float(low)
    hi = math.inf if high is None else float(high)
    change = delta.candidate - delta.baseline
    evidence = {
        "metric": label,
        "baseline_db": delta.baseline,
        "candidate_db": delta.candidate,
        "delta_db": change,
        "jnd_db": CLARITY_JND_DB,
        "clarity_low_db": low,
        "clarity_high_db": high,
    }
    title = aspect_text(aspect)
    values = _("{metric} {baseline:+.1f} dB to {candidate:+.1f} dB ({delta:+.1f} dB)").format(
        metric=label, baseline=delta.baseline, candidate=delta.candidate, delta=change
    )
    if abs(change) < CLARITY_JND_DB:
        reason = _("{values}: within the just-noticeable difference of about {jnd:g} dB").format(
            values=values, jnd=CLARITY_JND_DB
        )
        return AspectVerdict(aspect, Verdict.INSIGNIFICANT, title, reason, evidence)
    inside_before = lo <= delta.baseline <= hi
    inside_after = lo <= delta.candidate <= hi
    if inside_before and inside_after:
        reason = _(
            "{values}: a real change, but both takes are inside the range this profile wants, "
            "so it does not matter for the recording"
        ).format(values=values)
        return AspectVerdict(aspect, Verdict.INSIGNIFICANT, title, reason, evidence)
    if inside_after:
        reason = _("{values}: now inside the range this profile wants").format(values=values)
        return AspectVerdict(aspect, Verdict.IMPROVEMENT, title, reason, evidence)
    if inside_before:
        where = (
            _("too dry for a {profile} recording")
            if delta.candidate > hi
            else _("not clear enough for a {profile} recording")
        ).format(profile=_profile_title(profile))
        reason = _("{values}: now {where}").format(values=values, where=where)
        return AspectVerdict(aspect, Verdict.DEGRADATION, title, reason, evidence)
    # Outside on both sides: toward the range or away from it.
    toward = abs(_distance_to_range(delta.candidate, lo, hi)) < abs(
        _distance_to_range(delta.baseline, lo, hi)
    )
    where = (
        _("too dry for a {profile} recording")
        if delta.candidate > hi
        else _("not clear enough for a {profile} recording")
    ).format(profile=_profile_title(profile))
    if toward:
        reason = _("{values}: nearer the range this profile wants, but still {where}").format(
            values=values, where=where
        )
        return AspectVerdict(aspect, Verdict.IMPROVEMENT, title, reason, evidence)
    reason = _("{values}: further from the range this profile wants; {where}").format(
        values=values, where=where
    )
    return AspectVerdict(aspect, Verdict.DEGRADATION, title, reason, evidence)


def _distance_to_range(value: float, low: float, high: float) -> float:
    if value < low:
        return value - low
    if value > high:
        return value - high
    return 0.0


def _strongest(matches: list[tuple[float, float]]) -> tuple[float, float] | None:
    return max(matches, key=lambda item: item[1], default=None)


def _reflections(comparison: ComparisonResult, profile: object) -> AspectVerdict:
    aspect = ASPECT_REFLECTIONS
    title = aspect_text(aspect)
    not_compared = next(
        (note for note in comparison.notes if note.startswith(_REFLECTIONS_NOT_COMPARED)), None
    )
    if not_compared is not None:
        return AspectVerdict(aspect, Verdict.INSUFFICIENT, title, localize(not_compared))
    window = float(getattr(profile, "strong_reflection_window_ms", 30.0))
    threshold = float(getattr(profile, "strong_reflection_db", -10.0))
    before = _strongest(
        [
            (m.baseline_delay_ms, m.baseline_relative_db)
            for m in comparison.reflections
            if m.status in ("matched", "disappeared")
            and m.baseline_delay_ms is not None
            and m.baseline_relative_db is not None
            and m.baseline_delay_ms <= window
        ]
    )
    after = _strongest(
        [
            (m.candidate_delay_ms, m.candidate_relative_db)
            for m in comparison.reflections
            if m.status in ("matched", "appeared")
            and m.candidate_delay_ms is not None
            and m.candidate_relative_db is not None
            and m.candidate_delay_ms <= window
        ]
    )
    evidence: dict[str, Any] = {
        "window_ms": window,
        "threshold_db": threshold,
        "baseline": None if before is None else {"delay_ms": before[0], "level_db": before[1]},
        "candidate": None if after is None else {"delay_ms": after[0], "level_db": after[1]},
        "meaningful_db": REFLECTION_MEANINGFUL_DB,
    }
    if before is None and after is None:
        reason = _("no reflection within {window:g} ms on either side").format(window=window)
        return AspectVerdict(aspect, Verdict.INSIGNIFICANT, title, reason, evidence)
    level_before = before[1] if before is not None else None
    level_after = after[1] if after is not None else None
    if (level_before is None or level_before < threshold) and (
        level_after is None or level_after < threshold
    ):
        reason = _(
            "the strongest reflection within {window:g} ms stays below this profile's "
            "{threshold:.0f} dB threshold on both sides"
        ).format(window=window, threshold=threshold)
        return AspectVerdict(aspect, Verdict.INSIGNIFICANT, title, reason, evidence)
    if level_before is None:
        assert after is not None
        reason = _(
            "a reflection of {level:.1f} dB at {delay:.1f} ms appeared inside this profile's "
            "{window:g} ms window (threshold {threshold:.0f} dB)"
        ).format(level=after[1], delay=after[0], window=window, threshold=threshold)
        return AspectVerdict(aspect, Verdict.DEGRADATION, title, reason, evidence)
    if level_after is None:
        assert before is not None
        reason = _(
            "the reflection of {level:.1f} dB at {delay:.1f} ms is gone from this profile's "
            "{window:g} ms window"
        ).format(level=before[1], delay=before[0], window=window)
        return AspectVerdict(aspect, Verdict.IMPROVEMENT, title, reason, evidence)
    assert before is not None and after is not None
    change = level_after - level_before
    values = _(
        "the strongest reflection within {window:g} ms went from {before:.1f} dB at "
        "{before_ms:.1f} ms to {after:.1f} dB at {after_ms:.1f} ms"
    ).format(
        window=window, before=before[1], before_ms=before[0], after=after[1], after_ms=after[0]
    )
    if abs(change) < REFLECTION_MEANINGFUL_DB:
        reason = _("{values}: within {limit:g} dB").format(
            values=values, limit=REFLECTION_MEANINGFUL_DB
        )
        return AspectVerdict(aspect, Verdict.INSIGNIFICANT, title, reason, evidence)
    if change < 0.0:
        still = (
            _(", still above the {threshold:.0f} dB threshold").format(threshold=threshold)
            if level_after >= threshold
            else ""
        )
        reason = _("{values}: {change:.1f} dB weaker{still}").format(
            values=values, change=-change, still=still
        )
        return AspectVerdict(aspect, Verdict.IMPROVEMENT, title, reason, evidence)
    reason = _("{values}: {change:.1f} dB stronger").format(values=values, change=change)
    return AspectVerdict(aspect, Verdict.DEGRADATION, title, reason, evidence)


def _noise(comparison: ComparisonResult) -> AspectVerdict:
    aspect = ASPECT_NOISE
    title = aspect_text(aspect)
    rms = next((item for item in comparison.noise if item.name == "noise.rms_dbfs"), None)
    if rms is None or rms.validity is Validity.NOT_COMPARABLE:
        return _not_comparable(aspect, rms, _("the noise floor is not comparable"))
    if rms.validity is not Validity.VALID or rms.baseline is None or rms.candidate is None:
        reason = localize(rms.reason) if rms.reason else _("the noise delta is not valid")
        return AspectVerdict(
            aspect,
            Verdict.INSUFFICIENT,
            title,
            _("{reason}: declare the input gain unchanged to compare the noise floor").format(
                reason=reason
            ),
        )
    change = rms.candidate - rms.baseline
    evidence = {
        "baseline_dbfs": rms.baseline,
        "candidate_dbfs": rms.candidate,
        "delta_db": change,
        "meaningful_db": NOISE_MEANINGFUL_DB,
    }
    values = _("noise floor {baseline:.1f} dBFS to {candidate:.1f} dBFS ({delta:+.1f} dB)").format(
        baseline=rms.baseline, candidate=rms.candidate, delta=change
    )
    if abs(change) < NOISE_MEANINGFUL_DB:
        reason = _("{values}: within {limit:g} dB").format(values=values, limit=NOISE_MEANINGFUL_DB)
        return AspectVerdict(aspect, Verdict.INSIGNIFICANT, title, reason, evidence)
    if change < 0.0:
        return AspectVerdict(
            aspect,
            Verdict.IMPROVEMENT,
            title,
            _("{values}: quieter").format(values=values),
            evidence,
        )
    return AspectVerdict(
        aspect, Verdict.DEGRADATION, title, _("{values}: louder").format(values=values), evidence
    )


def _low_end(comparison: ComparisonResult) -> AspectVerdict:
    aspect = ASPECT_LOW_END
    title = aspect_text(aspect)
    not_compared = next(
        (note for note in comparison.notes if note.startswith(_RESONANCES_NOT_COMPARED)), None
    )
    if not_compared is not None:
        return AspectVerdict(aspect, Verdict.INSUFFICIENT, title, localize(not_compared))
    appeared = [
        m.candidate_hz
        for m in comparison.resonances
        if m.status == "appeared" and m.candidate_decay_distinguishable
    ]
    gone = [
        m.baseline_hz
        for m in comparison.resonances
        if m.status == "disappeared" and m.baseline_decay_distinguishable
    ]
    evidence = {
        "appeared_hz": [hz for hz in appeared if hz is not None],
        "disappeared_hz": [hz for hz in gone if hz is not None],
        "matched": sum(1 for m in comparison.resonances if m.status == "matched"),
    }
    if appeared and not gone:
        reason = _(
            "{count} distinguishable low-frequency resonance(s) appeared at {frequencies} Hz"
        ).format(
            count=len(appeared),
            frequencies=", ".join(f"{hz:.0f}" for hz in appeared if hz is not None),
        )
        return AspectVerdict(aspect, Verdict.DEGRADATION, title, reason, evidence)
    if gone and not appeared:
        reason = _(
            "{count} distinguishable low-frequency resonance(s) disappeared ({frequencies} Hz)"
        ).format(
            count=len(gone), frequencies=", ".join(f"{hz:.0f}" for hz in gone if hz is not None)
        )
        return AspectVerdict(aspect, Verdict.IMPROVEMENT, title, reason, evidence)
    if appeared and gone:
        reason = _(
            "{gone} distinguishable resonance(s) disappeared and {new} appeared: the low end "
            "changed rather than improved"
        ).format(gone=len(gone), new=len(appeared))
        return AspectVerdict(aspect, Verdict.DEGRADATION, title, reason, evidence)
    reason = _("no distinguishable low-frequency resonance appeared or disappeared")
    return AspectVerdict(aspect, Verdict.INSIGNIFICANT, title, reason, evidence)


__all__ = [
    "ASPECT_CLARITY",
    "ASPECT_LOW_END",
    "ASPECT_NOISE",
    "ASPECT_REFLECTIONS",
    "ASPECT_REVERBERATION",
    "CLARITY_JND_DB",
    "NOISE_MEANINGFUL_DB",
    "REFLECTION_MEANINGFUL_DB",
    "AspectVerdict",
    "ComparisonVerdict",
    "Verdict",
    "aspect_text",
    "judge_comparison",
    "verdict_chip",
    "verdict_word",
]
