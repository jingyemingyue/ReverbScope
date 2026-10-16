"""Exact visible chart ranges, entered in axis units rather than log coordinates."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import _


class AxisRangesDialog(QDialog):
    def __init__(
        self,
        x_label: str,
        y_label: str,
        x_range: tuple[float, ...],
        y_range: tuple[float, ...],
        *,
        x_frequency: bool = False,
        y_frequency: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Axis ranges"))
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.addWidget(QLabel(_("Lower limit")), 0, 1)
        grid.addWidget(QLabel(_("Upper limit")), 0, 2)
        self.fields: list[tuple[QDoubleSpinBox, QDoubleSpinBox]] = []
        for row, (label, limits, frequency) in enumerate(
            ((x_label, x_range, x_frequency), (y_label, y_range, y_frequency)), start=1
        ):
            grid.addWidget(QLabel(label), row, 0)
            fields = (QDoubleSpinBox(), QDoubleSpinBox())
            for column, (field, value) in enumerate(zip(fields, limits, strict=True), start=1):
                field.setDecimals(6)
                field.setRange(0.000001 if frequency else -1e12, 1e12)
                field.setValue(value)
                field.setKeyboardTracking(False)
                field.setMinimumWidth(130)
                field.valueChanged.connect(self._validate)
                grid.addWidget(field, row, column)
            self.fields.append(fields)
        layout.addLayout(grid)
        self.error = QLabel(_("Each lower limit must be below its upper limit."))
        self.error.setWordWrap(True)
        self.error.setProperty("role", "hint")
        layout.addWidget(self.error)
        self.buttons = QDialogButtonBox()
        self.apply_button = self.buttons.addButton(
            _("Apply"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.buttons.addButton(_("Cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._validate()

    def ranges(self) -> tuple[tuple[float, float], tuple[float, float]]:
        x, y = self.fields
        return (x[0].value(), x[1].value()), (y[0].value(), y[1].value())

    def _validate(self) -> None:
        if not hasattr(self, "buttons"):
            return
        valid = all(low.value() < high.value() for low, high in self.fields)
        self.apply_button.setEnabled(valid)
        self.error.setVisible(not valid)

    def accept(self) -> None:
        self._validate()
        if self.apply_button.isEnabled():
            super().accept()
