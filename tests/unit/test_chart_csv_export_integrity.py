"""Chart CSV export must not truncate an existing file when the write fails."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.ui.plotkit import ChartPanel

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_a_failed_chart_csv_export_keeps_the_previous_file(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = "# previous export\ncurve,x,y\nold,1,2\n"
    path = tmp_path / "curves.csv"
    path.write_text(previous, encoding="utf-8")

    chart = ChartPanel(x_label="x", y_label="y", title="Integrity")
    chart.add_curve("A", [0.0, 1.0], [0.0, 1.0], color="#177e89")

    real_replace = __import__("os").replace

    def boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(OSError, match="disk full"):
        chart.export_csv(path)
    assert path.read_text(encoding="utf-8") == previous

    monkeypatch.setattr("os.replace", real_replace)
    chart.export_csv(path)
    text = path.read_text(encoding="utf-8")
    assert "ReverbScope Integrity" in text
    assert "curve,x,y" in text
    assert "old,1,2" not in text
    chart.dispose()
