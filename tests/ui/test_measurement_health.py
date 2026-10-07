"""Results display actionable health in both languages, with no green invalid chip."""

from dataclasses import replace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from reverbscope.i18n import activate
from reverbscope.models.result import ClippingCheck
from reverbscope.ui.results import _Overview
from reverbscope.ui.theme import tone_color
from tests.health_fixtures import healthy_result

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_results_health_shows_problem_why_and_fix(app: QApplication, lang: str) -> None:
    activate(lang)
    overview = _Overview()
    result = replace(healthy_result(), clipping=ClippingCheck(0.0, 2, 8, True))
    overview.show_result(result, [], "generic")
    panel = overview.health
    texts = "\n".join(w.text() for w in panel.findChildren(QLabel))
    assert ("Measurement Health" if lang == "en" else "测量健康") in texts
    assert ("Why" if lang == "en" else "为什么") in texts
    assert ("Next step" if lang == "en" else "下一步") in texts
    assert ("preamp gain" if lang == "en" else "话放增益") in texts
    assert panel.status.property("tone") == "bad"
    assert len(panel.cards) == 1
    assert panel.cards[0].property("healthCode") == "recording.clipping"
    assert panel.cards[0].property("tone") == "bad"
    overview.close()


def test_refresh_replaces_health_findings_and_truncated_reflections_are_not_green(
    app: QApplication,
) -> None:
    overview = _Overview()
    result = healthy_result()
    truncated = replace(
        result,
        reflections=replace(
            result.reflections, window_truncated=True, analysed_window_ms=(0.5, 30.0)
        ),
    )
    overview.show_result(truncated, [], "generic")
    assert overview.health.status.property("tone") == "warn"
    assert tone_color("warn")[0] in overview.reflections.chip.styleSheet()
    assert "clean" not in overview.reflections.chip.text().lower()
    overview.show_result(result, [], "generic")
    assert overview.health.status.property("tone") == "good"
    assert overview.health.cards == []
    overview.close()


def test_invalid_take_does_not_overwrite_a_missing_metric_validity(app: QApplication) -> None:
    from reverbscope.models.result import Validity

    result = healthy_result()
    band = replace(
        result.decay.broadband,
        rt60_estimate_s=None,
        rt60_basis=None,
        t30=replace(result.decay.broadband.t30, seconds=None, validity=Validity.INSUFFICIENT_RANGE),
    )
    result = replace(
        result, clipping=ClippingCheck(0.0, 2, 8, True), decay=replace(result.decay, broadband=band)
    )
    overview = _Overview()
    overview.show_result(result, [], "generic")
    assert overview.health.status.property("tone") == "bad"
    assert overview.rt60.value.text() == "-"
    assert overview.rt60.chip.text() == "insufficient range"
    overview.close()


def test_health_evidence_is_plain_text_not_html(app: QApplication) -> None:
    overview = _Overview()
    result = replace(healthy_result(), warnings=("<b>warning from an older analyzer</b>",))
    overview.show_result(result, [], "generic")
    evidence = overview.health.cards[0].evidence
    assert evidence.textFormat() == Qt.TextFormat.PlainText
    assert "<b>" in evidence.text()
    overview.close()
