"""Reusable session list used on Home and on the Compare page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _, localize


def _when(created_at: str) -> str:
    """``2026-09-24 17:13`` in local time from an ISO timestamp (as stored if unparsable)."""
    from datetime import datetime

    try:
        moment = datetime.fromisoformat(created_at)
        if moment.tzinfo is not None:
            # Windows' localtime refuses dates before 1970 or far in the future.
            moment = moment.astimezone()
        return moment.strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return str(created_at)


class SessionBrowser(QWidget):
    """List recent sessions or the contents of a folder."""

    open_session = Signal(str)
    selection_changed = Signal()

    def __init__(self, parent: QWidget | None = None, *, multi_select: bool = False) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        browse = QPushButton(_("Browse Folder..."))
        browse.clicked.connect(self._browse_folder)
        recent = QPushButton(_("Recent"))
        recent.clicked.connect(self.refresh_recent)
        row.addStretch(1)
        row.addWidget(recent)
        row.addWidget(browse)
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setMinimumHeight(120)
        if multi_select:
            self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.itemActivated.connect(self._open_listed)
        self.list.itemSelectionChanged.connect(self.selection_changed.emit)
        layout.addWidget(self.list, 1)
        self.refresh_recent()

    def selected_paths(self) -> list[Path]:
        paths: list[Path] = []
        for item in self.list.selectedItems():
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                paths.append(Path(str(data)))
        return paths

    def refresh_recent(self) -> None:
        from reverbscope.io.recent import recent_session_paths
        from reverbscope.io.session_store import load_session

        self.list.clear()
        for path in recent_session_paths():
            try:
                session = load_session(path)
            except ReverbScopeError:
                label = str(path)
            else:
                room = session.room_name or _("(unnamed room)")
                details = [
                    part
                    for part in (session.measurement_position, _when(session.created_at))
                    if part
                ]
                label = f"{room}   ·   {'   ·   '.join(details)}\n{path}"
            item = QListWidgetItem(label)
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.list.addItem(item)
        if self.list.count() == 0:
            empty = QListWidgetItem(_("No recent sessions yet. Save a measurement to see it here."))
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)

    def list_folder(self, root: Path) -> None:
        from reverbscope.io.project_store import is_project, list_project_sessions
        from reverbscope.io.session_store import list_sessions

        self.list.clear()
        if is_project(root):
            try:
                entries = list_project_sessions(root)
            except ReverbScopeError as exc:
                QMessageBox.warning(self, _("Cannot list sessions"), localize(str(exc)))
                self.refresh_recent()
                return
            for label, path in entries:
                prefix = f"{label}  —  " if label else ""
                item = QListWidgetItem(f"{prefix}{path}")
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self.list.addItem(item)
            if self.list.count() == 0:
                empty = QListWidgetItem(_("No sessions in this project"))
                empty.setFlags(Qt.ItemFlag.NoItemFlags)
                self.list.addItem(empty)
            return
        try:
            listings = list_sessions(root)
        except ReverbScopeError as exc:
            QMessageBox.warning(self, _("Cannot list sessions"), localize(str(exc)))
            self.refresh_recent()
            return
        for listing in listings:
            item = QListWidgetItem(f"{listing.label}  —  {listing.path}")
            item.setData(Qt.ItemDataRole.UserRole, str(listing.path))
            self.list.addItem(item)
        if self.list.count() == 0:
            empty = QListWidgetItem(_("No session.json files under {root}").format(root=root))
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)

    def _browse_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, _("Choose a folder of sessions"))
        if directory:
            self.list_folder(Path(directory))

    def _open_listed(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.open_session.emit(str(path))
