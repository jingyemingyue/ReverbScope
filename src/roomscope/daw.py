"""Follow the DAW the user is actually using. Never guess which one.

RoomScope does not talk to a DAW host. This module only resolves a
:class:`DawProject` the caller already listed (tests and the fake path) or
that the user declared. On a machine with no DAW — including this VM —
:func:`open_daw_projects` is empty unless ``ROOMSCOPE_FAKE_DAWS`` is set.

The only session setting RoomScope already treats as DAW-dependent is the
**project sample rate**. The generated sweep must match it. Export bit depth
and time-stretch are user instructions, not values copied from a host.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass

from roomscope.errors import ConfigurationError
from roomscope.i18n import _, diag
from roomscope.models.configuration import SUPPORTED_SAMPLE_RATES, SweepSettings

#: Session settings that follow the chosen DAW project.
FOLLOWED_SETTINGS: tuple[str, ...] = ("sample_rate",)

#: Test / demo only. ``Name:rate`` or ``Name:rate:project``, separated by ``;``.
FAKE_DAWS_ENV = "ROOMSCOPE_FAKE_DAWS"

SOURCE_FAKE = "fake"
SOURCE_DECLARED = "declared"


class DawChoiceNeeded(ConfigurationError):  # noqa: N818 — a needed choice, not a crash
    """Zero or several DAW projects are in play; the user must choose."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        candidates: tuple[DawProject, ...] = (),
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.candidates = candidates


@dataclass(frozen=True)
class DawProject:
    """One DAW project the user can tell RoomScope to follow."""

    daw: str
    sample_rate: int
    project: str = ""
    source: str = SOURCE_DECLARED

    def __post_init__(self) -> None:
        if not self.daw.strip():
            raise ConfigurationError(_("DAW name is required"))
        if self.sample_rate not in SUPPORTED_SAMPLE_RATES:
            raise ConfigurationError(
                _("sample_rate {rate} is not supported; use one of {supported}").format(
                    rate=self.sample_rate, supported=SUPPORTED_SAMPLE_RATES
                )
            )

    def label(self) -> str:
        if self.project.strip():
            return f"{self.daw} — {self.project} ({self.sample_rate} Hz)"
        return f"{self.daw} ({self.sample_rate} Hz)"

    def matches(self, daw: str | None, project: str | None) -> bool:
        """Exact name match, ignoring letter case and extra spaces. No prefixes."""
        daw_ok = not daw or _norm(daw) == _norm(self.daw)
        project_ok = not project or _norm(project) == _norm(self.project)
        return daw_ok and project_ok

    def to_dict(self) -> dict[str, str | int]:
        return {
            "daw": self.daw,
            "project": self.project,
            "sample_rate": self.sample_rate,
            "source": self.source,
        }


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def parse_fake_daws(text: str) -> tuple[DawProject, ...]:
    """Parse ``ROOMSCOPE_FAKE_DAWS`` (``Name:rate`` or ``Name:rate:project``)."""
    found: list[DawProject] = []
    for raw in text.split(";"):
        item = raw.strip()
        if not item:
            continue
        name, sep, rest = item.partition(":")
        if not sep or not rest:
            raise ConfigurationError(
                _("fake DAW entry {item} must be Name:rate or Name:rate:project").format(item=item)
            )
        rate_text, _rate_sep, project = rest.partition(":")
        try:
            rate = int(rate_text)
        except ValueError as exc:
            raise ConfigurationError(
                _("fake DAW entry {item} has no sample rate").format(item=item)
            ) from exc
        found.append(
            DawProject(
                daw=name.strip(),
                sample_rate=rate,
                project=project.strip(),
                source=SOURCE_FAKE,
            )
        )
    return tuple(found)


def open_daw_projects(entries: Sequence[DawProject] | None = None) -> tuple[DawProject, ...]:
    """DAW projects in play.

    ``entries`` is for tests. Otherwise only ``ROOMSCOPE_FAKE_DAWS`` is read.
    Running hosts are not inspected; this VM has no DAW installed.
    """
    if entries is not None:
        return tuple(entries)
    return parse_fake_daws(os.environ.get(FAKE_DAWS_ENV, ""))


def apply_daw_follow(settings: SweepSettings, project: DawProject) -> SweepSettings:
    """Copy DAW-dependent settings from ``project`` onto the sweep."""
    return settings.with_sample_rate(project.sample_rate)


def resolve_daw_follow(
    candidates: Sequence[DawProject],
    *,
    daw: str | None = None,
    project: str | None = None,
    declared_rate: int | None = None,
) -> DawProject:
    """Pick the DAW project to follow, or raise :class:`DawChoiceNeeded`.

    * Several candidates and no unique ``daw`` / ``project`` → ask. No default.
    * No candidates → ask, unless the user declared both a DAW name and a rate.
    * One leftover candidate → follow it. A conflicting ``declared_rate`` is
      refused rather than overridden.
    """
    listed = tuple(candidates)
    daw_name = daw.strip() if daw and daw.strip() else None
    project_name = project.strip() if project and project.strip() else None
    matched = tuple(item for item in listed if item.matches(daw_name, project_name))

    if len(matched) == 1:
        chosen = matched[0]
        if declared_rate is not None and declared_rate != chosen.sample_rate:
            raise ConfigurationError(
                _(
                    "the chosen DAW project is {rate} Hz; --sample-rate {declared} Hz "
                    "does not match. RoomScope will not guess"
                ).format(rate=chosen.sample_rate, declared=declared_rate)
            )
        return chosen

    if not listed and daw_name and declared_rate is not None:
        return DawProject(
            daw=daw_name,
            sample_rate=declared_rate,
            project=project_name or "",
            source=SOURCE_DECLARED,
        )

    if not listed:
        raise DawChoiceNeeded(
            _none_message(),
            reason="none",
            candidates=(),
        )
    if len(matched) == 0:
        raise DawChoiceNeeded(
            _("none of the open DAW projects is {name}. RoomScope will not guess").format(
                name=daw_name or project_name
            ),
            reason="unknown",
            candidates=listed,
        )
    raise DawChoiceNeeded(
        _several_message(matched if daw_name or project_name else listed),
        reason="several",
        candidates=matched if daw_name or project_name else listed,
    )


def _none_message() -> str:
    return _(
        "No DAW project was found. This computer was not treated as running a DAW. "
        "Say which project RoomScope should follow (name and sample rate). "
        "The sweep sample rate must match that project. RoomScope will not guess."
    )


def _several_message(candidates: Sequence[DawProject]) -> str:
    lines = [
        _(
            "More than one DAW project is in play. Say which one RoomScope should "
            "follow; it will not guess. The sweep sample rate follows the chosen project."
        )
    ]
    for item in candidates:
        lines.append(f"  {item.label()}")
    lines.append(_("Use --daw NAME and, if that name is shared, --daw-project TITLE."))
    return "\n".join(lines)


def follow_note(project: DawProject) -> str:
    return diag(
        "following {label}; sweep sample rate matches that DAW project",
        label=project.label(),
    )
