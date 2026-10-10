"""reverbscope.ui.pg: the one module that imports pyqtgraph (GUI_2_ARCHITECTURE.md §6.1)."""

from __future__ import annotations

import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PG_MODULE = ROOT / "src" / "reverbscope" / "ui" / "pg.py"
_IMPORT = re.compile(r"^\s*(import\s+pyqtgraph\b|from\s+pyqtgraph\b)", re.MULTILINE)


def test_only_ui_pg_imports_pyqtgraph() -> None:
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src").rglob("*.py"))
        if path != PG_MODULE and _IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
    assert _IMPORT.search(PG_MODULE.read_text(encoding="utf-8"))


def test_the_bundle_keeps_the_colour_maps_pg_offers() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "pyinstaller_filters", ROOT / "packaging" / "pyinstaller_filters.py"
    )
    assert spec is not None and spec.loader is not None
    filters = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(filters)
    text = PG_MODULE.read_text(encoding="utf-8")
    assert 'COLORMAPS = ("viridis", "inferno")' in text
    assert filters.PYQTGRAPH_COLORMAPS == ("viridis", "inferno")
    maps = "pyqtgraph/colors/maps"
    datas = [
        (f"{maps}/viridis.csv", "/x/viridis.csv", "DATA"),
        (f"{maps}/inferno.csv", "/x/inferno.csv", "DATA"),
        (f"{maps}/CET-L1.csv", "/x/CET-L1.csv", "DATA"),
        (f"{maps}/PAL-relaxed.hex", "/x/PAL-relaxed.hex", "DATA"),
        (f"{maps}/CC-BY license - applies to CET color map data.txt", "/x/a", "DATA"),
        (
            f"{maps}/CC0 legal code - applies to virids, magma, plasma, inferno and cividis.txt",
            "/x/b",
            "DATA",
        ),
        ("pyqtgraph\\colors\\maps\\turbo.csv", "/x/turbo.csv", "DATA"),
        ("pyqtgraph/icons/auto.png", "/x/auto.png", "DATA"),
        ("reverbscope/schemas/session.json", "/x/session.json", "DATA"),
    ]
    kept = [entry[0] for entry in filters.without_unused_colormaps(datas)]
    assert kept == [
        f"{maps}/viridis.csv",
        f"{maps}/inferno.csv",
        f"{maps}/CC0 legal code - applies to virids, magma, plasma, inferno and cividis.txt",
        "pyqtgraph/icons/auto.png",
        "reverbscope/schemas/session.json",
    ]
    spec_text = (ROOT / "packaging" / "reverbscope.spec").read_text(encoding="utf-8")
    assert "a.datas = without_unused_colormaps(a.datas)" in spec_text


def test_the_desktop_bundle_leaves_pyqtgraph_extras_out() -> None:
    spec = (ROOT / "packaging" / "reverbscope.spec").read_text(encoding="utf-8")
    excludes = spec[spec.index("PYQTGRAPH_EXCLUDES = [") :]
    excludes = excludes[: excludes.index("]")]
    for module in (
        "PySide6.QtTest",
        "pyqtgraph.opengl",
        "pyqtgraph.examples",
        "pyqtgraph.jupyter",
        "OpenGL",
    ):
        assert f'"{module}"' in excludes, module
    desktop = spec[spec.index("    else [") :]
    assert "*PYQTGRAPH_EXCLUDES" in desktop.split("]", 1)[0]


# --- With Qt and pyqtgraph ---------------------------------------------------------------


@pytest.fixture(scope="module")
def pg() -> Iterator[ModuleType]:
    pytest.importorskip("PySide6.QtWidgets")
    pytest.importorskip("pyqtgraph")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from reverbscope.ui import pg as module

    yield module


@pytest.fixture
def plot(pg: ModuleType) -> Iterator[Any]:
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    widget = pg.pyqtgraph().PlotWidget()
    widget.resize(240, 160)
    widget.plot([0.0, 1.0, 2.0, 3.0], [1.0, 3.0, 2.0, 4.0])
    widget.show()
    QApplication.processEvents()
    yield widget
    # PlotWidget.close() is not idempotent (it drops its PlotItem), and the
    # session teardown in tests/conftest.py closes every top-level widget left.
    widget.close()
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.gui
def test_pyqtgraph_is_configured_without_opengl(pg: ModuleType) -> None:
    module = pg.pyqtgraph()
    assert module is pg.pyqtgraph()
    assert module.__version__ == "0.14.0"
    assert module.getConfigOption("useOpenGL") is False
    assert module.getConfigOption("antialias") is True
    assert module.getConfigOption("background") is None
    assert "OpenGL" not in sys.modules
    assert "pyqtgraph.opengl" not in sys.modules


@pytest.mark.gui
@pytest.mark.parametrize("name", ["viridis", "inferno"])
def test_colormap_offers_the_bundled_maps(pg: ModuleType, name: str) -> None:
    colormap = pg.colormap(name)
    assert isinstance(colormap, pg.pyqtgraph().ColorMap)
    assert len(colormap.getLookupTable(nPts=8)) == 8


@pytest.mark.gui
@pytest.mark.parametrize("name", ["CET-L1", "magma", "Viridis", ""])
def test_colormap_refuses_maps_the_bundle_drops(pg: ModuleType, name: str) -> None:
    with pytest.raises(ValueError, match="viridis, inferno"):
        pg.colormap(name)


@pytest.mark.gui
def test_disable_menus_keeps_mouse_zoom(pg: ModuleType, plot: Any) -> None:
    item = plot.getPlotItem()
    pg.disable_menus(item)
    assert not item.menuEnabled()
    assert not item.getViewBox().menuEnabled()
    assert item.getViewBox().state["mouseEnabled"] == [True, True]
    # A zoomed plot shows "A" on hover unless the buttons are hidden.
    item.getViewBox().setXRange(1, 2)
    item.mouseHovering = True
    item.updateButtons()
    assert not item.autoBtn.isVisible()


@pytest.mark.gui
@pytest.mark.parametrize("which", ["widget", "item"])
def test_svg_export_writes_parseable_svg(
    pg: ModuleType, plot: Any, tmp_path: Path, which: str
) -> None:
    out = tmp_path / "chart.svg"
    pg.svg_export(plot if which == "widget" else plot.getPlotItem(), out)
    root = ET.parse(out).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    shapes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] in ("path", "polyline")]
    assert shapes
    # The curve's points, in data coordinates under the ViewBox transform.
    assert any(node.get("d", "").startswith("M0,1 L1,3 L2,2 L3,4") for node in shapes)
    # At QSvgGenerator's default 72 dpi the cached axes replayed at 72/96 scale.
    assert 'transform="matrix(0.75,0,0,0.75' not in out.read_text(encoding="utf-8")


@pytest.mark.gui
@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_png_export_writes_the_scaled_size(
    pg: ModuleType, plot: Any, tmp_path: Path, scale: float
) -> None:
    out = tmp_path / "chart.png"
    pg.png_export(plot, out, scale=scale)
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    viewport = plot.viewport().size()
    assert (width, height) == (round(viewport.width() * scale), round(viewport.height() * scale))


@pytest.mark.gui
def test_png_export_refuses_a_bad_scale(pg: ModuleType, plot: Any, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="scale"):
        pg.png_export(plot, tmp_path / "chart.png", scale=0)
    assert not (tmp_path / "chart.png").exists()
