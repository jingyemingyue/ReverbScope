"""The one module that imports pyqtgraph (GUI_2_ARCHITECTURE.md §6.1).

Charts use pyqtgraph 0.14.0, pinned exactly in the ``gui`` extra because the
code here leans on its internals. Everything else in the GUI asks this module
for pyqtgraph (:func:`pyqtgraph`), a colour map (:func:`colormap`) or an
export (:func:`svg_export`, :func:`png_export`); a test rejects
``import pyqtgraph`` anywhere else.

pyqtgraph draws with ``QPainter`` on the Qt the app already ships; nothing
here turns on OpenGL or imports PyOpenGL. Its own SVG exporter fails on Qt
6.11 (it cannot parse the ``points`` Qt now writes for a polyline), so
:func:`svg_export` paints the chart into a ``QSvgGenerator`` instead. Its
context menus and export dialog are English only; :func:`disable_menus`
switches them off.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QByteArray, QPointF, QRect, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QImageWriter, QPainter
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView

if TYPE_CHECKING:
    from pyqtgraph import ColorMap, PlotItem

#: The colour maps the app uses; the desktop bundle keeps only these tables
#: (packaging/pyinstaller_filters.py ``PYQTGRAPH_COLORMAPS``).
COLORMAPS = ("viridis", "inferno")

#: A chart to export: a ``PlotWidget`` / ``GraphicsLayoutWidget`` (a
#: ``QGraphicsView``) or a ``PlotItem`` inside one (a ``QGraphicsItem``).
Chart = QGraphicsView | QGraphicsItem


@functools.cache
def pyqtgraph() -> ModuleType:
    """pyqtgraph, imported on first use and configured for the app."""
    import pyqtgraph as pg

    pg.setConfigOptions(
        antialias=True,
        # QPainter only: the bundles ship no PyOpenGL (packaging/reverbscope.spec).
        useOpenGL=False,
        # The chart takes the window's colours; plotkit styles axes and pens.
        background=None,
        leftButtonPan=True,
        useNumba=False,
        useCupy=False,
    )
    module: ModuleType = pg
    return module


def colormap(name: str) -> ColorMap:
    """The ``pyqtgraph.ColorMap`` called ``name``: one of :data:`COLORMAPS`."""
    if name not in COLORMAPS:
        raise ValueError(f"unknown colour map {name!r}; use one of {', '.join(COLORMAPS)}")
    return pyqtgraph().colormap.get(name)


def disable_menus(plot_item: PlotItem) -> None:
    """Switch off pyqtgraph's English context menus and the "A" auto-range button.

    Mouse zoom and pan stay on; Reset and Export live in the app's own menus.
    """
    plot_item.setMenuEnabled(False)
    view_box = plot_item.getViewBox()
    view_box.setMenuEnabled(False)
    view_box.setMouseEnabled(x=True, y=True)
    # Also keeps it hidden when the mouse hovers a zoomed plot.
    plot_item.hideButtons()


def svg_export(chart: Chart, path: str | Path) -> None:
    """Write ``chart`` as it looks on screen to an SVG file at ``path``."""
    size = _size(chart)
    width, height = max(1, round(size.width())), max(1, round(size.height()))
    generator = QSvgGenerator()
    generator.setFileName(str(path))
    generator.setSize(QSize(width, height))
    generator.setViewBox(QRect(0, 0, width, height))
    generator.setTitle("ReverbScope")
    # pyqtgraph caches axes in QPictures, which replay scaled by the screen's
    # DPI over the device's: at QSvgGenerator's default 72 dpi they shrank to
    # three quarters and no longer lined up with the curves.
    screen = QGuiApplication.primaryScreen()
    generator.setResolution(round(screen.logicalDotsPerInchX()) if screen is not None else 96)
    painter = QPainter()
    if not painter.begin(generator):
        raise OSError(f"cannot write {path}")
    try:
        _paint(chart, painter, QSizeF(width, height), scale=1.0)
    finally:
        painter.end()


def png_export(chart: Chart, path: str | Path, scale: float = 2.0) -> None:
    """Write ``chart`` to a PNG file at ``path``, ``scale`` times its size on screen."""
    if not scale > 0:
        raise ValueError(f"scale must be positive, not {scale!r}")
    size = _size(chart)
    width = max(1, round(size.width() * scale))
    height = max(1, round(size.height() * scale))
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        _paint(chart, painter, QSizeF(width, height), scale=scale)
    finally:
        painter.end()
    writer = QImageWriter(str(path), QByteArray(b"png"))
    if not writer.write(image):
        raise OSError(f"cannot write {path}: {writer.errorString()}")


def _size(chart: Chart) -> QSizeF:
    if isinstance(chart, QGraphicsView):
        return QSizeF(chart.viewport().size())
    return chart.sceneBoundingRect().size()


def _scene(chart: Chart) -> QGraphicsScene:
    scene = chart.scene()
    if scene is None:
        raise ValueError("the chart is not in a scene")
    return scene


def _background(chart: Chart) -> QBrush | QColor | None:
    """What is behind the chart on screen: the view's brush, else its palette."""
    if isinstance(chart, QGraphicsView):
        view: QGraphicsView | None = chart
    else:
        views = _scene(chart).views()
        view = views[0] if views else None
    if view is None:
        return None
    brush = view.backgroundBrush()
    if brush.style() != Qt.BrushStyle.NoBrush:
        return brush
    viewport = view.viewport()
    return viewport.palette().color(viewport.backgroundRole())


def _paint(chart: Chart, painter: QPainter, size: QSizeF, *, scale: float) -> None:
    target = QRectF(QPointF(0, 0), size)
    scene = _scene(chart)
    background = _background(chart)
    if background is not None:
        painter.fillRect(target, background)
    # What pyqtgraph's own exporters do: items hide hover-only decorations and
    # scale scatter symbols to the output resolution.
    options = {"antialias": True, "painter": painter, "resolutionScale": scale}
    exporting = [
        setter for item in scene.items() if (setter := _export_mode_setter(item)) is not None
    ]
    for setter in exporting:
        setter(True, options)
    try:
        if isinstance(chart, QGraphicsView):
            # The view's background was painted above; render() draws the scene.
            source = chart.mapToScene(chart.viewport().rect()).boundingRect()
            scene.render(painter, target, source, Qt.AspectRatioMode.IgnoreAspectRatio)
        else:
            scene.render(
                painter, target, chart.sceneBoundingRect(), Qt.AspectRatioMode.IgnoreAspectRatio
            )
    finally:
        for setter in exporting:
            setter(False, None)


def _export_mode_setter(item: QGraphicsItem) -> Callable[[bool, Any], None] | None:
    setter = getattr(item, "setExportMode", None)
    return setter if callable(setter) else None
