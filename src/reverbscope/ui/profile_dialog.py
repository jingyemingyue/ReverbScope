"""What a recording profile wants: the explanation behind the profile selector."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QVBoxLayout, QWidget

from reverbscope.i18n import _
from reverbscope.interpretation.explain import ProfileExplanation, explain_profile
from reverbscope.ui.widgets import label


class ProfileDialog(QDialog):
    """The title, the description, what the profile watches for, what it skips."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item: ProfileExplanation = explain_profile(name)
        self.setWindowTitle(_("{profile} profile").format(profile=self.item.title))
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(label(self.item.title, "title"))
        layout.addWidget(label(self.item.description, "subtitle", wrap=True))
        layout.addWidget(label(_("WHAT IT WATCHES FOR"), "section"))
        for line in self.item.wants:
            layout.addWidget(label(f"•  {line}", wrap=True))
        if self.item.skips:
            layout.addWidget(label(_("WHAT IT DOES NOT JUDGE"), "section"))
            for line in self.item.skips:
                layout.addWidget(label(f"•  {line}", wrap=True))
        layout.addWidget(
            label(
                _(
                    "Thresholds are engineering choices for this kind of recording, not a "
                    "grade; docs/MEASUREMENT_METHODOLOGY.md §8 lists them for every profile."
                ),
                "hint",
                wrap=True,
            )
        )
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(lambda _button: self.accept())
        layout.addWidget(buttons)


def show_profile_help(name: str, parent: QWidget | None = None) -> ProfileDialog:
    """Open the explanation of ``name`` beside ``parent``, without blocking."""
    dialog = ProfileDialog(name, parent)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.show()
    return dialog


def profile_of(combo: QComboBox) -> str:
    return str(combo.currentData() or "generic")
