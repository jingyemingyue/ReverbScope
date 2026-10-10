"""Regenerate the README screenshots from the synthetic demo (no audio hardware).

    QT_QPA_PLATFORM=offscreen python scripts/render_readme_assets.py [--out docs/images]

Writes:

* ``cli-demo.svg``            -- ``reverbscope demo`` as a terminal screenshot (SVG text)
* ``cli-demo.zh-CN.svg``      -- the same in Simplified Chinese
* ``gui-results.png``         -- the workstation, Overview view, position A
* ``gui-results.zh-CN.png``   -- the same in Simplified Chinese (README.zh-CN.md)
* ``gui-frequency-response.png`` -- the workstation, Frequency response view, position A
* ``gui-compare.png``         -- the workstation, Compare view, A -> B
* ``social-preview.png``      -- 1280x640 card for the GitHub social preview

Every image comes from ``reverbscope demo``: a simulated room, not a measurement.
The GUI images carry a "Synthetic demo data" stamp so they stay labelled when
they are shared out of context, and show the user edition, as the downloaded
app does (no Developer menu). Needs the ``gui`` extra.
"""

from __future__ import annotations

import argparse
import contextlib
import html
import io
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path

STAMP = "Synthetic demo data (reverbscope demo) - not a real room measurement"
STAMP_ZH = "合成演示数据（reverbscope demo），不是真实房间的测量"
TERMINAL_COLUMNS = 80
_SGR = re.compile(r"\x1b\[([\d;]*)m")
_COLOURS = {"31": "#f07178", "32": "#a8d982", "33": "#e6c07b", "36": "#6cc4d9"}


def _cells(text: str) -> int:
    """Terminal columns: East Asian wide characters take two (as in reverbscope.cli.console)."""
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)


def _runs(text: str) -> list[tuple[str, int]]:
    """``text`` split where the character width changes, with each run's width."""
    runs: list[tuple[str, int]] = []
    for char in text:
        wide = unicodedata.east_asian_width(char) in ("W", "F")
        if runs and (runs[-1][1] == 2) == wide:
            runs[-1] = (runs[-1][0] + char, runs[-1][1])
        else:
            runs.append((char, 2 if wide else 1))
    return runs


def _ansi_to_tspans(line: str, *, x0: float, char_w: float) -> str:
    """One terminal line with SGR colour codes -> SVG <tspan> elements.

    Each run of wide (CJK) or narrow characters starts at its exact terminal
    column, so the columns after Chinese text stay aligned whatever the
    fallback font's glyph widths are.
    """
    parts: list[str] = []
    bold = dim = False
    colour: str | None = None
    position = 0
    column = 0
    for match in [*_SGR.finditer(line), None]:
        end = match.start() if match is not None else len(line)
        text = line[position:end]
        for run, width in _runs(text):
            attrs = [f'x="{x0 + column * char_w:.1f}"']
            if bold:
                attrs.append('font-weight="bold"')
            if dim:
                attrs.append('opacity="0.62"')
            if colour:
                attrs.append(f'fill="{colour}"')
            parts.append(f"<tspan {' '.join(attrs)}>{html.escape(run)}</tspan>")
            column += len(run) * width
        if match is None:
            break
        for code in (match.group(1) or "0").split(";"):
            if code in {"0", ""}:
                bold = dim = False
                colour = None
            elif code == "1":
                bold = True
            elif code == "2":
                dim = True
            elif code in _COLOURS:
                colour = _COLOURS[code]
        position = match.end()
    return "".join(parts)


def terminal_svg(command: str, output: str, *, title: str) -> str:
    lines = [f"\x1b[32m$\x1b[0m \x1b[1m{command}\x1b[0m", *output.rstrip("\n").splitlines()]
    char_w, line_h, pad, bar = 8.4, 18, 16, 30
    columns = max(TERMINAL_COLUMNS, *(_cells(_SGR.sub("", line)) for line in lines))
    width = int(columns * char_w + 2 * pad)
    height = int(bar + pad + len(lines) * line_h + pad)
    rows = []
    for index, line in enumerate(lines):
        y = bar + pad + (index + 1) * line_h - 4
        spans = _ansi_to_tspans(line, x0=pad, char_w=char_w)
        rows.append(f'<text x="{pad}" y="{y}" xml:space="preserve">{spans}</text>')
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
            f"<title>{html.escape(title)}</title>",
            f'<rect width="{width}" height="{height}" rx="8" fill="#1d1f23"/>',
            f'<rect width="{width}" height="{bar}" rx="8" fill="#2b2e33"/>',
            f'<rect y="{bar - 8}" width="{width}" height="8" fill="#2b2e33"/>',
            '<circle cx="18" cy="15" r="6" fill="#ff5f57"/>',
            '<circle cx="38" cy="15" r="6" fill="#febc2e"/>',
            '<circle cx="58" cy="15" r="6" fill="#28c840"/>',
            f'<text x="{width / 2}" y="20" text-anchor="middle" fill="#9aa0a6" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="12">{html.escape(title)}</text>',
            '<g font-family="DejaVu Sans Mono, Menlo, Consolas, Noto Sans Mono CJK SC, monospace" '
            'font-size="14" '
            'fill="#d7dae0">',
            *rows,
            "</g>",
            "</svg>",
            "",
        ]
    )


def demo_folder(workdir: Path, lang: str) -> Path:
    """Where ``reverbscope demo`` runs in ``lang``.

    The demo writes the room and position names in the active language, so
    each language keeps its own sessions: the English window must not show
    the names the Chinese run wrote. English stays at ``workdir``, whose path
    the Compare screenshot shows.
    """
    return workdir if lang == "en" else workdir / lang


def enter_language(workdir: Path, lang: str) -> Path:
    """Use ``lang``'s demo folder and its own ReverbScope home; return the folder.

    Each language has its own home so its sessions stay out of the other
    language's recent-session list, which the Compare screenshot shows.
    """
    folder = demo_folder(workdir, lang)
    folder.mkdir(parents=True, exist_ok=True)
    os.environ["REVERBSCOPE_HOME"] = str(folder / "home")
    return folder


def render_cli(workdir: Path, out: Path) -> None:
    from reverbscope.cli.main import main
    from reverbscope.i18n import activate

    previous = Path.cwd()
    try:
        for lang, name, title in (
            ("en", "cli-demo.svg", "reverbscope demo (synthetic data)"),
            ("zh_CN", "cli-demo.zh-CN.svg", "reverbscope demo（合成数据）"),
        ):
            os.chdir(enter_language(workdir, lang))
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
                code = main(["--lang", lang, "--color", "always", "demo"])
            if code != 0:
                raise SystemExit(f"reverbscope demo failed with {code}")
            command = "reverbscope demo" if lang == "en" else "reverbscope --lang zh_CN demo"
            svg = terminal_svg(command, buffer.getvalue(), title=title)
            (out / name).write_text(svg, encoding="utf-8")
    finally:
        activate("en")
        os.chdir(previous)


def _stamp(pixmap: object, stamp: str = STAMP) -> object:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QPainter

    painter = QPainter(pixmap)  # type: ignore[call-overload]
    font = QFont()
    font.setPointSize(9)
    font.setBold(True)
    painter.setFont(font)
    metrics = painter.fontMetrics()
    text_w = metrics.horizontalAdvance(stamp) + 16
    text_h = metrics.height() + 8
    rect = QRect(pixmap.width() - text_w - 8, 8, text_w, text_h)  # type: ignore[attr-defined]
    painter.fillRect(rect, QColor(255, 196, 0, 235))
    painter.setPen(QColor(20, 20, 20))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, stamp)
    painter.end()
    return pixmap


def render_gui(workdir: Path, out: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # The downloaded app is the user edition; a source checkout would show the
    # Developer menu, which no reader of the README has.
    os.environ["REVERBSCOPE_EDITION"] = "user"
    from PySide6.QtWidgets import QApplication

    from reverbscope.i18n import activate
    from reverbscope.ui import main_window
    from reverbscope.ui.theme import apply_application_chrome

    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_application_chrome(app)  # type: ignore[arg-type]
    demo = demo_folder(workdir, "en") / "reverbscope-demo"

    def window_in(lang: str) -> main_window.MainWindow:
        # The window reads the language while it is built.
        enter_language(workdir, lang)
        activate(lang)
        window = main_window.MainWindow()
        window.resize(1366, 820)
        window.show()
        window.open_session_path(demo_folder(workdir, lang) / "reverbscope-demo" / "position-a")
        window.show_view("overview")
        return window

    def grab(window: main_window.MainWindow, name: str, stamp: str = STAMP) -> None:
        for _ in range(5):
            app.processEvents()
        _stamp(window.grab(), stamp).save(str(out / name))  # type: ignore[attr-defined]

    try:
        window = window_in("en")
        grab(window, "gui-results.png")
        window.show_view("fr")
        grab(window, "gui-frequency-response.png")
        window.resize(1366, 1000)
        window.show_compare()
        window.compare.set_paths(demo / "position-a", demo / "position-b")
        window.compare.same_gain.setChecked(True)
        window.compare.run_compare()
        grab(window, "gui-compare.png")
        window.close()
        # README.zh-CN.md shows the results page as a Chinese reader sees it.
        window = window_in("zh_CN")
        grab(window, "gui-results.zh-CN.png", STAMP_ZH)
        window.close()
    finally:
        activate("en")


def render_social_preview(out: Path) -> None:
    """1280x640 card: name, tagline and the (synthetic) results screenshot."""
    from PySide6.QtCore import QRect, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPixmap

    card = QImage(1280, 640, QImage.Format.Format_RGB32)
    card.fill(QColor("#15171b"))
    painter = QPainter(card)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    def text(x: int, y: int, w: int, h: int, body: str, size: int, colour: str, bold=False) -> None:
        font = QFont()
        font.setPixelSize(size)
        font.setBold(bold)
        painter.setFont(font)
        painter.setPen(QColor(colour))
        flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap
        painter.drawText(QRect(x, y, w, h), int(flags), body)

    text(64, 150, 560, 90, "ReverbScope", 76, "#ffffff", bold=True)
    text(
        64,
        250,
        520,
        110,
        "Open-source room acoustics analysis for recording engineers",
        32,
        "#d7dae0",
    )
    text(
        64,
        380,
        520,
        90,
        "RT60 · early reflections · frequency response · noise floor · "
        "microphone-position comparison",
        22,
        "#8fb8de",
    )
    text(64, 540, 560, 40, "DAW-independent · CLI · desktop app · Python API", 20, "#9aa0a6")

    shot = QPixmap(str(out / "gui-results.png"))
    target = QRectF(650, 70, 580, 580 * shot.height() / max(shot.width(), 1))
    clip = QPainterPath()
    clip.addRoundedRect(target, 12, 12)
    painter.setClipPath(clip)
    painter.drawPixmap(target.toRect(), shot)
    painter.setClipping(False)
    text(650, int(target.bottom()) + 10, 580, 30, "Screenshot: synthetic demo data", 16, "#9aa0a6")
    painter.end()
    card.save(str(out / "social-preview.png"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("docs/images"))
    parser.add_argument("--cli-only", action="store_true", help="skip the GUI screenshots")
    args = parser.parse_args(argv)
    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    # A fixed, readable folder name: the paths show up in the screenshots.
    workdir = Path(tempfile.gettempdir()) / "reverbscope-readme"
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True)
    try:
        # Keep the maintainer's recent-session list untouched; fixed width, colour on.
        os.environ["REVERBSCOPE_HOME"] = str(workdir / "home")
        os.environ["COLUMNS"] = str(TERMINAL_COLUMNS)
        render_cli(workdir, out)
        if not args.cli_only:
            render_gui(workdir, out)
            render_social_preview(out)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    for path in sorted(out.iterdir()):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
