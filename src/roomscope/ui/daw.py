"""Ask which DAW project Universal DAW Mode should follow."""

from __future__ import annotations

from roomscope.ui.qt import ensure_pyside6

ensure_pyside6()

from PySide6.QtWidgets import QInputDialog, QWidget

from roomscope.daw import SOURCE_DECLARED, DawProject
from roomscope.i18n import _
from roomscope.models.configuration import SUPPORTED_SAMPLE_RATES


def ask_daw_project(
    parent: QWidget | None, candidates: tuple[DawProject, ...], *, reason: str
) -> DawProject | None:
    """Ask which DAW to follow. Returns ``None`` if the user cancels.

    Does not pick a default. Several candidates are listed; none means the
    user types a name and a sample rate.
    """
    if reason == "several" and candidates:
        labels = [item.label() for item in candidates]
        chosen, accepted = QInputDialog.getItem(
            parent,
            _("Which DAW project should RoomScope follow?"),
            _(
                "More than one DAW project is in play. Choose one. "
                "The sweep sample rate will match it. RoomScope will not guess."
            ),
            labels,
            0,
            False,
        )
        if not accepted:
            return None
        for item in candidates:
            if item.label() == chosen:
                return item
        return None
    name, accepted = QInputDialog.getText(
        parent,
        _("Which DAW should RoomScope follow?"),
        _(
            "No DAW project was found. Type the DAW you are using. "
            "RoomScope will not guess a sample rate."
        ),
    )
    if not accepted or not name.strip():
        return None
    project, accepted = QInputDialog.getText(
        parent,
        _("Which project?"),
        _("Project title (optional). Needed when that DAW has more than one session open."),
    )
    if not accepted:
        return None
    rates = [str(rate) for rate in SUPPORTED_SAMPLE_RATES]
    rate_text, accepted = QInputDialog.getItem(
        parent,
        _("Project sample rate"),
        _("The sweep must be generated at this rate."),
        rates,
        0,
        False,
    )
    if not accepted:
        return None
    return DawProject(
        daw=name.strip(),
        sample_rate=int(rate_text),
        project=project.strip(),
        source=SOURCE_DECLARED,
    )
