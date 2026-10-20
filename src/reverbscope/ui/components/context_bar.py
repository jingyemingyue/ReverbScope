"""The current document and view, kept separate from task navigation.

In Analysis every view is a visible tab (not a drop-down), so all of them
can be found at a glance; the full title and its shortcut are in the
tooltip. The bar compacts itself rather than clipping: below the width its
content needs, the panel switches drop their text and keep their icons.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from reverbscope.i18n import _
from reverbscope.ui.components.icons import icon
from reverbscope.ui.design.tokens import CONTEXT_HEIGHT, SPACE
from reverbscope.ui.workspace import WorkspaceModel, entry_label

#: Views that open a new group of tabs (a thin rule is drawn before them).
_GROUP_STARTS = ("fr", "noise", "report")


def tab_label(view_id: str, title: str) -> str:
    """The short tab text of a view; the full title stays in the tooltip."""
    short = {
        "overview": _("Overview"),
        "fr": _("Frequency"),
        "etc": _("Time"),
        "decay": _("Decay"),
        "noise": _("Noise"),
        "spectrogram": _("Spectrogram"),
        "waterfall": _("Waterfall"),
        "report": _("Report"),
    }
    return short.get(view_id, title)


class ViewTabs(QWidget):
    """A row of checkable view tabs with the item API of a combo box.

    ``addItem``, ``findData``, ``itemData``, ``currentData``,
    ``setCurrentIndex`` and ``currentIndexChanged`` behave as on
    :class:`QComboBox`, so the workspace drives it the same way.
    """

    currentIndexChanged = Signal(int)  # noqa: N815 - Qt naming

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("viewtabs", True)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QToolButton] = []
        self._data: list[str] = []
        self._rules: list[QFrame] = []
        self._current = -1
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    # --- the combo-box API ------------------------------------------------------

    def addItem(self, text: str, data: str, tooltip: str = "") -> None:  # noqa: N802
        if data in _GROUP_STARTS and self._buttons:
            rule = QFrame()
            rule.setProperty("vrule", True)
            rule.setFixedSize(1, 16)
            self._row.addWidget(rule, 0, Qt.AlignmentFlag.AlignVCenter)
            self._rules.append(rule)
        button = QToolButton()
        button.setText(text)
        button.setCheckable(True)
        button.setProperty("viewtab", True)
        button.setAccessibleName(text)
        button.setToolTip(tooltip or text)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        index = len(self._buttons)
        button.clicked.connect(lambda _checked=False, row=index: self._clicked(row))
        self._group.addButton(button)
        self._row.addWidget(button)
        self._buttons.append(button)
        self._data.append(data)

    def clear(self) -> None:
        for button in self._buttons:
            self._group.removeButton(button)
        for widget in (*self._buttons, *self._rules):
            self._row.removeWidget(widget)
            widget.deleteLater()
        self._buttons, self._data, self._rules = [], [], []
        self._current = -1

    def count(self) -> int:
        return len(self._buttons)

    def findData(self, data: object) -> int:  # noqa: N802
        return self._data.index(data) if data in self._data else -1

    def itemData(self, index: int) -> str | None:  # noqa: N802
        return self._data[index] if 0 <= index < len(self._data) else None

    def itemText(self, index: int) -> str:  # noqa: N802
        return self._buttons[index].text() if 0 <= index < len(self._buttons) else ""

    def currentIndex(self) -> int:  # noqa: N802
        return self._current

    def currentData(self) -> str | None:  # noqa: N802
        return self.itemData(self._current)

    def button(self, index: int) -> QToolButton:
        return self._buttons[index]

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        index = index if 0 <= index < len(self._buttons) else -1
        self._group.setExclusive(index >= 0)
        for row, button in enumerate(self._buttons):
            button.setChecked(row == index)
        self._group.setExclusive(True)
        if index != self._current:
            self._current = index
            self.currentIndexChanged.emit(index)

    def _clicked(self, row: int) -> None:
        self.setCurrentIndex(row)


class ContextBar(QWidget):
    entry_chosen = Signal(str)

    def __init__(self, model: WorkspaceModel) -> None:
        super().__init__()
        self.model = model
        self.setProperty("contextbar", True)
        self.setMinimumHeight(CONTEXT_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE, 0, 2 * SPACE, 0)
        layout.setSpacing(SPACE)
        self.view = ViewTabs()
        self.view.setAccessibleName(_("Analysis view"))
        layout.addWidget(self.view)
        self.title = QLabel(_("Project"))
        self.title.setProperty("role", "page-title")
        layout.addSpacing(SPACE)
        layout.addWidget(self.title)
        self.measurement_controls = QWidget()
        self.measurement_layout = QHBoxLayout(self.measurement_controls)
        self.measurement_layout.setContentsMargins(SPACE, 0, 0, 0)
        self.measurement_layout.setSpacing(SPACE)
        self.measurement_controls.hide()
        layout.addWidget(self.measurement_controls)
        layout.addStretch()
        # The data is synthetic: said in words on every task, never only by colour.
        self.synthetic = QLabel(_("Synthetic demo data"))
        self.synthetic.setProperty("role", "tag")
        self.synthetic.setToolTip(_("Simulated by the demo, not measured in a real room."))
        self.synthetic.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.synthetic.hide()
        layout.addWidget(self.synthetic, 0, Qt.AlignmentFlag.AlignVCenter)
        self.documents = QComboBox()
        self.documents.setAccessibleName(_("Current measurement"))
        self.documents.setToolTip(_("Current measurement"))
        self.documents.setMinimumContentsLength(10)
        self.documents.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.documents.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.documents.currentIndexChanged.connect(self._selected)
        layout.addWidget(self.documents)
        self.list_button = self._panel_switch(_("Measurements"), _("Measurement list"), "list")
        layout.addWidget(self.list_button)
        self.details_button = self._panel_switch(
            _("Properties"), _("Measurement properties"), "properties"
        )
        layout.addWidget(self.details_button)
        self._compact = False
        for signal in (model.entries_changed, model.current_changed, model.entry_updated):
            signal.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _panel_switch(text: str, name: str, glyph: str) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setIcon(icon(glyph, accent=True))
        button.setIconSize(QSize(16, 16))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setCheckable(True)
        button.setAccessibleName(name)
        button.setToolTip(name)
        button.setProperty("panelswitch", True)
        return button

    def restyle(self) -> None:
        self.list_button.setIcon(icon("list", accent=True))
        self.details_button.setIcon(icon("properties", accent=True))

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
        self._fit()

    def _selected(self, index: int) -> None:
        key = self.documents.itemData(index)
        if isinstance(key, str) and key:
            self.entry_chosen.emit(key)

    def set_analysis(self, analysis: bool) -> None:
        self.view.setVisible(analysis)
        self.title.setVisible(not analysis)
        for widget in (self.documents, self.list_button, self.details_button):
            widget.setVisible(analysis)
        self._fit()

    # --- no clipping --------------------------------------------------------------

    def is_compact(self) -> bool:
        return self._compact

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._fit()

    def _set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        style = (
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if compact
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        for button in (self.list_button, self.details_button):
            button.setToolButtonStyle(style)
        self.synthetic.setText(_("Synthetic") if compact else _("Synthetic demo data"))

    def _fit(self) -> None:
        """Drop the switch labels when the full bar would not fit in the width."""
        if self.width() <= 0:
            return
        self._set_compact(False)
        layout = self.layout()
        assert layout is not None
        needed = layout.minimumSize().width()
        self._set_compact(needed > self.width())
