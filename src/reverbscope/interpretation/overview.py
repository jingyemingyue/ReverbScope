"""Overview of a project: every position's takes under one recording profile.

Reads the sessions a project lists (:mod:`reverbscope.io.project_store`),
their results and, through :mod:`reverbscope.health`, their measurement
health, and says for each position what was measured there, whether the
takes repeat, whether the room at that position *fits* the recording
profile, and how the position compares with the first one (the verdicts
of :mod:`reverbscope.interpretation.verdicts`). Across positions it gives
the spatial average of :mod:`reverbscope.core.averaging`, the ISO 3382-2
class the position counts reach, and what to measure next. Nothing here
ranks positions or scores the room: *fits* is the absence of a warning
under the profile, and a choice between two positions that both fit is
the user's, made on the verdicts and on what the recording needs.

Repeatability is judged against the just-noticeable difference for T that
ISO 3382-1 lists (5 %, :data:`~reverbscope.models.comparison.T_JND_PERCENT`;
the table was not verified against the standard text): two takes at one
position whose RT60 differ by more than that disagree, and the overview
says so rather than averaging them quietly.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from reverbscope.core.averaging import AveragedDecay, average_decay, iso_3382_2_class
from reverbscope.errors import ReverbScopeError
from reverbscope.health import HealthStatus, assess
from reverbscope.i18n import _, current_locale, list_join, pgettext
from reverbscope.interpretation.interpreter import Finding, Severity, interpret
from reverbscope.interpretation.profiles import get_profile, profile_title
from reverbscope.interpretation.verdicts import ComparisonVerdict, Verdict, judge_comparison
from reverbscope.labels import accuracy_class_text, topic_text
from reverbscope.models.comparison import T_JND_PERCENT
from reverbscope.models.result import AnalysisResult, Validity
from reverbscope.models.session import MeasurementSession


class Fit(StrEnum):
    """Whether the room at a position fits the recording profile."""

    #: No warning under the profile; the measurement is not invalid.
    FITS = "fits"
    #: The profile warns about the take (the topics are listed).
    WARNINGS = "warnings"
    #: The measurement is invalid, or has no VALID reverberation time.
    UNKNOWN = "unknown"


def fit_word(fit: Fit | str) -> str:
    words = {
        Fit.FITS: pgettext("fit", "fits"),
        Fit.WARNINGS: pgettext("fit", "warnings"),
        Fit.UNKNOWN: pgettext("fit", "cannot say"),
    }
    try:
        return words[Fit(fit)]
    except ValueError:
        return str(fit)


@dataclass(frozen=True)
class ProjectEntry:
    """One session of a project, as the store lists it (``""`` = no position)."""

    position: str
    directory: str
    session: MeasurementSession
    result: AnalysisResult


@dataclass(frozen=True)
class SessionSummary:
    """One take: its health, its headline numbers and its fit."""

    directory: str
    position: str
    created_at: str
    #: :class:`~reverbscope.health.HealthStatus` value.
    health: str
    #: Titles of the health checks that are not good, in the interface language.
    health_problems: tuple[str, ...]
    #: The broadband RT60 (only ever from a VALID T30 or T20) and its basis.
    rt60_s: float | None
    rt60_basis: str | None
    #: The profile's clarity index ("C50" / "C80"), when VALID.
    clarity_metric: str | None
    clarity_db: float | None
    #: The noise floor, and whether it comes from a verified quiet segment.
    noise_rms_dbfs: float | None
    noise_verified: bool
    #: The strongest reflection inside the profile's window, if any.
    reflection_ms: float | None
    reflection_db: float | None
    #: Topics of the profile's warnings (stable ids) and the count of notices.
    warnings: tuple[str, ...]
    notices: int
    fit: Fit
    #: Why, in the interface language.
    fit_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "directory": self.directory,
            "position": self.position,
            "created_at": self.created_at,
            "health": self.health,
            "health_problems": list(self.health_problems),
            "rt60_s": self.rt60_s,
            "rt60_basis": self.rt60_basis,
            "clarity_metric": self.clarity_metric,
            "clarity_db": self.clarity_db,
            "noise_rms_dbfs": self.noise_rms_dbfs,
            "noise_verified": self.noise_verified,
            "reflection_ms": self.reflection_ms,
            "reflection_db": self.reflection_db,
            "warnings": list(self.warnings),
            "notices": self.notices,
            "fit": str(self.fit),
            "fit_reason": self.fit_reason,
        }


@dataclass(frozen=True)
class PositionSummary:
    """One microphone position: its takes, their agreement, and the verdict
    against the first position."""

    label: str
    sessions: tuple[SessionSummary, ...]
    #: Index into ``sessions`` of the take the position is represented by:
    #: the healthiest, then the latest.
    representative: int
    #: Largest difference between the takes' RT60, as a percentage of the
    #: smaller; ``None`` with fewer than two takes with an RT60.
    repeat_spread_percent: float | None
    #: Whether every pair of takes agrees within the T just-noticeable difference.
    repeatable: bool | None
    #: The verdicts of this position's representative take against the first
    #: position's; ``None`` for the first position or when no comparison
    #: could be made.
    verdict: ComparisonVerdict | None
    #: One line about the verdict (or why there is none), in the interface language.
    verdict_text: str

    @property
    def representative_session(self) -> SessionSummary:
        return self.sessions[self.representative]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "sessions": [item.to_dict() for item in self.sessions],
            "representative": self.representative,
            "repeat_spread_percent": self.repeat_spread_percent,
            "repeatable": self.repeatable,
            "verdict": None if self.verdict is None else self.verdict.to_dict(),
            "verdict_text": self.verdict_text,
        }


@dataclass(frozen=True)
class ProjectOverview:
    """A project under one recording profile."""

    name: str
    profile: str
    positions: tuple[PositionSummary, ...]
    #: Sessions in the project folder that no position lists.
    unlisted: tuple[SessionSummary, ...]
    averaged: AveragedDecay | None
    n_source_positions: int
    #: Spread of the positions' representative RT60 across the room, as a
    #: percentage of the mean; ``None`` with fewer than two.
    spatial_spread_percent: float | None
    #: What to measure or check next, in the interface language.
    next_steps: tuple[str, ...] = ()
    locale: str = "en"
    #: Sessions that could not be summarised, with the reason (one line each).
    skipped: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def fitting(self) -> tuple[PositionSummary, ...]:
        return tuple(p for p in self.positions if p.representative_session.fit is Fit.FITS)

    @property
    def iso_3382_2_class(self) -> str | None:
        return None if self.averaged is None else self.averaged.iso_3382_2_class

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "profile": self.profile,
            "locale": self.locale,
            "positions": [item.to_dict() for item in self.positions],
            "unlisted": [item.to_dict() for item in self.unlisted],
            "averaged": None if self.averaged is None else self.averaged.to_dict(),
            "n_source_positions": self.n_source_positions,
            "spatial_spread_percent": self.spatial_spread_percent,
            "next_steps": list(self.next_steps),
            "skipped": [list(item) for item in self.skipped],
        }


_HEALTH_RANK = {
    HealthStatus.GOOD: 0,
    HealthStatus.WARNING: 1,
    HealthStatus.UNKNOWN: 2,
    HealthStatus.INVALID: 3,
}


def summarize_project(
    entries: list[ProjectEntry] | tuple[ProjectEntry, ...],
    profile_name: str = "generic",
    *,
    project_name: str = "",
    n_source_positions: int = 1,
    skipped: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
) -> ProjectOverview:
    """The overview of ``entries`` (in project order) under ``profile_name``.

    ``skipped`` names the sessions the caller could not load, with the reason.
    """
    profile = get_profile(profile_name)
    sources = max(1, int(n_source_positions))
    summaries = [_summarize_session(entry, profile_name, profile) for entry in entries]
    by_label: dict[str, list[int]] = {}
    for index, entry in enumerate(entries):
        if entry.position:
            by_label.setdefault(entry.position, []).append(index)
    positions: list[PositionSummary] = []
    first: tuple[PositionSummary, ProjectEntry] | None = None
    for label, indexes in by_label.items():
        takes = tuple(summaries[i] for i in indexes)
        representative = _representative(takes)
        rep_entry = entries[indexes[representative]]
        spread, repeatable = _repeatability(takes)
        verdict: ComparisonVerdict | None = None
        if first is None:
            text = _("the first position: the others are judged against it")
        else:
            verdict, text = _against_first(first[1], rep_entry, profile_name, first[0].label)
        summary = PositionSummary(
            label=label,
            sessions=takes,
            representative=representative,
            repeat_spread_percent=spread,
            repeatable=repeatable,
            verdict=verdict,
            verdict_text=text,
        )
        positions.append(summary)
        if first is None:
            first = (summary, rep_entry)
    unlisted = tuple(summaries[i] for i, entry in enumerate(entries) if not entry.position)
    averaged = _averaged(entries, len(by_label), sources)
    spread_percent = _spatial_spread(positions)
    overview = ProjectOverview(
        name=project_name,
        profile=profile_name,
        positions=tuple(positions),
        unlisted=unlisted,
        averaged=averaged,
        n_source_positions=sources,
        spatial_spread_percent=spread_percent,
        locale=current_locale(),
        skipped=tuple(skipped),
    )
    return replace(overview, next_steps=tuple(_next_steps(overview, profile_name)))


# --- one take ------------------------------------------------------------------------


def _summarize_session(entry: ProjectEntry, profile_name: str, profile: object) -> SessionSummary:
    result = entry.result
    report = assess(result)
    problems = tuple(check.title for check in report.problems)
    broadband = result.decay.broadband
    clarity_metric: str | None = None
    clarity_db: float | None = None
    metric_name = getattr(profile, "clarity_metric", None)
    if metric_name in ("c50", "c80"):
        metric = getattr(broadband, metric_name)
        if metric.validity is Validity.VALID and metric.value is not None:
            clarity_metric = str(metric_name).upper()
            clarity_db = float(metric.value)
    window = float(getattr(profile, "strong_reflection_window_ms", 30.0))
    inside = [r for r in result.reflections.reflections if r.delay_ms <= window]
    strongest = max(inside, key=lambda r: r.relative_db, default=None)
    try:
        findings: list[Finding] = interpret(result, profile_name)
    except ReverbScopeError:
        # A third-party profile that fails leaves the take without findings.
        findings = []
    warnings = tuple(dict.fromkeys(f.topic for f in findings if f.severity is Severity.WARNING))
    notices = sum(1 for f in findings if f.severity is Severity.NOTICE)
    fit, reason = _fit(report.overall, problems, broadband.rt60_estimate_s, warnings, profile_name)
    return SessionSummary(
        directory=entry.directory,
        position=entry.position,
        created_at=entry.session.created_at,
        health=str(report.overall),
        health_problems=problems,
        rt60_s=broadband.rt60_estimate_s,
        rt60_basis=broadband.rt60_basis,
        clarity_metric=clarity_metric,
        clarity_db=clarity_db,
        noise_rms_dbfs=result.noise.rms_dbfs,
        noise_verified=result.noise.segment_source is not None
        and result.noise.rms_dbfs is not None,
        reflection_ms=None if strongest is None else strongest.delay_ms,
        reflection_db=None if strongest is None else strongest.relative_db,
        warnings=warnings,
        notices=notices,
        fit=fit,
        fit_reason=reason,
    )


def _fit(
    health: HealthStatus,
    problems: tuple[str, ...],
    rt60_s: float | None,
    warnings: tuple[str, ...],
    profile_name: str,
) -> tuple[Fit, str]:
    title = profile_title(profile_name)
    if health is HealthStatus.INVALID:
        return Fit.UNKNOWN, _("the measurement is invalid ({checks})").format(
            checks=list_join(problems)
        )
    if rt60_s is None:
        return Fit.UNKNOWN, _("no VALID reverberation time")
    if warnings:
        return Fit.WARNINGS, _("the {profile} profile warns about {topics}").format(
            profile=title, topics=list_join(topic_text(topic) for topic in warnings)
        )
    return Fit.FITS, _("no warning under the {profile} profile").format(profile=title)


# --- one position --------------------------------------------------------------------


def _representative(takes: tuple[SessionSummary, ...]) -> int:
    """The healthiest take, the latest among equals."""
    best = 0
    for index, take in enumerate(takes):
        current = takes[best]
        rank = _HEALTH_RANK.get(HealthStatus(take.health), 3)
        best_rank = _HEALTH_RANK.get(HealthStatus(current.health), 3)
        if rank < best_rank or (rank == best_rank and take.created_at >= current.created_at):
            best = index
    return best


def _repeatability(takes: tuple[SessionSummary, ...]) -> tuple[float | None, bool | None]:
    values = [take.rt60_s for take in takes if take.rt60_s is not None and take.rt60_s > 0.0]
    if len(values) < 2:
        return None, None
    spread = 100.0 * (max(values) - min(values)) / min(values)
    return spread, spread <= T_JND_PERCENT


def _against_first(
    first: ProjectEntry, entry: ProjectEntry, profile_name: str, first_label: str
) -> tuple[ComparisonVerdict | None, str]:
    from reverbscope.core.compare import compare

    try:
        comparison = compare(first.result, entry.result)
    except ReverbScopeError as exc:
        return None, _("not compared with position {label}: {error}").format(
            label=first_label, error=exc
        )
    verdict = judge_comparison(
        comparison, profile_name, baseline=first.result, candidate=entry.result
    )
    if verdict.count(Verdict.NOT_COMPARABLE) == len(verdict.aspects):
        reason = verdict.aspects[0].reason if verdict.aspects else ""
        return verdict, _("not comparable with position {label}: {reason}").format(
            label=first_label, reason=reason
        )
    return verdict, _("against position {label}: {headline}").format(
        label=first_label, headline=verdict.headline()
    )


# --- the room ------------------------------------------------------------------------


def _averaged(
    entries: list[ProjectEntry] | tuple[ProjectEntry, ...], n_positions: int, sources: int
) -> AveragedDecay | None:
    if not entries:
        return None
    labelled = [entry for entry in entries if entry.position]
    n_mic = max(1, n_positions)
    try:
        return average_decay(
            [entry.result for entry in entries],
            n_source_positions=sources,
            n_microphone_positions=n_mic,
            n_combinations=max(1, min(len(labelled) or 1, sources * n_mic)),
            session_labels=[entry.directory for entry in entries],
        )
    except ReverbScopeError:
        return None


def _spatial_spread(positions: list[PositionSummary]) -> float | None:
    values = [
        p.representative_session.rt60_s
        for p in positions
        if p.representative_session.rt60_s is not None and p.representative_session.rt60_s > 0.0
    ]
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return 100.0 * (max(values) - min(values)) / mean


def _next_steps(overview: ProjectOverview, profile_name: str) -> list[str]:
    steps: list[str] = []
    title = profile_title(profile_name)
    positions = overview.positions
    if not positions:
        steps.append(
            _(
                "No position yet: measure one from the Project page, or add a saved session "
                "with reverbscope project add <project> <session> --position <label>."
            )
        )
        return steps + _unlisted_step(overview)
    n_mic = len(positions)
    sources = overview.n_source_positions
    now = iso_3382_2_class(sources, n_mic)
    for more in range(1, 4):
        better = iso_3382_2_class(sources, n_mic + more)
        if _class_rank(better) > _class_rank(now):
            steps.append(
                _(
                    "{n} microphone position(s) reach the ISO 3382-2 {now} class; {more} more "
                    "(same source position and level) would reach {better}."
                ).format(
                    n=n_mic,
                    now=accuracy_class_text(now),
                    more=more,
                    better=accuracy_class_text(better),
                )
            )
            break
    else:
        # With one source the table stops at survey: say what the next class
        # takes, a second loudspeaker position and perhaps more microphones.
        for more in range(4):
            better = iso_3382_2_class(sources + 1, n_mic + more)
            if _class_rank(better) <= _class_rank(now):
                continue
            if more == 0:
                how = _(
                    "measure every position again with the loudspeaker elsewhere, and pass "
                    "--sources {sources}"
                ).format(sources=sources + 1)
            else:
                how = _(
                    "{more} more microphone position(s) ({total} in all), each measured with "
                    "the loudspeaker in both places; pass --sources {sources}"
                ).format(more=more, total=n_mic + more, sources=sources + 1)
            steps.append(
                _(
                    "{n} microphone position(s) reach the ISO 3382-2 {now} class; {better} "
                    "needs a second source position: {how}."
                ).format(
                    n=n_mic,
                    now=accuracy_class_text(now),
                    better=accuracy_class_text(better),
                    how=how,
                )
            )
            break
    single = [p.label for p in positions if len(p.sessions) == 1]
    if single:
        steps.append(
            _(
                "A second take at {labels} would show whether the measurement repeats "
                "(takes at one position should agree within {jnd:g} % in RT60)."
            ).format(labels=list_join(single), jnd=T_JND_PERCENT)
        )
    for position in positions:
        if position.repeatable is False and position.repeat_spread_percent is not None:
            steps.append(
                _(
                    "The takes at {label} differ by {spread:.0f} % in RT60, more than the "
                    "{jnd:g} % just-noticeable difference: check the microphone position, the "
                    "level and the noise before trusting either."
                ).format(
                    label=position.label, spread=position.repeat_spread_percent, jnd=T_JND_PERCENT
                )
            )
    for position in positions:
        take = position.representative_session
        if take.health == str(HealthStatus.INVALID):
            steps.append(
                _("Measure {label} again: {checks}.").format(
                    label=position.label, checks=list_join(take.health_problems)
                )
            )
    fitting = [p.label for p in overview.fitting]
    if not fitting:
        steps.append(
            _(
                "No position fits the {profile} profile yet: each take's findings say what "
                "to change (distance, treatment, level)."
            ).format(profile=title)
        )
    elif len(fitting) == 1:
        steps.append(
            _("{label} is the one position that fits the {profile} profile.").format(
                label=fitting[0], profile=title
            )
        )
    else:
        steps.append(
            _(
                "Positions that fit the {profile} profile: {labels}. The overview does not "
                "rank them: choose on the verdicts and on what the recording needs."
            ).format(profile=title, labels=list_join(fitting))
        )
    return steps + _unlisted_step(overview)


def _unlisted_step(overview: ProjectOverview) -> list[str]:
    if not overview.unlisted:
        return []
    return [
        _(
            "{n} session(s) in the project folder belong to no position; they enter the "
            "average but not the position counts (reverbscope project add … --position)."
        ).format(n=len(overview.unlisted))
    ]


_CLASS_RANK = {"below_survey": 0, "survey": 1, "engineering": 2, "precision": 3}


def _class_rank(name: str) -> int:
    return _CLASS_RANK.get(name, 0)


__all__ = [
    "Fit",
    "PositionSummary",
    "ProjectEntry",
    "ProjectOverview",
    "SessionSummary",
    "fit_word",
    "summarize_project",
]
