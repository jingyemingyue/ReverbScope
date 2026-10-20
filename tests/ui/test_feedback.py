"""Help ▸ Send Feedback / Report a Bug open a prefilled GitHub issue form.

The app only hands a URL to the system browser after a menu click; the form's
version and operating-system fields arrive filled in through its query
parameters, and the form exists in both languages with those field ids.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl, QUrlQuery
from PySide6.QtWidgets import QApplication

from reverbscope import __version__
from reverbscope.i18n import activate
from reverbscope.ui import feedback

pytestmark = pytest.mark.gui

ROOT = Path(__file__).resolve().parents[2]
FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _query(url: QUrl) -> dict[str, str]:
    items = QUrlQuery(url).queryItems(QUrl.ComponentFormattingOption.FullyDecoded)
    return dict(items)


def test_the_url_names_the_form_of_the_interface_language() -> None:
    fields = {"version": "0.5.0b4 (Python 3.12.3, Qt 6.11.2)", "os": "macOS-15.5 (arm64)"}
    english = feedback.issue_url("bug", "en", fields)
    chinese = feedback.issue_url("feedback", "zh_CN", fields)
    assert english.toString().startswith(feedback.NEW_ISSUE_URL + "?")
    assert _query(english) == {"template": "bug.yml", **fields}
    assert _query(chinese)["template"] == "feedback-zh-CN.yml"


def test_reserved_characters_survive_the_query_string() -> None:
    fields = {"version": "1.0+local & 50% = ok", "os": "Linux"}
    encoded = feedback.issue_url("bug", "en", fields).toString(
        QUrl.ComponentFormattingOption.FullyEncoded
    )
    # "+" would read as a space and "&" / "=" would split the field.
    assert "1.0%2Blocal%20%26%2050%25%20%3D%20ok" in encoded
    assert _query(QUrl(encoded))["version"] == fields["version"]


def test_the_prefilled_fields_name_the_app_python_and_qt() -> None:
    fields = feedback.environment_fields()
    assert set(fields) == {"version", "os"}
    assert fields["version"].startswith(__version__)
    assert "Python " in fields["version"] and "Qt " in fields["version"]
    assert fields["os"]


@pytest.mark.parametrize("stem", sorted(feedback.FORMS.values()))
@pytest.mark.parametrize("suffix", ["", "-zh-CN"])
def test_every_linked_form_exists_with_the_prefilled_ids(stem: str, suffix: str) -> None:
    yaml = pytest.importorskip("yaml")
    path = FORMS / f"{stem}{suffix}.yml"
    if not FORMS.is_dir():
        pytest.skip("issue forms are not part of this checkout (sdist)")
    form = yaml.safe_load(path.read_text(encoding="utf-8"))
    ids = {item.get("id") for item in form["body"]}
    assert {"version", "os"} <= ids


class _Desktop:
    """Stands in for QDesktopServices: records the URL instead of opening a browser."""

    def __init__(self, opened: list[QUrl]) -> None:
        self.opened = opened

    def openUrl(self, url: QUrl) -> bool:  # noqa: N802 - the Qt name
        self.opened.append(url)
        return True


def test_the_help_menu_opens_the_forms(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    from reverbscope.ui.main_window import MainWindow

    opened: list[QUrl] = []
    monkeypatch.setattr(feedback, "QDesktopServices", _Desktop(opened))
    window = MainWindow()
    try:
        window.feedback_action.trigger()
        window.bug_action.trigger()
        assert [_query(url)["template"] for url in opened] == ["feedback.yml", "bug.yml"]
        activate("zh_CN")
        window.bug_action.trigger()
        assert _query(opened[-1])["template"] == "bug-zh-CN.yml"
    finally:
        activate("en")
        window.close()
