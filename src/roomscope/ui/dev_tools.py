"""Diagnostic windows: audio-device inspector and environment report.

The inspector is in the Developer menu of the developer edition
(``roomscope.edition``): it lists every host API and device the backend sees,
probes the sample rates on request (nothing is played) and copies the
inventory as JSON. The environment report (``roomscope doctor``) is in the
Help menu of every edition, for bug and hardware reports.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from roomscope.audio.inventory import DeviceInventory, build_inventory
from roomscope.errors import RoomScopeError
from roomscope.i18n import N_, _, localize
from roomscope.ui.theme import apply_report_font
from roomscope.ui.widgets import label

#: Where the Environment Report sends the user (the issue-template chooser).
ISSUES_URL = "https://github.com/jingyemingyue/RoomScope/issues/new/choose"

COLUMNS = (
    "#",
    N_("Name"),
    N_("Host API"),
    N_("In"),
    N_("Out"),
    N_("Default rate"),
    N_("Record rates"),
    N_("Play rates"),
    N_("Latency low/high (ms)"),
    N_("Recommended"),
    N_("Notes"),
)


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value * 1000.0:.1f}"


class DeviceInspector(QDialog):
    """Every device of every host API, with probed rates and recommendations."""

    def __init__(self, backend_name: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Audio Device Inspector"))
        self.resize(1100, 560)
        self._backend_name = backend_name
        self.inventory: DeviceInventory | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(
            label(
                _(
                    "Every host API and device PortAudio reports. Probing asks each device "
                    "which sample rates it accepts for one channel; nothing is played. "
                    "See docs/AUDIO_DEVICES.md for what each host API does to the signal."
                ),
                "hint",
                wrap=True,
            )
        )
        row = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItem(_("All host APIs"), None)
        self.filter.currentIndexChanged.connect(self._fill)
        self.probe_button = QPushButton(_("Probe sample rates"))
        self.probe_button.clicked.connect(lambda: self.refresh(probe=True))
        self.copy_button = QPushButton(_("Copy as JSON"))
        self.copy_button.clicked.connect(self.copy_json)
        row.addWidget(self.filter)
        row.addStretch(1)
        row.addWidget(self.probe_button)
        row.addWidget(self.copy_button)
        layout.addLayout(row)
        self.summary = label("", "hint", wrap=True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([_(column) for column in COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.refresh(probe=False)

    def refresh(self, *, probe: bool) -> None:
        from roomscope.audio.backend import get_backend

        try:
            self.inventory = build_inventory(get_backend(self._backend_name), probe_rates=probe)
        except RoomScopeError as exc:
            self.inventory = None
            self.summary.setText(localize(str(exc)))
            self.table.setRowCount(0)
            return
        self.filter.blockSignals(True)
        current = self.filter.currentData()
        self.filter.clear()
        self.filter.addItem(_("All host APIs"), None)
        for api in self.inventory.host_apis:
            self.filter.addItem(f"{api.name} ({api.device_count})", api.name)
        index = self.filter.findData(current)
        self.filter.setCurrentIndex(max(index, 0))
        self.filter.blockSignals(False)
        apis = ", ".join(api.name for api in self.inventory.host_apis) or "-"
        self.summary.setText(
            _("Backend {backend}; {version}; host APIs: {apis}; {n} device(s).").format(
                backend=self.inventory.backend,
                version=self.inventory.portaudio_version or "-",
                apis=apis,
                n=len(self.inventory.devices),
            )
        )
        self._fill()

    def _fill(self) -> None:
        if self.inventory is None:
            return
        api = self.filter.currentData()
        probes = [p for p in self.inventory.devices if api is None or p.device.host_api == api]
        self.table.setRowCount(len(probes))
        probed = bool(self.inventory.rates_probed)
        for row, probe in enumerate(probes):
            d = probe.device
            recommended = []
            if probe.recommended_input:
                recommended.append(_("input"))
            if probe.recommended_output:
                recommended.append(_("output"))
            latency_in = (
                f"{_ms(d.default_low_input_latency_s)}/{_ms(d.default_high_input_latency_s)}"
            )
            latency_out = (
                f"{_ms(d.default_low_output_latency_s)}/{_ms(d.default_high_output_latency_s)}"
            )
            values = [
                str(d.index),
                d.name + (" *" if d.is_default_input or d.is_default_output else ""),
                d.host_api,
                str(d.max_input_channels),
                str(d.max_output_channels),
                f"{d.default_sample_rate:.0f}",
                ", ".join(str(r) for r in probe.input_rates)
                if probed or probe.input_rates
                else "…",
                ", ".join(str(r) for r in probe.output_rates)
                if probed or probe.output_rates
                else "…",
                _("in {input}, out {output}").format(input=latency_in, output=latency_out),
                " + ".join(recommended),
                "; ".join(localize(note) for note in probe.notes),
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == len(values) - 1:
                    item.setToolTip(text)
                self.table.setItem(row, column, item)

    def copy_json(self) -> None:
        if self.inventory is None:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(json.dumps(self.inventory.to_dict(), indent=1))


class EnvironmentReport(QDialog):
    """``roomscope doctor`` in a window: probe, copy, and where to report.

    Offered in every edition (Help menu): an installed user filing a bug needs
    it as much as a developer. Nothing is sent anywhere; the user copies the
    text into an issue.
    """

    def __init__(self, backend_name: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Environment Report"))
        self.resize(820, 580)
        self._backend_name = backend_name
        layout = QVBoxLayout(self)
        layout.addWidget(
            label(
                _(
                    "Paste this report into a GitHub issue so the problem can be reproduced. "
                    "Nothing is sent automatically. Probing asks each device which sample "
                    "rates it accepts; nothing is played. Device names can contain personal "
                    "names: review the text before posting."
                ),
                "hint",
                wrap=True,
            )
        )
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setProperty("report", True)
        apply_report_font(self.text)
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        self.probe_button = QPushButton(_("Probe sample rates"))
        self.probe_button.clicked.connect(lambda: self.refresh(probe=True))
        folder = QPushButton(_("Open Data Folder"))
        folder.setToolTip(_("The log file and settings are in this folder."))
        folder.clicked.connect(self._open_folder)
        issue = QPushButton(_("Open Issue Page"))
        issue.setToolTip(ISSUES_URL)
        issue.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ISSUES_URL)))
        copy = QPushButton(_("Copy"))
        copy.setProperty("primary", True)
        copy.clicked.connect(self._copy)
        row.addWidget(self.probe_button)
        row.addWidget(folder)
        row.addStretch(1)
        row.addWidget(issue)
        row.addWidget(copy)
        layout.addLayout(row)
        self.refresh(probe=False)

    def refresh(self, *, probe: bool) -> None:
        from roomscope.diagnostics import environment_report, format_environment_report

        report = environment_report(self._backend_name, probe_rates=probe)
        self.text.setPlainText(format_environment_report(report))

    def _open_folder(self) -> None:
        from roomscope.io.recent import roomscope_home

        home = roomscope_home()
        home.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(home)))

    def _copy(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.text.toPlainText())
