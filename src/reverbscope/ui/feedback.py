"""Help ▸ Send Feedback / Report a Bug: open a GitHub issue form in the browser.

Nothing is sent by the app. The form opens in the system browser through
``QDesktopServices`` only when the user picks the menu item (GUIDELINES §4
C5); the version, Python, Qt and operating-system fields are filled in through
the issue form's URL query parameters, and the user sees and edits every
field before deciding to submit anything.
"""

from __future__ import annotations

import platform
from collections.abc import Callable

from PySide6.QtCore import QUrl, QUrlQuery, qVersion
from PySide6.QtGui import QDesktopServices

from reverbscope import __version__
from reverbscope.i18n import current_locale

#: The repository's issue forms (``.github/ISSUE_TEMPLATE``).
NEW_ISSUE_URL = "https://github.com/jingyemingyue/ReverbScope/issues/new"
#: Issue-form stems per kind; the Simplified Chinese form adds ``-zh-CN``.
FORMS = {"bug": "bug", "feedback": "feedback"}


def environment_fields() -> dict[str, str]:
    """The issue-form fields the app can fill in without asking.

    ``version`` carries the Python and Qt versions as well, because the bug
    form has no separate field for them. Paths, device names and settings
    are deliberately left out: they belong in the reviewed Environment Report.
    """
    try:
        import PySide6

        pyside = f", PySide6 {PySide6.__version__}"
    except (ImportError, AttributeError):  # pragma: no cover - PySide6 is imported above
        pyside = ""
    version = f"{__version__} (Python {platform.python_version()}, Qt {qVersion()}{pyside})"
    system = platform.platform(terse=True)
    machine = platform.machine()
    return {"version": version, "os": f"{system} ({machine})" if machine else system}


def issue_url(kind: str, locale: str = "en", fields: dict[str, str] | None = None) -> QUrl:
    """The ``issues/new`` URL of the ``kind`` form in the interface language."""
    stem = FORMS[kind] + ("-zh-CN" if locale.startswith("zh") else "")
    query = QUrlQuery()
    query.addQueryItem("template", f"{stem}.yml")
    for key, value in (environment_fields() if fields is None else fields).items():
        # QUrlQuery reads "%XX" as already encoded and leaves "+" alone, which
        # a query string reads as a space: encode both before adding.
        query.addQueryItem(key, value.replace("%", "%25").replace("+", "%2B"))
    url = QUrl(NEW_ISSUE_URL)
    url.setQuery(query)
    return url


def issue_form_opener(kind: str) -> Callable[[], None]:
    """What a Help-menu action runs: open the ``kind`` form for the current language.

    It holds no reference to the window, so the menu action does not keep a
    closed window alive.
    """

    def open_form() -> None:
        QDesktopServices.openUrl(issue_url(kind, current_locale()))

    return open_form
