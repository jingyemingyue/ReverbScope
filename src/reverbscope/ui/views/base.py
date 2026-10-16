"""The base of every analysis view: draw from the model, and only while visible."""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import QWidget

from reverbscope.ui.workspace import WorkspaceModel


class AnalysisView(QWidget):
    """A view of the workspace model.

    Subclasses set :attr:`view_id`, implement :meth:`title` and
    :meth:`redraw`, and call :meth:`refresh` whenever what they show may have
    changed. ``refresh`` draws at once while the view is visible; while it is
    hidden it only marks the view dirty, and the next ``showEvent`` draws it.
    Ten hidden charts no longer redraw at every selection change.
    """

    view_id = ""

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self._dirty = True
        self.setProperty("page", True)

    def title(self) -> str:
        raise NotImplementedError

    def redraw(self) -> None:
        raise NotImplementedError

    def refresh(self) -> None:
        if self.isVisible():
            self._dirty = False
            self.redraw()
        else:
            self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    def restyle(self) -> None:
        """Draw again in the colour scheme now in force."""
        self.refresh()

    def shutdown(self) -> None:
        """Stop and wait for any worker thread this view started (window closing)."""

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        if self._dirty:
            self._dirty = False
            self.redraw()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
        # Only a view shown as a window of its own (tests, the benchmark) gets
        # here; inside the main window the window disposes the charts.
        if self.isWindow():
            from reverbscope.ui.plotkit import dispose_charts

            dispose_charts(self)
        super().closeEvent(event)
