"""The inspector: what the workbench knows about the selected measurement.

Six tabs under one compact header: the measurement quality (the health
checks), the diagnostics (the recording profile's findings), the properties,
the data tables, the comparison with the baseline, and the text report.
Nothing here computes or judges a number: the rows come from
:mod:`reverbscope.ui.results_presenter`, the health report, the findings,
the comparison and its verdict; the panel lays them out and says which chart
a row belongs to (:attr:`InspectorPanel.locate_requested`), so the window
can show that chart and highlight the band, resonance or reflection.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from reverbscope.cli.render import (
    REFLECTIONS_NOT_COMPARED,
    REPORT_CONSOLE,
    RESONANCES_NARROWED,
    RESONANCES_NOT_COMPARED,
    created_text,
    render_analysis,
)
from reverbscope.demo import localize_demo_name
from reverbscope.health import HealthCheck, HealthReport, affects_text, status_word
from reverbscope.i18n import _, list_join, localize
from reverbscope.interpretation import Finding
from reverbscope.interpretation.profiles import profile_title
from reverbscope.interpretation.verdicts import ComparisonVerdict, verdict_chip
from reverbscope.labels import (
    metric_label,
    severity_text,
    signed_number,
    status_text,
    topic_text,
    validity_word,
)
from reverbscope.models.comparison import ComparisonResult, ResonanceMatch
from reverbscope.models.result import AnalysisResult
from reverbscope.ui.document import Measurement
from reverbscope.ui.plots import decay_table_rows, energy_table_rows
from reverbscope.ui.results_presenter import (
    GROUP_DECAY,
    GROUP_FREQUENCY,
    GROUP_IMPULSE,
    GROUP_NOISE,
    GROUP_PLACEMENT,
    HEALTH_TONE,
    band_detail_rows,
    candidate_detail_rows,
    candidate_rows,
    check_group,
    check_rows,
    evidence_rows,
    finding_group,
    finding_rows,
    health_summary,
    impulse_detail_rows,
    noise_band_rows,
    noise_detail_rows,
    placement_length_rows,
    placement_notes,
    placement_summary,
    ranked_checks,
    ranked_findings,
    reflection_rows,
    resonance_detail_rows,
    resonance_note,
    resonance_rows,
)
from reverbscope.ui.theme import apply_report_font, tokens, tone_color
from reverbscope.ui.widgets import SEVERITY_TONE, Chip, KeyValueList, flat, label

#: The plot kinds of the impulse group's two charts (``results_presenter``
#: keeps one group, :data:`GROUP_IMPULSE`, for both). A reflection row of the
#: Tables tab points at the reflections chart; a check or a finding of the
#: group is emitted with the group key itself, ``"impulse"``.
KIND_IMPULSE = GROUP_IMPULSE
KIND_REFLECTIONS = "reflections"

#: The tables of the Tables tab, in menu order: key and title.
#: The inspector's tabs, in order, by key.
TAB_KEYS = ("quality", "diagnostics", "properties", "tables", "comparison", "report")
TABLE_KEYS = (
    "decay",
    "energy",
    "noise",
    "reflections",
    "resonances",
    "placement_lengths",
    "candidates",
)
#: Which table an item name of a chart (``PlotPanel.item_selected``) or a
#: plot kind key selects.
_ITEM_TABLE = {
    "band": "decay",
    "resonance": "resonances",
    "reflection": "reflections",
    "candidate": "candidates",
    GROUP_FREQUENCY: "resonances",
    GROUP_DECAY: "decay",
    GROUP_NOISE: "noise",
    KIND_IMPULSE: "reflections",
    KIND_REFLECTIONS: "reflections",
    GROUP_PLACEMENT: "candidates",
}


def quality_chip_text(measurement: Measurement | None) -> tuple[str, str]:
    """The toolbar chip of a measurement: the overall health word and its tone;
    empty with the neutral tone when nothing is selected."""
    if measurement is None:
        return "", "neutral"
    return status_word(measurement.status), HEALTH_TONE[measurement.status]


def _table_title(key: str) -> str:
    return {
        "decay": _("Decay (EDT/T20/T30/RT60)"),
        "energy": _("Energy (C50/C80/D50/Ts)"),
        "noise": _("Noise bands"),
        "reflections": _("Reflections"),
        "resonances": _("Resonances"),
        "placement_lengths": _("Placement lengths"),
        "candidates": _("Placement candidates"),
    }.get(key, key)


def _table_columns(key: str) -> list[str]:
    return {
        "decay": [_("Band"), "EDT", "T20", "T30", _("RT60 estimate")],
        "energy": [_("Band"), "C50", "C80", "D50", _("Centre time")],
        "noise": [_("Band"), _("Level (dBFS)")],
        "reflections": [_("Delay (ms)"), _("Level re direct (dB)")],
        "resonances": [
            _("Frequency (Hz)"),
            _("Above baseline (dB)"),
            _("Decay 20 dB"),
            _("Distinguishable"),
        ],
        "placement_lengths": [_("Figure"), _("Value"), _("Validity"), _("Note")],
        "candidates": [
            _("Delay (ms)"),
            _("Level re direct (dB)"),
            _("Excess path (m)"),
            _("Surface"),
            _("Plane"),
        ],
    }.get(key, [])


def _mode_text(measurement: Measurement) -> str:
    if measurement.synthetic:
        return _("synthetic data")
    mode = measurement.session.mode
    return {
        "universal_daw": _("Universal DAW Mode"),
        "standalone": _("Standalone Mode"),
    }.get(mode, mode)


def _channels_text(measurement: Measurement) -> str:
    """The channels of the take as the command line names them: the
    interface's 1-based channels of a Standalone take, or the analysed
    column of an imported file."""
    session = measurement.session
    parts: list[str] = []
    if session.input_channel is not None:
        parts.append(_("input {channels}").format(channels=session.input_channel))
        if session.loopback_channel is not None:
            parts.append(_("loopback on input {channel}").format(channel=session.loopback_channel))
        if session.output_channel is not None:
            parts.append(_("output {channel}").format(channel=session.output_channel))
        return list_join(parts)
    analysis = session.analysis_settings
    if analysis.channel is not None:
        parts.append(_("input {channels}").format(channels=analysis.channel + 1))
    if analysis.loopback_channel is not None:
        parts.append(_("loopback on input {channel}").format(channel=analysis.loopback_channel + 1))
    return list_join(parts) if parts else _("not available")


def property_rows(measurement: Measurement) -> list[tuple[str, str]]:
    """The Properties tab: what the session and the result say about the take."""
    session = measurement.session
    result = measurement.result
    sweep = session.sweep_settings
    microphone = localize_demo_name(session.mode, session.microphone_name).strip()
    if session.microphone_type:
        microphone = (
            f"{microphone} ({session.microphone_type})" if microphone else session.microphone_type
        )
    rows = [
        (_("Room"), localize_demo_name(session.mode, session.room_name).strip() or "-"),
        (_("Position"), localize_demo_name(session.mode, measurement.position).strip() or "-"),
        (_("Microphone"), microphone or "-"),
        (_("Mode"), _mode_text(measurement)),
        (_("Recording profile"), profile_title(measurement.profile)),
        (_("Sample rate"), f"{result.sample_rate} Hz"),
        (
            _("Sweep"),
            _("{duration:g} s, {level:g} dBFS").format(
                duration=sweep.duration_s, level=sweep.level_dbfs
            ),
        ),
        (_("Channels"), _channels_text(measurement)),
        (_("Created"), created_text(session.created_at)),
        (
            _("Saved path"),
            str(measurement.path) if measurement.path is not None else _("not saved"),
        ),
    ]
    if measurement.recording_path is not None:
        rows.append((_("Recording"), str(measurement.recording_path)))
    if session.notes.strip():
        rows.append((_("Notes"), session.notes.strip()))
    return rows


# --- models ---------------------------------------------------------------------------


class ChecksModel(QAbstractTableModel):
    """The health checks of a report, the problems first (worst first), then
    the good ones. Columns: status, check, reason, affects; the tooltip is
    what to do about it."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._checks: list[HealthCheck] = []

    def set_report(self, report: HealthReport | None) -> None:
        self.beginResetModel()
        self._checks = [] if report is None else [*ranked_checks(report), *report.good]
        self.endResetModel()

    def check_at(self, row: int) -> HealthCheck | None:
        return self._checks[row] if 0 <= row < len(self._checks) else None

    def group_at(self, row: int) -> str | None:
        check = self.check_at(row)
        return check_group(check) if check is not None else None

    def rowCount(  # noqa: N802 - Qt override
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._checks)

    def columnCount(  # noqa: N802 - Qt override
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        return 0 if parent is not None and parent.isValid() else 4

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        check = self.check_at(index.row())
        if check is None:
            return None
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                status_word(check.status),
                check.title,
                check.reason,
                affects_text(check.affects),
            )[column]
        if role == Qt.ItemDataRole.ToolTipRole:
            return "\n".join((check.reason, *check.fix, *check.details))
        if role == Qt.ItemDataRole.ForegroundRole and column == 0:
            return QColor(tone_color(HEALTH_TONE[check.status])[0])
        if role == Qt.ItemDataRole.UserRole:
            return check_group(check)
        return None

    def headerData(  # noqa: N802 - Qt override
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return (_("Status"), _("Check"), _("Reason"), _("Affects"))[section]
        return None


class DiagnosticsModel(QAbstractTableModel):
    """The findings of the recording profile, the worst first. Columns:
    severity, topic, message; the tooltip is the stable message id. Each row
    knows the plot kind its chart has (:meth:`group_at`)."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[tuple[int, Finding]] = []

    def set_findings(self, findings: Sequence[Finding]) -> None:
        self.beginResetModel()
        self._rows = ranked_findings(list(findings))
        self.endResetModel()

    def finding_at(self, row: int) -> Finding | None:
        return self._rows[row][1] if 0 <= row < len(self._rows) else None

    def original_index(self, row: int) -> int:
        """The finding's index in the measurement's own list."""
        return self._rows[row][0] if 0 <= row < len(self._rows) else -1

    def group_at(self, row: int) -> str | None:
        finding = self.finding_at(row)
        return finding_group(finding) if finding is not None else None

    def rowCount(  # noqa: N802 - Qt override
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._rows)

    def columnCount(  # noqa: N802 - Qt override
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        return 0 if parent is not None and parent.isValid() else 3

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        finding = self.finding_at(index.row())
        if finding is None:
            return None
        column = index.column()
        severity = str(finding.severity)
        if role == Qt.ItemDataRole.DisplayRole:
            return (severity_text(severity), topic_text(finding.topic), finding.message)[column]
        if role == Qt.ItemDataRole.ToolTipRole:
            return finding.message_id or finding.message
        if role == Qt.ItemDataRole.ForegroundRole and column == 0:
            return QColor(tone_color(SEVERITY_TONE.get(severity, "neutral"))[0])
        if role == Qt.ItemDataRole.UserRole:
            return finding_group(finding)
        return None

    def headerData(  # noqa: N802 - Qt override
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return (_("Severity"), _("Topic"), _("Message"))[section]
        return None


# --- widgets --------------------------------------------------------------------------


def _compact_view(view: QAbstractItemView) -> None:
    """One line per row, no grid, alternate colours, rows selected whole."""
    view.setAlternatingRowColors(True)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setTextElideMode(Qt.TextElideMode.ElideRight)
    if isinstance(view, QTableView):
        view.setShowGrid(False)
        view.setWordWrap(False)
        vertical = view.verticalHeader()
        vertical.setVisible(False)
        vertical.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vertical.setDefaultSectionSize(22)
        view.horizontalHeader().setHighlightSections(False)
        view.horizontalHeader().setStretchLastSection(True)


def _table(columns: Sequence[str]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(list(columns))
    _compact_view(table)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def _cell(value: str, tooltip: str = "") -> QTableWidgetItem:
    item = QTableWidgetItem(value)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if tooltip:
        item.setToolTip(tooltip)
    return item


def _fill_table(table: QTableWidget, rows: Sequence[tuple[str, ...]], *, bold_first: bool) -> None:
    """Rows of figures; a withheld or unreliable value is coloured and a
    missing one muted, so a blank never reads as zero (as the old analysis
    tables did)."""
    colours = tokens()
    table.blockSignals(True)
    table.clearSelection()
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = _cell(value, value)
            if c > 0 and (value.startswith("(") or value == _("insufficient range")):
                item.setForeground(QColor(colours["warn"]))
            elif c > 0 and value in {_("n/a"), "-"}:
                item.setForeground(QColor(colours["muted"]))
            if bold_first and r == 0:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            table.setItem(r, c, item)
    table.blockSignals(False)


def _scrolling(widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(widget)
    return scroll


def _with_note(table: QTableWidget, note: QLabel) -> QWidget:
    """``table`` with a line of explanation under it (a comparison tab)."""
    page = QWidget()
    box = QVBoxLayout(page)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(2)
    box.addWidget(table, 1)
    box.addWidget(note)
    return page


def _notes_starting(comparison: ComparisonResult, *prefixes: str) -> str:
    """The comparison's notes that start with one of ``prefixes``, in the language shown."""
    return "\n".join(localize(note) for note in comparison.notes if note.startswith(prefixes))


def _decay_flags(match: ResonanceMatch) -> str:
    def _flag(value: bool | None) -> str:
        if value is None:
            return "—"
        return _("yes") if value else _("no")

    return f"{_flag(match.baseline_decay_distinguishable)} / {_flag(match.candidate_decay_distinguishable)}"


def _pair(delay_ms: float | None, level_db: float | None) -> str:
    if delay_ms is None:
        return ""
    if level_db is None:
        return f"{delay_ms:.2f}"
    return f"{delay_ms:.2f} / {level_db:.1f}"


class _Detail(QWidget):
    """The right half of a tab: a one-line message, the rows, and a button
    that shows the row's chart."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)
        self.message = label("", wrap=True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message.hide()
        layout.addWidget(self.message)
        self.rows = KeyValueList()
        layout.addWidget(self.rows)
        self.button = flat(QPushButton(_("Show in chart")))
        self.button.setEnabled(False)
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

    def show_rows(
        self, rows: Sequence[tuple[str, str]], *, message: str = "", locatable: bool
    ) -> None:
        self.message.setText(message)
        self.message.setVisible(bool(message))
        self.rows.set_rows(rows)
        self.button.setEnabled(locatable)

    def clear(self) -> None:
        self.show_rows([], locatable=False)


def _split(left: QWidget, right: QWidget) -> QSplitter:
    """A tab body for a wide, short dock: the table left, the detail right."""
    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.setChildrenCollapsible(False)
    splitter.addWidget(left)
    splitter.addWidget(_scrolling(right))
    splitter.setStretchFactor(0, 3)
    splitter.setStretchFactor(1, 2)
    return splitter


class InspectorPanel(QWidget):
    """The properties, quality, diagnostics, tables, comparison and report of
    the selected measurement.

    :attr:`locate_requested` carries ``(plot kind key, index or None)``: the
    chart to show and the band, resonance, reflection or candidate to
    highlight in it. :attr:`comparison_settings_changed` carries whether the
    input gain was unchanged between the baseline and the candidate (the
    window compares again with that setting).
    """

    locate_requested = Signal(str, object)
    comparison_settings_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._measurement: Measurement | None = None
        self._comparison: (
            tuple[Measurement, Measurement, ComparisonResult, ComparisonVerdict] | None
        )
        self._comparison = None
        self._table_key = TABLE_KEYS[0]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # The header: the name, the overall status and the two markers.
        header = QHBoxLayout()
        header.setSpacing(8)
        self.name = QLabel("")
        font = self.name.font()
        font.setBold(True)
        self.name.setFont(font)
        self.name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        header.addWidget(self.name)
        self.status_chip = Chip("", "neutral", glyph=True)
        header.addWidget(self.status_chip)
        self.synthetic_chip = Chip(_("synthetic data"), "info")
        self.synthetic_chip.setToolTip(_("Synthetic data: a simulated room, not a measurement."))
        header.addWidget(self.synthetic_chip)
        self.unsaved_chip = Chip(_("unsaved"), "warn")
        header.addWidget(self.unsaved_chip)
        header.addStretch(1)
        self.header = QWidget()
        self.header.setLayout(header)
        layout.addWidget(self.header)

        self.hint = label(_("No measurement selected."), "hint")
        layout.addWidget(self.hint)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs, 1)
        self._build_quality_tab()
        self._build_diagnostics_tab()
        self._build_properties_tab()
        self._build_tables_tab()
        self._build_comparison_tab()
        self._build_report_tab()
        self.set_measurement(None)

    # --- tabs -----------------------------------------------------------------------

    def tab_index(self, name: str) -> int:
        """The index of a tab by its key: ``quality``, ``diagnostics``,
        ``properties``, ``tables``, ``comparison`` or ``report``."""
        return TAB_KEYS.index(name) if name in TAB_KEYS else -1

    def show_tab(self, name: str) -> None:
        index = self.tab_index(name)
        if index >= 0 and self.tabs.isTabEnabled(index):
            self.tabs.setCurrentIndex(index)

    def header_text(self) -> str:
        """The header as one line: the name, the status and the markers shown."""
        parts = [self.name.text(), self.status_chip.text()]
        if not self.synthetic_chip.isHidden():
            parts.append(self.synthetic_chip.text())
        if not self.unsaved_chip.isHidden():
            parts.append(self.unsaved_chip.text())
        return "  ".join(part for part in parts if part)

    def set_same_gain(self, same_gain: bool) -> None:
        """Tick "Input gain unchanged" (the window compares again on the signal)."""
        self.same_gain.setChecked(same_gain)

    # --- building -------------------------------------------------------------------

    def _build_quality_tab(self) -> None:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 4, 0, 0)
        box.setSpacing(4)
        self.health_summary = label("", "hint", wrap=True)
        box.addWidget(self.health_summary)
        self.checks_model = ChecksModel(self)
        self.checks_view = QTableView()
        self.checks_view.setModel(self.checks_model)
        _compact_view(self.checks_view)
        header = self.checks_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.check_detail = _Detail()
        self.check_detail.button.clicked.connect(self._locate_check)
        self.checks_view.selectionModel().currentRowChanged.connect(
            lambda current, _previous: self._check_selected(current.row())
        )
        box.addWidget(_split(self.checks_view, self.check_detail), 1)
        self.quality_tab = page
        self.tabs.addTab(page, _("Measurement quality"))

    def _build_diagnostics_tab(self) -> None:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 4, 0, 0)
        box.setSpacing(4)
        self.findings_hint = label("", "hint", wrap=True)
        box.addWidget(self.findings_hint)
        self.diagnostics_model = DiagnosticsModel(self)
        self.diagnostics_view = QTableView()
        self.diagnostics_view.setModel(self.diagnostics_model)
        _compact_view(self.diagnostics_view)
        header = self.diagnostics_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.diagnostics_view.doubleClicked.connect(lambda index: self._locate_finding(index.row()))
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self.diagnostics_view)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self._locate_current_finding)
        self.finding_detail = _Detail()
        self.finding_detail.button.clicked.connect(self._locate_current_finding)
        self.diagnostics_view.selectionModel().currentRowChanged.connect(
            lambda current, _previous: self._finding_selected(current.row())
        )
        box.addWidget(_split(self.diagnostics_view, self.finding_detail), 1)
        self.diagnostics_tab = page
        self.tabs.addTab(page, _("Diagnostics"))

    def _build_properties_tab(self) -> None:
        body = QWidget()
        box = QVBoxLayout(body)
        box.setContentsMargins(0, 6, 6, 4)
        self.properties = KeyValueList()
        box.addWidget(self.properties)
        box.addStretch(1)
        self.properties_tab = _scrolling(body)
        self.tabs.addTab(self.properties_tab, _("Properties"))

    def _build_tables_tab(self) -> None:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 4, 0, 0)
        box.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.table_kind = QComboBox()
        for key in TABLE_KEYS:
            self.table_kind.addItem(_table_title(key), key)
        self.table_kind.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.table_kind.currentIndexChanged.connect(self._table_kind_changed)
        row.addWidget(self.table_kind)
        self.table_note = label("", "hint", wrap=True)
        self.table_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.table_note, 1)
        box.addLayout(row)
        self.table = _table(_table_columns(self._table_key))
        self.table.itemSelectionChanged.connect(self._table_row_selected)
        self.table_detail = _Detail()
        self.table_detail.button.clicked.connect(self._locate_table_row)
        box.addWidget(_split(self.table, self.table_detail), 1)
        self.tables_tab = page
        self.tabs.addTab(page, _("Tables"))

    def _build_comparison_tab(self) -> None:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 4, 0, 0)
        box.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.comparison_pair = label("", "hint", wrap=True)
        top.addWidget(self.comparison_pair, 1)
        self.same_gain = QCheckBox(_("Input gain unchanged"))
        self.same_gain.setToolTip(
            _(
                "Required for a VALID noise delta. Leave unchecked if the preamp gain "
                "may have changed."
            )
        )
        self.same_gain.toggled.connect(self.comparison_settings_changed.emit)
        top.addWidget(self.same_gain)
        box.addLayout(top)
        self.verdict_headline = label("", wrap=True)
        self.verdict_headline.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.verdict_headline)
        self.verdict_conditions = label("", "hint", wrap=True)
        box.addWidget(self.verdict_conditions)
        self.aspects = _table([_("Verdict"), _("Aspect"), _("Reason")])
        self.deltas = _table(
            [_("Metric"), _("Baseline"), _("Candidate"), _("Delta"), "%", _("Validity")]
        )
        self.reflections = _table(
            [_("Status"), _("Baseline (ms / dB)"), _("Candidate (ms / dB)"), _("Δ level (dB)")]
        )
        self.reflections_note = label("", "hint", wrap=True)
        self.resonances = _table(
            [_("Status"), _("Baseline (Hz)"), _("Candidate (Hz)"), _("Decay distinguishable")]
        )
        self.resonances_note = label("", "hint", wrap=True)
        self.comparison_tables = QTabWidget()
        self.comparison_tables.setDocumentMode(True)
        self.comparison_tables.addTab(self.deltas, _("Metrics"))
        self.comparison_tables.addTab(
            _with_note(self.reflections, self.reflections_note), _("Reflections")
        )
        self.comparison_tables.addTab(
            _with_note(self.resonances, self.resonances_note), _("Resonances")
        )
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.aspects)
        splitter.addWidget(self.comparison_tables)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        box.addWidget(splitter, 1)
        self.comparison_tab = page
        self.tabs.addTab(page, _("Comparison"))

    def _build_report_tab(self) -> None:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 4, 0, 0)
        box.setSpacing(4)
        row = QHBoxLayout()
        self.copy_button = flat(QPushButton(_("Copy report")))
        self.copy_button.clicked.connect(self.copy_report)
        row.addWidget(self.copy_button)
        self.report_note = label("", "hint")
        row.addWidget(self.report_note, 1)
        box.addLayout(row)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setProperty("report", True)
        self.report.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        apply_report_font(self.report)
        box.addWidget(self.report, 1)
        self.report_tab = page
        self.tabs.addTab(page, _("Report"))

    # --- the measurement ------------------------------------------------------------

    def measurement(self) -> Measurement | None:
        return self._measurement

    def set_measurement(self, measurement: Measurement | None) -> None:
        """Show ``measurement``; ``None`` shows the hint alone and emits nothing."""
        self._measurement = measurement
        if measurement is None:
            self.header.hide()
            self.tabs.hide()
            self.hint.show()
            self.checks_model.set_report(None)
            self.diagnostics_model.set_findings([])
            self.check_detail.clear()
            self.finding_detail.clear()
            self.table_detail.clear()
            self.properties.set_rows([])
            self.health_summary.setText("")
            self.findings_hint.setText("")
            self.table_note.setText("")
            self.table.setRowCount(0)
            self.report.setPlainText("")
            self.report_note.setText("")
            self._show_comparison()
            return
        self.hint.hide()
        self.header.show()
        self.tabs.show()
        self._show_header(measurement)
        self._show_quality(measurement)
        self._show_diagnostics(measurement)
        self.properties.set_rows(property_rows(measurement))
        self._fill_table()
        self._show_comparison()
        self.report.setPlainText(
            render_analysis(
                REPORT_CONSOLE, measurement.result, measurement.findings, measurement.profile
            )
        )
        self.report_note.setText("")

    def restyle(self) -> None:
        """Fill the tables again in the colour scheme now in force."""
        self.set_measurement(self._measurement)

    def _show_header(self, measurement: Measurement) -> None:
        self.name.setText(measurement.name())
        text, tone = quality_chip_text(measurement)
        self.status_chip.setText(text)
        self.status_chip.set_tone(tone)
        self.synthetic_chip.setVisible(measurement.synthetic)
        self.unsaved_chip.setVisible(measurement.unsaved)

    # --- quality --------------------------------------------------------------------

    def _show_quality(self, measurement: Measurement) -> None:
        report = measurement.health
        assert report is not None
        self.health_summary.setText(health_summary(report))
        self.checks_model.set_report(report)
        self.check_detail.clear()

    def _check_selected(self, row: int) -> None:
        check = self.checks_model.check_at(row)
        if check is None:
            self.check_detail.clear()
            return
        self.check_detail.show_rows(check_rows(check), locatable=check_group(check) is not None)

    def _locate_check(self) -> None:
        group = self.checks_model.group_at(self.checks_view.currentIndex().row())
        if group is not None:
            self.locate_requested.emit(group, None)

    # --- diagnostics ----------------------------------------------------------------

    def _show_diagnostics(self, measurement: Measurement) -> None:
        self.diagnostics_model.set_findings(measurement.findings)
        self.finding_detail.clear()
        if measurement.findings_problem:
            self.findings_hint.setText(localize(measurement.findings_problem))
        elif not measurement.findings:
            self.findings_hint.setText(
                _("No findings under the {profile} profile.").format(
                    profile=profile_title(measurement.profile)
                )
            )
        else:
            self.findings_hint.setText("")
        self.findings_hint.setVisible(bool(self.findings_hint.text()))

    def _finding_selected(self, row: int) -> None:
        finding = self.diagnostics_model.finding_at(row)
        if finding is None:
            self.finding_detail.clear()
            return
        self.finding_detail.show_rows(
            finding_rows(finding),
            message=finding.message,
            locatable=finding_group(finding) is not None,
        )

    def _locate_current_finding(self) -> None:
        self._locate_finding(self.diagnostics_view.currentIndex().row())

    def _locate_finding(self, row: int) -> None:
        group = self.diagnostics_model.group_at(row)
        finding = self.diagnostics_model.finding_at(row)
        if group == KIND_IMPULSE and finding is not None and finding.topic == "early_reflections":
            # The impulse group holds two charts; a reflection finding wants the timeline.
            group = KIND_REFLECTIONS
        if group is not None:
            self.locate_requested.emit(group, None)

    # --- tables ---------------------------------------------------------------------

    def table_key(self) -> str:
        return self._table_key

    def set_table_key(self, key: str) -> None:
        index = self.table_kind.findData(key)
        if index >= 0:
            self.table_kind.setCurrentIndex(index)

    def _table_kind_changed(self, index: int) -> None:
        key = self.table_kind.itemData(index)
        if isinstance(key, str) and key in TABLE_KEYS:
            self._table_key = key
            self._fill_table()

    def _table_rows(self, result: AnalysisResult) -> tuple[list[tuple[str, ...]], str]:
        """The rows of the current table and the note under its title."""
        key = self._table_key
        placement = result.placement
        if key == "decay":
            return list(decay_table_rows(result)), _(
                "A value in brackets is unreliable; 'insufficient range' means the decay "
                "could not be evaluated over the range that metric needs. Select a band "
                "for the reasons."
            )
        if key == "energy":
            return list(energy_table_rows(result)), _(
                "C50 is early energy over late energy at 50 ms (speech). C80 is the same "
                "at 80 ms (music). D50 is the share of energy in the first 50 ms. Centre "
                "time is the energy-weighted average time. Time zero is the detected "
                "direct sound. A ratio is reported only when the decay range is at least "
                "20 dB, and it is not a room score."
            )
        if key == "noise":
            noise = result.noise
            if noise.rms_dbfs is None:
                note = _("No quiet segment could be verified, so no level is reported.") + " "
                note += " ".join(localize(item) for item in noise.notes)
            else:
                note = _("Levels are digital (dBFS), not dB SPL: uncalibrated.")
            return list(noise_band_rows(result)), note
        if key == "reflections":
            refl = result.reflections
            if refl.window_truncated and refl.analysed_window_ms is not None:
                note = _(
                    "The response ended at {end:.1f} ms, before the {window:.0f} ms window: "
                    "later arrivals could not be seen."
                ).format(end=refl.analysed_window_ms[1], window=refl.window_ms[1])
            else:
                note = _(
                    "Arrivals above {threshold:g} dB re the direct sound inside the window."
                ).format(threshold=refl.threshold_db)
            return list(reflection_rows(result)), note
        if key == "resonances":
            return list(resonance_rows(result)), resonance_note(result)
        if key == "placement_lengths":
            if placement is None:
                return [], placement_summary(None)
            return list(placement_length_rows(placement)), placement_summary(placement)
        if key == "candidates":
            if placement is None:
                return [], placement_summary(None)
            return list(candidate_rows(placement)), " ".join(placement_notes(placement))
        return [], ""

    def _fill_table(self) -> None:
        columns = _table_columns(self._table_key)
        self.table.blockSignals(True)
        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.blockSignals(False)
        self.table_detail.clear()
        if self._measurement is None:
            self.table.setRowCount(0)
            self.table_note.setText("")
            return
        rows, note = self._table_rows(self._measurement.result)
        _fill_table(self.table, rows, bold_first=self._table_key in {"decay", "energy"})
        self.table_note.setText(note)
        self.table_note.setToolTip(note)

    def _selected_table_row(self) -> int:
        rows = {index.row() for index in self.table.selectedIndexes()}
        return rows.pop() if len(rows) == 1 else -1

    def _table_target(self, row: int) -> tuple[str, int | None]:
        """The plot kind and the index a table row points at."""
        key = self._table_key
        if key in {"decay", "energy"}:
            return GROUP_DECAY, row
        if key == "noise":
            return GROUP_NOISE, None
        if key == "reflections":
            return KIND_REFLECTIONS, row
        if key == "resonances":
            return GROUP_FREQUENCY, row
        if key == "candidates":
            return GROUP_PLACEMENT, row
        return GROUP_PLACEMENT, None

    def _table_detail_rows(self, result: AnalysisResult, row: int) -> list[tuple[str, str]]:
        key = self._table_key
        placement = result.placement
        if key in {"decay", "energy"}:
            return band_detail_rows(result, row)
        if key == "noise":
            return noise_detail_rows(result)
        if key == "reflections":
            reflections = result.reflections.reflections
            rows: list[tuple[str, str]] = []
            if 0 <= row < len(reflections):
                reflection = reflections[row]
                rows = [
                    (_("Delay"), f"{reflection.delay_ms:.2f} ms"),
                    (_("Level re direct"), f"{reflection.relative_db:.1f} dB"),
                ]
                if placement is not None and row < len(placement.candidates):
                    rows.append(
                        (_("Excess path"), f"{placement.candidates[row].excess_path_m:.2f} m")
                    )
            return [*rows, *impulse_detail_rows(result)]
        if key == "resonances":
            if 0 <= row < len(result.resonances.candidates):
                return resonance_detail_rows(result, row)
            return []
        if key == "placement_lengths":
            if placement is None:
                return []
            lengths = placement_length_rows(placement)
            if 0 <= row < len(lengths):
                figure, value, validity, note = lengths[row]
                return [(_("Figure"), figure), (_("Value"), value), (_("Validity"), validity)] + (
                    [(_("Note"), note)] if note else []
                )
            return []
        if key == "candidates" and placement is not None and 0 <= row < len(placement.candidates):
            return candidate_detail_rows(placement.candidates[row])
        return []

    def _table_row_selected(self) -> None:
        row = self._selected_table_row()
        if self._measurement is None or row < 0:
            self.table_detail.clear()
            return
        self.table_detail.show_rows(
            self._table_detail_rows(self._measurement.result, row), locatable=True
        )
        kind, index = self._table_target(row)
        self.locate_requested.emit(kind, index)

    def _locate_table_row(self) -> None:
        row = self._selected_table_row()
        if self._measurement is None or row < 0:
            return
        kind, index = self._table_target(row)
        self.locate_requested.emit(kind, index)

    def show_item(self, kind: str, index: int) -> None:
        """A chart clicked a band, resonance, reflection or candidate: select
        the matching table row on the Tables tab without asking the chart back."""
        key = _ITEM_TABLE.get(kind)
        if key is None or self._measurement is None:
            return
        self.tabs.setCurrentWidget(self.tables_tab)
        self.set_table_key(key)
        if not 0 <= index < self.table.rowCount():
            return
        self.blockSignals(True)
        try:
            self.table.selectRow(index)
            self.table.scrollTo(self.table.model().index(index, 0))
        finally:
            self.blockSignals(False)

    # --- comparison -----------------------------------------------------------------

    def set_comparison(
        self,
        baseline: Measurement | None,
        candidate: Measurement | None,
        comparison: ComparisonResult | None,
        verdict: ComparisonVerdict | None,
    ) -> None:
        """Show the comparison of ``candidate`` against ``baseline``; the tab
        is greyed out until all four are at hand."""
        if baseline is None or candidate is None or comparison is None or verdict is None:
            self._comparison = None
        else:
            self._comparison = (baseline, candidate, comparison, verdict)
        self._show_comparison()

    def comparison_enabled(self) -> bool:
        return self.tabs.isTabEnabled(self.tabs.indexOf(self.comparison_tab))

    def _show_comparison(self) -> None:
        index = self.tabs.indexOf(self.comparison_tab)
        shown = self._comparison
        if shown is None or self._measurement is None:
            if self.tabs.currentIndex() == index:
                self.tabs.setCurrentIndex(0)
            self.tabs.setTabEnabled(index, False)
            self.tabs.setTabToolTip(index, _("Set a baseline and select another measurement."))
            self.comparison_pair.setText("")
            self.verdict_headline.setText("")
            self.verdict_conditions.setText("")
            for table in (self.aspects, self.deltas, self.reflections, self.resonances):
                table.setRowCount(0)
            self.reflections_note.setText("")
            self.resonances_note.setText("")
            return
        baseline, candidate, comparison, verdict = shown
        self.tabs.setTabEnabled(index, True)
        self.tabs.setTabToolTip(index, "")
        self.comparison_pair.setText(
            "   ".join(
                (
                    _("{label}: {description}").format(
                        label=_("Baseline"), description=baseline.name()
                    ),
                    _("{label}: {description}").format(
                        label=_("Candidate"), description=candidate.name()
                    ),
                    _("{label}: {description}").format(
                        label=_("Profile"), description=profile_title(verdict.profile)
                    ),
                )
            )
        )
        self.same_gain.blockSignals(True)
        self.same_gain.setChecked(bool(comparison.settings.get("same_input_gain", False)))
        self.same_gain.blockSignals(False)
        self.verdict_headline.setText(verdict.headline())
        self.verdict_conditions.setText("\n".join(verdict.conditions))
        self.verdict_conditions.setVisible(bool(verdict.conditions))
        self._fill_aspects(verdict)
        self._fill_deltas(comparison)
        self._fill_matches(comparison)

    def _fill_aspects(self, verdict: ComparisonVerdict) -> None:
        self.aspects.setRowCount(len(verdict.aspects))
        for r, aspect in enumerate(verdict.aspects):
            evidence = "\n".join(
                f"{name}: {value}" for name, value in evidence_rows(aspect.evidence)
            )
            tooltip = f"{aspect.reason}\n{evidence}".strip()
            chip = _cell(verdict_chip(aspect.verdict), tooltip)
            chip.setForeground(
                QColor(tone_color(SEVERITY_TONE.get(str(aspect.verdict), "neutral"))[0])
            )
            self.aspects.setItem(r, 0, chip)
            self.aspects.setItem(r, 1, _cell(aspect.title, tooltip))
            self.aspects.setItem(r, 2, _cell(aspect.reason, tooltip))

    def _fill_deltas(self, comparison: ComparisonResult) -> None:
        rows = (
            list(comparison.decay)
            + list(comparison.noise)
            + list(comparison.placement)
            + list(comparison.loopback)
        )
        self.deltas.setRowCount(len(rows))
        for r, item in enumerate(rows):
            values = [
                metric_label(item.name, item.unit),
                "" if item.baseline is None else f"{item.baseline:.3f}",
                "" if item.candidate is None else f"{item.candidate:.3f}",
                "" if item.delta is None else signed_number(item.delta, 3),
                "" if item.delta_percent is None else signed_number(item.delta_percent, 1),
                validity_word(item.validity),
            ]
            for c, value in enumerate(values):
                cell = _cell(value)
                if c == 0:
                    cell.setToolTip(item.name)
                if c == len(values) - 1 and item.reason:
                    # Why a delta is missing (core diagnostics, English).
                    cell.setToolTip(localize(item.reason))
                self.deltas.setItem(r, c, cell)

    def _fill_matches(self, comparison: ComparisonResult) -> None:
        self.reflections.setRowCount(len(comparison.reflections))
        self.reflections_note.setText(_notes_starting(comparison, REFLECTIONS_NOT_COMPARED))
        for r, match in enumerate(comparison.reflections):
            delta = "" if match.level_delta_db is None else signed_number(match.level_delta_db, 1)
            values = (
                status_text(match.status),
                _pair(match.baseline_delay_ms, match.baseline_relative_db),
                _pair(match.candidate_delay_ms, match.candidate_relative_db),
                delta,
            )
            for c, value in enumerate(values):
                self.reflections.setItem(r, c, _cell(value))
        self.resonances.setRowCount(len(comparison.resonances))
        self.resonances_note.setText(
            _notes_starting(comparison, RESONANCES_NOT_COMPARED, RESONANCES_NARROWED)
        )
        for r, resonance in enumerate(comparison.resonances):
            values = (
                status_text(resonance.status),
                "" if resonance.baseline_hz is None else f"{resonance.baseline_hz:.1f}",
                "" if resonance.candidate_hz is None else f"{resonance.candidate_hz:.1f}",
                _decay_flags(resonance),
            )
            for c, value in enumerate(values):
                self.resonances.setItem(r, c, _cell(value))

    # --- report ---------------------------------------------------------------------

    def report_text(self) -> str:
        return self.report.toPlainText()

    def copy_report(self) -> None:
        text = self.report.toPlainText()
        if not text.strip():
            self.report_note.setText(_("Nothing to copy yet."))
            return
        QGuiApplication.clipboard().setText(text)
        self.report_note.setText(_("Report copied to the clipboard."))


__all__ = [
    "KIND_IMPULSE",
    "KIND_REFLECTIONS",
    "TABLE_KEYS",
    "ChecksModel",
    "DiagnosticsModel",
    "InspectorPanel",
    "property_rows",
    "quality_chip_text",
]
