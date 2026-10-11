"""The measurement list model: position groups, the visibility checkbox,
the role tags, precise row updates and the two-way selection sync."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QApplication, QTreeView

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui.document import Measurement, WorkspaceDocument
from reverbscope.ui.measurement_model import (
    COLUMN_NAME,
    COLUMN_ROLE,
    MeasurementListModel,
    connect_selection,
    style_tree,
)
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def result(short_sweep: SweepSettings) -> AnalysisResult:
    take = synthetic_recording(
        short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)])
    )
    return analyze(take, Reference.from_settings(short_sweep))


def _measurement(result: AnalysisResult, position: str, *, path: Path | None = None) -> Measurement:
    session = MeasurementSession(room_name="Booth", measurement_position=position)
    return Measurement(session=session, result=result, path=path)


def _rows(model: MeasurementListModel) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    for row in range(model.rowCount(QModelIndex())):
        group = model.index(row, COLUMN_NAME, QModelIndex())
        names = [
            str(model.data(model.index(child, COLUMN_NAME, group)))
            for child in range(model.rowCount(group))
        ]
        out.append((str(model.data(group)), names))
    return out


def test_measurements_group_by_position(app: QApplication, result: AnalysisResult) -> None:
    document = WorkspaceDocument()
    model = MeasurementListModel(document)
    document.add(_measurement(result, "A"))
    document.add(_measurement(result, "B"))
    document.add(_measurement(result, "A"))
    assert _rows(model) == [("A", ["Booth / A", "Booth / A"]), ("B", ["Booth / B"])]
    assert model.headerData(COLUMN_NAME, Qt.Orientation.Horizontal) == "Measurement"


def test_the_checkbox_is_the_visibility_and_the_group_follows(
    app: QApplication, result: AnalysisResult
) -> None:
    document = WorkspaceDocument()
    model = MeasurementListModel(document)
    first = document.add(_measurement(result, "A"))
    second = document.add(_measurement(result, "A"))
    group = model.index(0, COLUMN_NAME, QModelIndex())
    assert model.data(group, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    changed: list[tuple[int, int]] = []
    model.dataChanged.connect(lambda a, b, *r: changed.append((a.row(), a.column())))
    document.set_visible(first, False)
    assert (
        model.data(model.index_for(first), Qt.ItemDataRole.CheckStateRole)
        == Qt.CheckState.Unchecked
    )
    assert model.data(group, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.PartiallyChecked
    assert changed, "the row and its group announce the change"
    # Checking through the model reaches the document; the selection stays.
    document.set_selected(second)
    assert model.setData(
        model.index_for(first), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole
    )
    assert document.is_visible(first) and document.selected_id() == second
    # A group checkbox hides every curve of the position.
    assert model.setData(group, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    assert not document.is_visible(first) and not document.is_visible(second)
    assert model.data(group, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked


def test_role_tags_and_tooltips(app: QApplication, result: AnalysisResult, tmp_path: Path) -> None:
    from reverbscope.demo import DEMO_MODE

    document = WorkspaceDocument()
    model = MeasurementListModel(document)
    saved = document.add(_measurement(result, "A", path=tmp_path / "a"))
    live = document.add(_measurement(result, "B"))
    synthetic = Measurement(
        session=MeasurementSession(mode=DEMO_MODE, room_name="Synthetic demo room"), result=result
    )
    synthetic_id = document.add(synthetic)
    role = lambda identifier: str(model.data(model.index_for(identifier, COLUMN_ROLE)))  # noqa: E731
    assert role(saved) == ""
    assert role(live) == "unsaved"
    assert "synthetic data" in role(synthetic_id) and "unsaved" in role(synthetic_id)
    document.set_baseline(saved)
    assert role(saved) == "baseline"
    document.set_baseline(None)
    assert role(saved) == ""
    tooltip = str(model.data(model.index_for(saved), Qt.ItemDataRole.ToolTipRole))
    assert str(tmp_path / "a") in tooltip
    assert "not saved" in str(model.data(model.index_for(live), Qt.ItemDataRole.ToolTipRole))
    # Saving drops the tag through measurement_changed.
    changed: list[int] = []
    model.dataChanged.connect(lambda a, b, *r: changed.append(a.row()))
    document.mark_saved(live, tmp_path / "b")
    assert role(live) == "" and changed
    swatch = model.data(model.index_for(saved), Qt.ItemDataRole.DecorationRole)
    assert swatch is not None and not swatch.isNull()


def test_removing_a_measurement_removes_its_row_and_an_emptied_group(
    app: QApplication, result: AnalysisResult
) -> None:
    document = WorkspaceDocument()
    model = MeasurementListModel(document)
    first = document.add(_measurement(result, "A"))
    second = document.add(_measurement(result, "B"))
    removed: list[tuple[bool, int]] = []
    model.rowsRemoved.connect(
        lambda parent, first_row, last: removed.append((parent.isValid(), first_row))
    )
    document.remove(second)
    assert _rows(model) == [("A", ["Booth / A"])]
    assert removed == [(True, 0), (False, 1)]
    document.remove(first)
    assert _rows(model) == [] and model.rowCount(QModelIndex()) == 0


def test_a_changed_position_moves_the_row_to_its_group(
    app: QApplication, result: AnalysisResult
) -> None:
    document = WorkspaceDocument()
    model = MeasurementListModel(document)
    identifier = document.add(_measurement(result, "A"))
    document.add(_measurement(result, "B"))
    measurement = document.get(identifier)
    assert measurement is not None
    measurement.position = "B"
    document.touch(identifier)
    assert _rows(model) == [("B", ["Booth / B", "Booth / B"])]
    assert model.index_for(identifier).parent().row() == 0


def test_the_view_and_the_document_select_each_other(
    app: QApplication, result: AnalysisResult
) -> None:
    document = WorkspaceDocument()
    model = MeasurementListModel(document)
    view = QTreeView()
    view.setModel(model)
    style_tree(view)
    sync = connect_selection(view, document)
    assert sync is not None
    first = document.add(_measurement(result, "A"))
    second = document.add(_measurement(result, "B"))
    view.show()
    app.processEvents()
    # The document's selection moves the view's current row...
    assert model.measurement_at(view.currentIndex()) is document.get(second)
    document.set_selected(first)
    assert model.measurement_at(view.currentIndex()) is document.get(first)
    # ...and the view's current row selects in the document.
    view.setCurrentIndex(model.index_for(second))
    assert document.selected_id() == second
    # A group row takes the focus but never the selection.
    view.setCurrentIndex(model.index(0, COLUMN_NAME, QModelIndex()))
    assert document.selected_id() == second
    assert view.selectionModel().isSelected(model.index_for(second))
    document.set_selected(None)
    assert not view.selectionModel().hasSelection()
    view.close()
