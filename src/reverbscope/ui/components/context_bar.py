"""The current document and view, kept separate from task navigation."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from reverbscope.i18n import _
from reverbscope.ui.design.tokens import CONTEXT_HEIGHT, SPACE
from reverbscope.ui.workspace import WorkspaceModel, entry_label


class ContextBar(QWidget):
    entry_chosen = Signal(str)

    def __init__(self, model: WorkspaceModel) -> None:
        super().__init__()
        self.model = model
        self.setProperty("contextbar", True)
        self.setMinimumHeight(CONTEXT_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2 * SPACE, SPACE, 2 * SPACE, SPACE)
        layout.setSpacing(2 * SPACE)
        self.view = QComboBox()
        self.view.setAccessibleName(_("Analysis view"))
        self.view.setMinimumContentsLength(12)
        layout.addWidget(self.view)
        self.title = QLabel(_("Project"))
        self.title.setProperty("role", "page-title")
        layout.addWidget(self.title)
        self.measurement_controls = QWidget()
        self.measurement_layout = QHBoxLayout(self.measurement_controls)
        self.measurement_layout.setContentsMargins(0, 0, 0, 0)
        self.measurement_controls.hide()
        layout.addWidget(self.measurement_controls)
        layout.addStretch()
        self.synthetic = QLabel(_("Synthetic demo data"))
        self.synthetic.setProperty("role", "hint")
        self.synthetic.hide()
        layout.addWidget(self.synthetic)
        self.documents = QComboBox()
        self.documents.setAccessibleName(_("Current measurement"))
        self.documents.setMinimumContentsLength(15)
        self.documents.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.documents.currentIndexChanged.connect(self._selected)
        layout.addWidget(self.documents)
        self.list_button = QToolButton()
        self.list_button.setText(_("Measurements"))
        self.list_button.setCheckable(True)
        self.list_button.setAccessibleName(_("Measurement list"))
        layout.addWidget(self.list_button)
        self.details_button = QToolButton()
        self.details_button.setText(_("Properties"))
        self.details_button.setCheckable(True)
        self.details_button.setAccessibleName(_("Measurement properties"))
        layout.addWidget(self.details_button)
        for signal in (model.entries_changed, model.current_changed, model.entry_updated):
            signal.connect(self.refresh)
        self.refresh()

    def refresh(self, *_args: object) -> None:
        self.documents.blockSignals(True)
        self.documents.clear()
        for entry in self.model.entries():
            self.documents.addItem(entry_label(entry), entry.key)
        index = self.documents.findData(self.model.current_key)
        self.documents.setCurrentIndex(index)
        self.documents.setEnabled(self.documents.count() > 0)
        self.documents.blockSignals(False)
        current = self.model.current()
        self.synthetic.setVisible(current is not None and current.synthetic)

    def _selected(self, index: int) -> None:
        key = self.documents.itemData(index)
        if isinstance(key, str) and key:
            self.entry_chosen.emit(key)

    def set_analysis(self, analysis: bool) -> None:
        self.view.setVisible(analysis)
        self.title.setVisible(not analysis)
        for widget in (self.documents, self.list_button, self.details_button):
            widget.setVisible(analysis)
