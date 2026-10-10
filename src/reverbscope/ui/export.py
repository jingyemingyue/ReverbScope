"""Export entry points of the Results page: the CSV tables of a result and
the chart on screen as a PNG. Every failure is shown with its reason;
nothing reports success it did not have.
"""

from __future__ import annotations

from pathlib import Path

from matplotlib.figure import Figure
from PySide6.QtWidgets import QFileDialog, QWidget

from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _, list_join, localize
from reverbscope.io.exporters import get_exporter
from reverbscope.models.result import AnalysisResult
from reverbscope.ui.widgets import ask_save_path, error_box


def export_csv_tables(parent: QWidget, result: AnalysisResult, start_dir: str = "") -> str:
    """Write the CSV exporter's files into a folder the user picks.

    Returns the status sentence (what was written, or empty when cancelled);
    a failure opens a dialog with the reason and returns its sentence.
    """
    directory = QFileDialog.getExistingDirectory(
        parent, _("Choose a folder for the CSV files"), start_dir
    )
    if not directory:
        return ""
    try:
        written = get_exporter("csv").export(result, Path(directory))
    except (ReverbScopeError, OSError) as exc:
        message = _("The CSV export failed: {error}").format(error=localize(str(exc)))
        error_box(parent, _("Cannot export"), message)
        return message
    names = list_join(path.name for path in written)
    return _("Wrote {n} CSV file(s) to {path}: {names}").format(
        n=len(written), path=directory, names=names
    )


def export_figure_png(parent: QWidget, figure: Figure, suggested: str) -> str:
    """Save ``figure`` as it is on screen; returns the status sentence."""
    target = ask_save_path(
        parent, _("Save chart as PNG"), f"{suggested}.png", _("PNG images (*.png)")
    )
    if target is None:
        return ""
    try:
        figure.savefig(str(target), dpi=150, facecolor=figure.get_facecolor())
    except (OSError, ValueError) as exc:
        message = _("The chart could not be written: {error}").format(error=str(exc))
        error_box(parent, _("Cannot export"), message)
        return message
    return _("Wrote {path}").format(path=target)
