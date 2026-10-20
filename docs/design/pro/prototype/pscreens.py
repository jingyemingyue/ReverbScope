# ruff: noqa: ARG001, B023, N812
# Design-phase mockup renderer (docs only, not product code).
"""Pro-desktop key screens. Each function returns a top-level QWidget of S.W x S.H."""

from __future__ import annotations

import math

import numpy as np
import pdata as D
import pk
import pshell as P
from charts import Chart
from pk import (
    C,
    L,
    S,
    badge,
    btn,
    check,
    combo,
    hbox,
    hline,
    ico,
    lab,
    num,
    planned_badge,
    tool,
    vbox,
    vline,
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

LV = Qt.AlignmentFlag.AlignVCenter


def _fr_title(cur: str = "B-1") -> tuple[str, str]:
    return (
        f"B-1 · {L('位置 B', 'Position B')}",
        L("合成演示房间 · 48 kHz · 10月18日 21:10", "Synthetic demo room · 48 kHz · Oct 18 21:10"),
    )


def _smoothing_controls(compact: int = 0) -> list:
    items = [pk.labelled(L("平滑", "Smoothing"), combo("1/6 oct", 78, mono=True))]
    if compact < 2:
        items.append(check(L("对齐电平", "Align levels"), False))
    if compact == 0:
        items.append(check(L("原始曲线", "Raw curve"), False))
    return items


def fr_chart(
    show_x_label: bool = True,
    cross: float | None = 109.7,
    raw: bool = False,
    overlay_a: bool = True,
    annotate: bool = False,
    sparse: bool = False,
) -> Chart:
    ch = Chart(
        "freq",
        L("频率（Hz）", "Frequency (Hz)"),
        L("电平（dB，相对）", "Level (dB, relative)"),
        show_x_label=show_x_label,
    )
    lo, hi = D.excitation("b")
    ch.x_freq(20, 20000, sparse=sparse)
    ch.y_lin(-20, 30, 10, 2)
    ch.shade(20, lo)
    ch.shade(hi, 20000)
    if overlay_a:
        g, m = D.fr("a")
        ch.curve(g, m, "series_2", 1.8, dash=[5, 3], alpha=0.9, z=1)
    if raw:
        g, m = D.fr("b", smoothed=False)
        ch.curve(g, m, "series_1", 1.0, alpha=0.35, z=0)
    g, m = D.fr("b")
    ch.curve(g, m, "series_1", 2.2, z=10)
    if cross:
        ch.crosshair(cross, D.fr_at("b", cross))
        ch.marker(cross, D.fr_at("b", cross), "series_1", 6, z=90)
        if overlay_a:
            ch.marker(cross, D.fr_at("a", cross), "series_2", 6, hollow=True, z=90)
    if annotate:
        ch.text(
            L(" 共振候选 109.7 Hz ", " Resonance 109.7 Hz "),
            125,
            D.fr_at("b", 109.7) + 1.5,
            "info",
            anchor=(0, 1),
            role="caption",
            fill="info_soft",
        )
    ch.text(L("扫频范围外", "outside sweep"), 21.5, -18.5, "faint", anchor=(0, 1), role="caption")
    return ch


def diff_chart(sparse: bool = False) -> Chart:
    ch = Chart("freq", L("频率（Hz）", "Frequency (Hz)"), L("差值（dB）", "Diff (dB)"))
    lo, hi = D.excitation("b")
    ch.x_freq(20, 20000, sparse=sparse)
    ch.y_lin(-15, 15, 10, 5)
    ch.shade(20, lo)
    ch.shade(hi, 20000)
    f, d = D.diff()
    ch.curve(f, d, "series_1", 1.8, z=10)
    ch.crosshair(109.7)
    return ch


def fr_center(
    compact: int = 0, stacked: bool = True, cross: float = 109.7, hint: str = ""
) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    v.addWidget(
        P.chart_bar(
            P.pointer_tools(compact=compact > 0),
            vline(),
            *_smoothing_controls(compact),
            right=[P.layout_switch(1 if stacked else 0), vline(), *P.fit_export(compact >= 2)],
        )
    )
    right = L(
        "显示平滑 1/6 oct · 斜线区为扫频范围外",
        "Display smoothing 1/6 oct · hatched: outside the sweep",
    )
    v.addWidget(
        P.legend_strip(
            [
                ("series_1", "B-1", False, L("当前", "current")),
                ("series_2", "A-1", True, L("基准", "baseline")),
            ],
            right if compact < 2 else "",
        )
    )
    sp = QSplitter(Qt.Orientation.Vertical)
    sp.setHandleWidth(1)
    sp.setStyleSheet(f"QSplitter::handle {{ background: {C('border')}; }}")
    sp.addWidget(fr_chart(show_x_label=not stacked, cross=cross, sparse=compact >= 2))
    if stacked:
        dw = QWidget()
        dv = QVBoxLayout(dw)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(0)
        dv.addWidget(
            P.pane_header(
                L("差值 · B-1 − A-1", "Difference · B-1 − A-1"),
                lab(L("两条都按上图所画", "both as drawn above"), "caption", "faint"),
            )
        )
        dv.addWidget(diff_chart(sparse=compact >= 2))
        sp.addWidget(dw)
        sp.setSizes([560, 220])
    v.addWidget(sp, 1)
    b, a = D.fr_at("b", cross), D.fr_at("a", cross)
    v.addWidget(
        P.readout_bar(
            [
                (f"{cross:.1f} Hz", "text"),
                (f"B-1 {D.signed(b)} dB", "series_1"),
                (f"A-1 {D.signed(a)} dB", "series_2"),
                (f"Δ {D.signed(b - a)} dB", "text"),
            ],
            right=hint
            or (
                L(
                    "显示值 · 滚轮缩放 · 拖动平移 · 双击/R 适配",
                    "Displayed values · wheel zoom · drag pan · double-click/R fit",
                )
                if compact == 0
                else ""
            ),
        )
    )
    return w


def inspector_main(highlight: str = "res") -> QWidget:
    body = vbox(
        P.quality_block(),
        hline(),
        P.key_figures("b"),
        hline(),
        P.detections("b", highlight),
        hline(),
        P.fr_params(),
        "stretch",
        spacing=8,
    )
    return P.panel(0, body)


def screen_fr_pro() -> QWidget:
    t, s = _fr_title()
    return P.window(
        P.toolbar("fr", title=t, subtitle=s),
        fr_center(),
        P.measurement_list(),
        inspector_main(),
        P.control_bar(),
    )


# ====================================================================== helpers
def _column(*parts, stretch_index: int | None = None) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    for i, p in enumerate(parts):
        if p is None:
            continue
        v.addWidget(p, 1 if i == stretch_index else 0)
    return w


def _vsplit(*widgets, sizes=None) -> QSplitter:
    sp = QSplitter(Qt.Orientation.Vertical)
    sp.setHandleWidth(1)
    sp.setStyleSheet(f"QSplitter::handle {{ background: {C('border')}; }}")
    for w in widgets:
        sp.addWidget(w)
    if sizes:
        sp.setSizes(sizes)
    return sp


def _hsplit(*widgets, sizes=None) -> QSplitter:
    sp = QSplitter(Qt.Orientation.Horizontal)
    sp.setHandleWidth(1)
    sp.setStyleSheet(f"QSplitter::handle {{ background: {C('border')}; }}")
    for w in widgets:
        sp.addWidget(w)
    if sizes:
        sp.setSizes(sizes)
    return sp


def table(
    headers: list[str],
    rows: list[list],
    widths: list[int] | None = None,
    first_left: bool = True,
    row_h: int = 22,
    num_px: int | None = None,
) -> QTableWidget:
    """rows: each cell a str or (str, color token, bold)."""
    t = QTableWidget(len(rows), len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(row_h)
    t.horizontalHeader().setFixedHeight(24)
    t.setShowGrid(False)
    t.setFrameShape(t.Shape.NoFrame)
    t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    hh = t.horizontalHeader()
    hh.setFont(pk.font("label"))
    for c in range(len(headers)):
        it = t.horizontalHeaderItem(c)
        it.setTextAlignment(
            (Qt.AlignmentFlag.AlignLeft if (c == 0 and first_left) else Qt.AlignmentFlag.AlignRight)
            | LV
        )
    from PySide6.QtGui import QBrush, QColor

    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            txt, col, bold = (
                (cell, "text", False) if isinstance(cell, str) else ((*cell, False))[:3]
            )
            it = QTableWidgetItem(txt)
            f = pk.font("control" if (c == 0 and first_left) else "num", size=num_px)
            if bold:
                f.setWeight(pk.QFont.Weight(600))
            it.setFont(f)
            it.setForeground(QBrush(QColor(C(col))))
            it.setTextAlignment(
                (
                    Qt.AlignmentFlag.AlignLeft
                    if (c == 0 and first_left)
                    else Qt.AlignmentFlag.AlignRight
                )
                | LV
            )
            if r % 2 == 1:
                it.setBackground(QBrush(QColor(C("readout_bg"))))
            t.setItem(r, c, it)
    if widths:
        for c, w in enumerate(widths):
            if w:
                t.setColumnWidth(c, w)
        hh.setStretchLastSection(True)
    else:
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.setStyleSheet(
        t.styleSheet()
        + f"QTableWidget::item {{ border-bottom: 1px solid {C('surface_alt')}; padding: 0 4px; }}"
    )
    return t


def _title():
    return _fr_title()


# ====================================================================== 02 ETC + cursors
def etc_chart(cursors: bool = True) -> Chart:
    ch = Chart(
        "lin",
        L("直达声之后的时间（ms）", "Time after direct sound (ms)"),
        L("电平（dB，相对直达声）", "Level (dB re direct)"),
    )
    ch.x_lin(-5, 100, 10, 2)
    ch.y_lin(-80, 5, 10, 5)
    r = D.result("b")["reflections"]
    lo, hi = r["analysed_window_ms"]
    ch.band(lo, hi, "accent", 16)
    ch.hline(r["threshold_db"], "muted", dash=True)
    ch.text(L("阈值 −20 dB", "threshold −20 dB"), 82, -20.5, "muted", anchor=(0, 0), role="caption")
    ch.text(
        L("搜索窗 0.8–80 ms", "search window 0.8–80 ms"),
        22,
        3.5,
        "accent_fg",
        anchor=(0, 0),
        role="caption",
    )
    e = D.etc("b")
    k = (e.time_ms > -5.2) & (e.time_ms < 101)
    ch.curve(e.time_ms[k], e.level_db[k], "series_1", 1.3, z=10)
    refl = r["reflections"][0]
    ch.marker(refl["delay_ms"], refl["relative_db"], "series_1", 8, z=60)
    ch.text(
        "#1",
        refl["delay_ms"] + 1.0,
        refl["relative_db"] + 1.0,
        "text",
        anchor=(0, 1),
        role="num_strong",
    )
    if cursors:
        ch.cursor(0.0, "A", 0.0, ytop=5)
        ch.cursor(refl["delay_ms"], "B", refl["relative_db"], dashed=True, ytop=5)
    return ch


def cursor_box(rows: list[tuple[str, str, str]], title: str) -> QWidget:
    f = pk.frame("popover")
    g = QVBoxLayout(f)
    g.setContentsMargins(10, 6, 10, 8)
    g.setSpacing(1)
    g.addWidget(hbox(lab(title, "label", "muted"), "stretch", planned_badge(), spacing=6))
    for name, a, b in rows:
        g.addWidget(
            hbox(
                lab(name, "control", "muted", width=58),
                num(a, "text", width=84),
                num(b, "text", width=70),
                spacing=4,
            )
        )
    return f


def screen_etc() -> QWidget:
    t, s = _title()
    r = D.result("b")
    refl = r["reflections"]["reflections"][0]
    c = D.speed_of_sound("b")
    path = refl["delay_ms"] / 1000 * c
    bar = P.chart_bar(
        P.pointer_tools(cursor_on=True),
        vline(),
        pk.labelled(L("显示", "Show"), combo(L("能量时间曲线", "Energy-time curve"), 112)),
        pk.labelled(L("范围", "Span"), combo(L("前 100 ms", "first 100 ms"), 92)),
        vline(),
        tool("crosshair", L("放置光标", "Place cursor"), "on"),
        right=[P.layout_switch(0), vline(), *P.fit_export()],
    )
    legend = P.legend_strip(
        [("series_1", "B-1", False, L("当前", "current"))],
        L(
            "包络：反射检测器的包络，0.1 ms 峰值保持 · t = 0 为直达声",
            "Envelope: the reflection detector's, 0.1 ms peak hold · t = 0 at direct sound",
        ),
    )
    ch = etc_chart()
    from charts import overlay

    overlay(
        ch,
        cursor_box(
            [
                ("A", "0.00 ms", "0.0 dB"),
                ("B", f"{refl['delay_ms']:.2f} ms", f"{D.neg(refl['relative_db'])} dB"),
                ("Δ  B − A", f"{refl['delay_ms']:.2f} ms", f"{D.neg(refl['relative_db'])} dB"),
                (L("声程差", "Δ path"), f"{path:.2f} m", f"c={c:.1f}"),
            ],
            L("光标读数", "Cursor readout"),
        ),
        "tr",
        24,
        34,
    )
    tbl_w = _column(
        P.pane_header(
            L("早期反射 · 0.8–80 ms，高于 −20 dB", "Early reflections · 0.8–80 ms, above −20 dB"),
            lab(L("点击一行在图上定位", "click a row to locate it"), "caption", "faint"),
        ),
        table(
            [
                "#",
                L("延迟 (ms)", "Delay (ms)"),
                L("电平 (dB)", "Level (dB)"),
                L("多走路程 (m)", "Excess path (m)"),
                L("说明", "Note"),
            ],
            [
                [
                    ("1", "text", True),
                    f"{refl['delay_ms']:.2f}",
                    D.neg(refl["relative_db"]),
                    f"{path:.2f}",
                    L("候选反射", "candidate reflection"),
                ]
            ],
            widths=[40, 110, 110, 130, 0],
        ),
        lab(
            "  "
            + L(
                "候选是高出局部扩散声级的包络峰；在密集的早期尾部，部分候选可能是统计起伏。",
                "Candidates are envelope peaks above the local diffuse level; in a dense early tail some may be fluctuations.",
            ),
            "caption",
            "faint",
        ),
        stretch_index=1,
    )
    bar.findChildren(QWidget)
    center = _column(
        bar,
        legend,
        _vsplit(ch, tbl_w, sizes=[640, 110]),
        P.readout_bar(
            [
                ("A 0.00 ms  0.0 dB", "text"),
                (f"B {refl['delay_ms']:.2f} ms  {D.neg(refl['relative_db'])} dB", "text"),
                (f"Δt {refl['delay_ms']:.2f} ms", "text"),
                (f"{L('声程差', 'Δ path')} {path:.2f} m", "text"),
            ],
            planned=True,
            right=L("Shift 拖动光标吸附到峰值", "Shift-drag snaps a cursor to a peak"),
        ),
        stretch_index=2,
    )
    body = vbox(
        P.section(L("反射检测", "Reflection detection")),
        P.kv(L("阈值", "Threshold"), "−20", "dB"),
        P.kv(L("显著度", "Prominence"), "6", "dB"),
        P.kv(L("搜索窗", "Search window"), "0.8–80", "ms", value_w=96),
        P.kv(L("直达声", "Direct sound"), "5.00", "ms"),
        P.kv(L("直达声置信度", "Direct-sound confidence"), L("高", "high"), "", value_w=64),
        P.kv(
            L("声速（20 °C 假定）", "Speed of sound (20 °C assumed)"), f"{c:.1f}", "m/s", value_w=64
        ),
        hline(),
        P.detections("b", "refl"),
        hline(),
        P.section(L("清晰度", "Clarity")),
        P.kv("C50", D.signed(D.broadband("b")["c50"]["value"]), "dB"),
        P.kv("C80", D.signed(D.broadband("b")["c80"]["value"]), "dB"),
        P.kv("D50", f"{D.broadband('b')['d50']['value']:.0f}", "%"),
        "stretch",
        spacing=1,
    )
    return P.window(
        P.toolbar("etc", title=t, subtitle=s),
        center,
        P.measurement_list(overlay_a=False),
        P.panel(1, body),
        P.control_bar(),
    )


# ====================================================================== 03 RT60 per band
BAND_HZ = [63, 125, 250, 500, 1000, 2000, 4000, 8000]


def band_colors(n: int = 8) -> list[str]:
    return [f"band_{i + 1}" for i in range(n)]


def edc_chart() -> Chart:
    ch = Chart(
        "lin",
        L("时间（s）", "Time (s)"),
        L("Schroeder 衰减（dB）", "Schroeder decay (dB)"),
        show_x_label=True,
    )
    ch.x_lin(0, 1.2, 0.1, 0.02, fmt=lambda v: f"{v:.1f}", label_every=1)
    ch.y_lin(-70, 2, 10, 5)
    cols = band_colors()
    for b, col in zip(D.bands("b"), cols, strict=False):
        t = np.asarray(b["edc_time_s"])
        y = np.asarray(b["edc_db"])
        ch.curve(t, y, col, 1.2, alpha=0.9, z=2)
    bb = D.broadband("b")
    ch.curve(np.asarray(bb["edc_time_s"]), np.asarray(bb["edc_db"]), "text", 2.0, z=10)
    for lv in (-5, -35):
        ch.hline(lv, "muted", dash=True)
    ch.text(
        L("T30 评估 −5…−35 dB", "T30 range −5…−35 dB"),
        1.19,
        -35.5,
        "muted",
        anchor=(1, 0),
        role="caption",
    )
    ch.shade(bb["truncation_time_s"], 1.2)
    ch.text(
        L("截断后 · 未参与分析", "after truncation · not analysed"),
        bb["truncation_time_s"] + 0.01,
        -66,
        "faint",
        anchor=(0, 1),
        role="caption",
    )
    return ch


def rt_chart(compare: bool = False, show_x_label: bool = True) -> Chart:
    ch = Chart(
        "freq",
        L("倍频程频带中心（Hz）", "Octave band centre (Hz)"),
        L("混响时间（s）", "Reverberation time (s)"),
        show_x_label=show_x_label,
    )
    ch.pi.setXRange(math.log10(44), math.log10(11300), padding=0)
    ch.pi.getAxis("bottom").setTicks(
        [[(math.log10(f), (f"{f // 1000}k" if f >= 1000 else str(f))) for f in BAND_HZ], []]
    )
    ch._vlines([math.log10(f) for f in BAND_HZ], "plot_grid_major")
    ch.y_lin(0, 1.0, 0.2, 0.05, fmt=lambda v: f"{v:.1f}", zero=False)
    x = np.asarray(BAND_HZ, float)

    def series(pos, metric, color, dash, sym, width=1.8):
        vals = [b[metric]["seconds"] for b in D.bands(pos)]
        valid = [b[metric]["validity"] == "valid" for b in D.bands(pos)]
        y = np.asarray([v if ok else np.nan for v, ok in zip(vals, valid, strict=False)], float)
        ch.curve(x, y, color, width, dash=dash, z=5)
        for xi, v, ok in zip(x, vals, valid, strict=False):
            if v is not None:
                ch.marker(xi, v, color, 7, hollow=not ok, symbol=sym)
                if not ok:
                    ch.text("?", xi * 1.06, v + 0.012, "warn", anchor=(0, 1), role="num_strong")

    if compare:
        series("a", "t30", "series_2", [5, 3], "o")
        series("b", "t30", "series_1", False, "o", 2.2)
    else:
        series("b", "edt", "series_1", [1.5, 2.5], "t", 1.4)
        series("b", "t20", "series_1", [5, 3], "s", 1.4)
        series("b", "t30", "series_1", False, "o", 2.2)
        bb = D.broadband("b")["t30"]["seconds"]
        ch.hline(bb, "muted", dash=True)
        ch.text(
            L(f"宽带 T30 {bb:.2f} s", f"broadband T30 {bb:.2f} s"),
            9800,
            bb + 0.01,
            "muted",
            anchor=(1, 1),
            role="caption",
        )
    return ch


def rt_table(compact_cols: bool = False) -> QTableWidget:
    rows = []
    for b in [D.broadband("b"), *D.bands("b")]:

        def m(k):
            d = b[k]
            if d["seconds"] is None:
                return ("—", "faint")
            if d["validity"] != "valid":
                return (f"({d['seconds']:.2f})?", "warn")
            return (f"{d['seconds']:.2f}", "text")

        label = L("宽带", "Broadband") if b["band_label"] == "broadband" else b["band_label"]
        rows.append(
            [
                (label, "text", b["band_label"] == "broadband"),
                m("edt"),
                m("t20"),
                m("t30"),
                (f"{b['rt60_estimate_s']:.2f} ({b['rt60_basis']})", "text", True),
                D.signed(b["c50"]["value"]),
                D.signed(b["c80"]["value"]),
                f"{b['d50']['value']:.0f}",
                f"{b['centre_time']['value'] * 1000:.0f}",
                f"{b['peak_to_noise_db']:.1f}",
                D.neg(b["curvature_percent"]),
            ]
        )
    hdr = [
        L("频带", "Band"),
        "EDT (s)",
        "T20 (s)",
        "T30 (s)",
        "RT60 (s)",
        "C50 (dB)",
        "C80 (dB)",
        "D50 (%)",
        "Ts (ms)",
        L("衰减范围 (dB)", "Decay range (dB)"),
        L("曲率 (%)", "Curv. (%)"),
    ]
    return table(hdr, rows, widths=[74, 80, 70, 70, 96, 74, 74, 64, 60, 104, 0], row_h=21)


def screen_rt60() -> QWidget:
    t, s = _title()
    bar = P.chart_bar(
        P.pointer_tools(),
        vline(),
        pk.labelled(L("频带", "Band"), combo(L("全部频带", "All bands"), 92)),
        pk.labelled(L("指标", "Metric"), combo("T30", 64, mono=True)),
        check(L("评估范围", "Evaluation range"), True),
        right=[P.layout_switch(1), vline(), *P.fit_export()],
    )
    cols = band_colors()
    chips = [
        (c, b, False, "")
        for c, b in zip(cols, ["63", "125", "250", "500", "1k", "2k", "4k", "8k"], strict=False)
    ]
    legend = P.legend_strip(
        [("text", L("宽带", "Broadband"), False, ""), *chips],
        L("B-1 · 每个频带的 Schroeder 曲线", "B-1 · Schroeder curve per band"),
    )
    rt_head = P.pane_header(
        L("分频带混响时间 · B-1", "Reverberation by band · B-1"),
        pk.swatch("series_1"),
        lab("T30", "caption", "muted"),
        pk.swatch("series_1", True),
        lab("T20", "caption", "muted"),
        lab("···  EDT", "caption", "muted"),
        ico("circle", 10, "warn"),
        lab(L("空心 = 不可靠，不连线", "hollow = unreliable, not joined"), "caption", "muted"),
    )
    tbl_head = P.pane_header(
        L("分频带数据表 · B-1", "Band table · B-1"),
        lab(
            L("“?” 不可靠：悬停查看原因", "“?” unreliable: hover for the reason"),
            "caption",
            "faint",
        ),
        badge(L("衰减视图内的表格 · 新布局", "Table inside Decay view · new layout"), "neutral"),
    )
    center = _column(
        bar,
        legend,
        _vsplit(
            edc_chart(),
            _column(rt_head, rt_chart(), stretch_index=1),
            _column(tbl_head, rt_table(), stretch_index=1),
            sizes=[262, 218, 242],
        ),
        P.readout_bar(
            [
                ("1 kHz", "text"),
                ("T30 0.45 s", "series_1"),
                ("T20 0.46 s", "series_1"),
                ("EDT 0.49 s", "series_1"),
            ],
            right=L(
                "63 Hz、250 Hz 的 EDT 不可靠：衰减曲线在直达声处下降超过 5 dB",
                "EDT at 63 Hz and 250 Hz unreliable: the decay drops over 5 dB across the direct sound",
            ),
        ),
        stretch_index=2,
    )
    bb = D.broadband("b")
    body = vbox(
        P.section(L("衰减分析", "Decay analysis")),
        P.kv(L("方法", "Method"), "ISO 3382-1", "", value_w=96),
        P.kv(L("T30 评估", "T30 range"), "−5…−35", "dB", value_w=80),
        P.kv(L("T20 评估", "T20 range"), "−5…−25", "dB", value_w=80),
        P.kv(L("EDT 评估", "EDT range"), "0…−10", "dB", value_w=80),
        P.kv(L("截断（宽带）", "Truncation (broadband)"), f"{bb['truncation_time_s']:.2f}", "s"),
        P.kv(L("本底噪声（宽带）", "Noise floor (bb)"), D.neg(bb["noise_floor_db"]), "dB"),
        P.kv(L("噪声余量", "Noise margin"), "10", "dB"),
        P.kv(L("曲率", "Curvature"), f"{bb['curvature_percent']:.1f}", "%"),
        hline(),
        P.section(L("宽带结果", "Broadband")),
        P.kv("RT60 (T30)", f"{bb['t30']['seconds']:.2f}", "s"),
        P.kv("EDT", f"{bb['edt']['seconds']:.2f}", "s"),
        P.kv("T20", f"{bb['t20']['seconds']:.2f}", "s"),
        hline(),
        P.section(L("提示", "Notes")),
        hbox(
            ico("triangle-alert", 12, "warn"),
            lab(L("2 个频带的 EDT 不可靠", "EDT unreliable in 2 bands"), "control", "warn"),
            "stretch",
            spacing=6,
        ),
        lab(
            L(
                "不画误差线：当前没有不确定度 σ(T)\n（路线图 A1）",
                "No error bars: no uncertainty σ(T) yet\n(roadmap A1)",
            ),
            "caption",
            "faint",
        ),
        "stretch",
        spacing=1,
    )
    return P.window(
        P.toolbar("decay", title=t, subtitle=s),
        center,
        P.measurement_list(overlay_a=False),
        P.panel(1, body),
        P.control_bar(),
    )


# ====================================================================== 04 waterfall
def waterfall_chart(selected: int = 0) -> Chart:
    w = D.waterfall("b")
    count = w.times_ms.size
    ch = Chart(
        "freq",
        L("频率（Hz）", "Frequency (Hz)"),
        L("电平（dB，相对首切片峰值）", "Level (dB re first-slice peak)"),
    )
    top_dx, top_dy = 0.22, 40.0
    ch.pi.setXRange(math.log10(20), math.log10(20000) + top_dx, padding=0)
    ticks = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
    ch.pi.getAxis("bottom").setTicks(
        [[(math.log10(f), f"{f // 1000}k" if f >= 1000 else str(f)) for f in ticks], []]
    )
    ch._vlines([math.log10(f) for f in ticks], "plot_grid_minor")
    ch.pi.setYRange(-63, 46, padding=0)
    ch.pi.getAxis("left").setTicks(
        [[(v, f"{v:g}".replace("-", "\u2212")) for v in range(-60, 1, 10)], []]
    )
    ch._hlines(list(range(-60, 1, 10)), "plot_grid_minor")
    import pyqtgraph as pg

    cm = pg.colormap.get("viridis")
    for i in range(count - 1, -1, -1):
        dx, dy = top_dx * i / (count - 1), top_dy * i / (count - 1)
        col = cm.map(i / (count - 1), mode="qcolor").name()
        keep = w.freqs_hz <= 20000
        f = w.freqs_hz[keep] * 10**dx
        y = w.levels_db[i][keep] + dy
        sel = i == selected
        ch.curve(
            f,
            y,
            "cursor" if sel else col,
            2.2 if sel else 1.0,
            z=(count - i) * 2 + (200 if sel else 0),
            fill_to=-60 + dy,
            fill_token="plot_bg",
        )
    return ch


def colorbar(w: int = 140) -> QWidget:
    import pyqtgraph as pg
    from PySide6.QtGui import QLinearGradient, QPainter

    cm = pg.colormap.get("viridis")
    bar = QWidget()
    bar.setFixedSize(w, 10)

    def paint(ev, bar=bar):
        p = QPainter(bar)
        g = QLinearGradient(0, 0, bar.width(), 0)
        for k in range(11):
            g.setColorAt(k / 10, cm.map(k / 10, mode="qcolor"))
        p.fillRect(bar.rect(), g)
        p.end()

    bar.paintEvent = paint  # type: ignore[assignment]
    return hbox(lab("0", "tick", "muted"), bar, lab("290 ms", "tick", "muted"), spacing=4)


def screen_waterfall() -> QWidget:
    t, s = _title()
    w = D.waterfall("b")
    lv = w.levels_db[0]
    pk_i = int(np.nanargmax(lv))
    bar = P.chart_bar(
        P.pointer_tools(),
        vline(),
        pk.labelled(L("窗", "Window"), combo("300 ms", 76, mono=True)),
        pk.labelled(L("上升", "Rise"), combo("0.5 ms", 72, mono=True)),
        pk.labelled(L("步长", "Step"), combo("10 ms", 68, mono=True)),
        pk.labelled(L("切片", "Slices"), combo("30", 48, mono=True)),
        pk.labelled(L("平滑", "Smoothing"), combo(L("无", "none"), 56)),
        check(L("透视", "Perspective"), True),
        right=[P.layout_switch(0), vline(), *P.fit_export(True)],
    )
    legend = P.legend_strip(
        [],
        L(
            "累积频谱衰减 · B-1 · 每条切片下方遮挡（新增）",
            "Cumulative spectral decay · B-1 · slices occlude those behind (new)",
        ),
        right_widget=hbox(16, colorbar(), spacing=0),
    )
    slider = hbox(
        pk.spacer_w(10),
        lab(L("切片", "Slice"), "control", "muted"),
        _slider(0.0),
        num("0.0 ms", "text", width=60),
        lab(
            L(
                f"峰值 {D.signed(float(lv[pk_i]))} dB，位于 {w.freqs_hz[pk_i]:.1f} Hz",
                f"peak {D.signed(float(lv[pk_i]))} dB at {w.freqs_hz[pk_i]:.1f} Hz",
            ),
            "num",
            "muted",
        ),
        "stretch",
        spacing=8,
    )
    slider.setFixedHeight(30)
    slider.setStyleSheet(f"background:{C('plot_bg')};")
    center = _column(
        bar,
        legend,
        waterfall_chart(0),
        slider,
        P.readout_bar(
            [
                ("0.0 ms", "text"),
                ("109.8 Hz", "text"),
                (f"{D.signed(float(lv[pk_i]))} dB", "cursor"),
            ],
            right=L(
                "仅显示变换：从已存脉冲响应计算，后台线程，按测量缓存",
                "Display transform: computed from the stored IR in a worker, cached per measurement",
            ),
        ),
        stretch_index=2,
    )
    body = vbox(
        P.section(L("变换参数", "Transform")),
        P.kv(L("窗长", "Window"), "300", "ms"),
        P.kv(L("上升", "Rise"), "0.5", "ms"),
        P.kv(L("渐变", "Taper"), "25", "%"),
        P.kv(L("起点", "Start"), "0", "ms"),
        P.kv(L("步长", "Step"), "10", "ms"),
        P.kv(L("切片数", "Slices"), "30", ""),
        P.kv(L("每倍频程点数", "Points / octave"), "48", ""),
        P.kv(L("显示下限", "Floor"), "−60", "dB"),
        hline(),
        P.section(L("说明", "Notes")),
        lab(
            L(
                "纵轴相对第一条切片的峰值；透视偏移\n只是显示位移（0.22 dec，40 dB）。",
                "Levels re first-slice peak; perspective is a\ndisplay shift only (0.22 dec, 40 dB).",
            ),
            "caption",
            "muted",
        ),
        hline(),
        P.detections("b", "res"),
        "stretch",
        spacing=1,
    )
    return P.window(
        P.toolbar("waterfall", title=t, subtitle=s),
        center,
        P.measurement_list(overlay_a=False),
        P.panel(1, body),
        P.control_bar(),
    )


def _slider(frac: float, w: int = 260) -> QWidget:
    from PySide6.QtGui import QColor, QPainter

    s = QWidget()
    s.setFixedSize(w, 16)

    def paint(ev, s=s):
        p = QPainter(s)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(0, 7, s.width(), 3, QColor(C("surface_alt")))
        x = int(frac * (s.width() - 12))
        p.setBrush(QColor(C("surface")))
        p.setPen(QColor(C("border_strong")))
        p.drawEllipse(x, 2, 12, 12)
        p.end()

    s.paintEvent = paint  # type: ignore[assignment]
    return s


# ====================================================================== 05 compare, dual chart
def screen_compare() -> QWidget:
    _t, _s = _title()
    bar = P.chart_bar(
        P.pointer_tools(),
        vline(),
        *_smoothing_controls(1),
        vline(),
        check(L("联动横轴光标", "Link cursors"), True),
        right=[
            P.layout_switch(2),
            planned_badge(L("并排 未实现", "Side-by-side planned")),
            vline(),
            *P.fit_export(True),
        ],
    )
    legend = P.legend_strip(
        [
            ("series_1", "B-1", False, L("当前", "current")),
            ("series_2", "A-1", True, L("基准", "baseline")),
        ],
        L("两个窗格画同一组测量", "Both panes draw the same measurements"),
    )
    left = _column(
        P.pane_header(
            L("左 · 频率响应", "Left · Frequency response"),
            combo(L("频率响应", "Frequency"), 84, flat=True),
        ),
        fr_chart(cross=1000, sparse=True),
        stretch_index=1,
    )
    right = _column(
        P.pane_header(L("右 · 分频带 T30", "Right · T30 by band"), combo("RT60", 62, flat=True)),
        rt_chart(compare=True),
        stretch_index=1,
    )
    sp = _hsplit(left, right, sizes=[466, 464])
    a1, b1 = D.fr_at("a", 1000), D.fr_at("b", 1000)
    ta = D.bands("a")[4]["t30"]["seconds"]
    tb = D.bands("b")[4]["t30"]["seconds"]
    center = _column(
        bar,
        legend,
        sp,
        P.readout_bar(
            [
                ("1.00 kHz", "text"),
                (f"B-1 {D.signed(b1)} dB", "series_1"),
                (f"A-1 {D.signed(a1)} dB", "series_2"),
                (f"1 kHz T30  A-1 {ta:.2f} s → B-1 {tb:.2f} s", "text"),
            ]
        ),
        stretch_index=2,
    )

    # compare panel
    def row(name, key, unit, digits=2, scale=1.0):
        r = D.cmp_row(key)
        a, b, d = r["baseline"] * scale, r["candidate"] * scale, (r["delta"] or 0) * scale
        pct = r.get("delta_percent")
        return [
            name,
            f"{a:.{digits}f}",
            f"{b:.{digits}f}",
            D.signed(d, digits),
            "—" if pct is None else D.signed(pct, 0) + " %",
        ]

    rows = [
        row("T30 (s)", "broadband.t30", "s"),
        row("T20 (s)", "broadband.t20", "s"),
        row("EDT (s)", "broadband.edt", "s"),
        row("C50 (dB)", "broadband.c50", "dB", 1),
        row("C80 (dB)", "broadband.c80", "dB", 1),
        row("Ts (ms)", "broadband.centre_time", "ms", 1, 1000),
        row(L("噪声", "Noise"), "noise.rms_dbfs", "dBFS", 1),
    ]
    tw = table(
        [L("宽带", "Broadband"), "A-1", "B-1", "Δ", "Δ%"],
        rows,
        widths=[58, 48, 48, 50, 52],
        row_h=21,
        num_px=11,
    )
    tw.setFixedHeight(24 + 21 * len(rows) + 2)
    refl = vbox(
        P.section(L("早期反射", "Early reflections")),
        hbox(
            ico("minus", 12, "muted"),
            lab(L("消失 2.4 ms −3.1 dB", "gone 2.4 ms −3.1 dB"), "num", "muted"),
            spacing=6,
        ),
        hbox(
            ico("minus", 12, "muted"),
            lab(L("消失 7.1 ms −9.6 dB", "gone 7.1 ms −9.6 dB"), "num", "muted"),
            spacing=6,
        ),
        hbox(
            ico("plus", 12, "muted"),
            lab(L("出现 9.3 ms −14.5 dB", "new 9.3 ms −14.5 dB"), "num", "muted"),
            spacing=6,
        ),
        P.section(L("共振", "Resonance")),
        hbox(
            ico("equal", 12, "muted"),
            lab(L("匹配 109.9 → 109.7 Hz", "matched 109.9 → 109.7 Hz"), "num", "muted"),
            spacing=6,
        ),
        spacing=2,
    )
    body = vbox(
        hbox(
            lab(L("A-1 → B-1", "A-1 → B-1"), "heading"),
            "stretch",
            lab(L("同一输入增益", "same input gain"), "caption", "muted"),
            spacing=6,
        ),
        tw,
        lab(
            L(
                "混响时间可感知差约 5 %（ISO 3382-1）。\n单对位置不判断“显著”。",
                "JND for reverberation time ≈ 5 % (ISO 3382-1).\nA single pair is not called significant.",
            ),
            "caption",
            "faint",
        ),
        hline(),
        refl,
        hline(),
        P.section(L("公共频带", "Common band")),
        P.kv(L("频率", "Frequency"), "30.6–19.7k", "Hz", value_w=96),
        "stretch",
        spacing=6,
    )
    return P.window(
        P.toolbar(
            "fr",
            title=L("对比 · A-1 → B-1", "Compare · A-1 → B-1"),
            subtitle=L("合成演示房间 · 两个位置", "Synthetic demo room · two positions"),
        ),
        center,
        P.measurement_list(),
        P.panel(2, body),
        P.control_bar(),
    )


# ====================================================================== 06 guided (normal mode)
def screen_guided() -> QWidget:
    t, s = _title()
    guide = P.chart_bar(
        ico("lightbulb", 14, "accent_fg"),
        lab(
            L(
                "这张图：房间让每个频率变响或变轻了多少。越接近平直越好；斜线区没有测到。",
                "This chart: how much the room makes each frequency louder or quieter. Flatter is better; hatched areas were not measured.",
            ),
            "control",
        ),
        right=[
            check(L("显示上次（A-1）", "Show previous (A-1)"), True),
            tool("maximize", L("适配", "Fit"), icon_color="muted"),
            tool("download", icon_color="muted"),
        ],
    )
    ch = Chart(
        "freq",
        L("频率（Hz）· 低音 ← → 高音", "Frequency (Hz) · bass ← → treble"),
        L("响度（dB）", "Loudness (dB)"),
    )
    lo, hi = D.excitation("b")
    ch.x_freq(20, 20000, sparse=False)
    ch.y_lin(-20, 30, 10, 10)
    ch.shade(20, lo)
    ch.shade(hi, 20000)
    g, m = D.fr("a")
    ch.curve(g, m, "series_2", 1.6, dash=[5, 3], alpha=0.8, z=1)
    g, m = D.fr("b")
    ch.curve(g, m, "series_1", 2.4, z=10)
    ch.band(80, 150, "info", 26)
    ch.marker(109.7, D.fr_at("b", 109.7), "info", 9, z=95)
    from charts import overlay

    call = pk.frame("popover")
    cl = QVBoxLayout(call)
    cl.setContentsMargins(10, 8, 10, 8)
    cl.setSpacing(2)
    cl.addWidget(
        hbox(
            lab("1", "num_strong", "info"),
            lab(L("低音在 110 Hz 附近堆积", "Bass builds up near 110 Hz"), "control_strong"),
            "stretch",
            spacing=6,
        )
    )
    cl.addWidget(
        lab(
            L(
                "比周围响约 11 dB，低音会发闷、发轰。\n换个位置再测，看它会不会变。",
                "About 11 dB louder than around it; bass can sound boomy.\nMeasure another spot and see whether it moves.",
            ),
            "caption",
            "muted",
        )
    )
    overlay(ch, call, "tl", 300, 26)
    legend = P.legend_strip(
        [
            ("series_1", L("这次 B-1", "This one B-1"), False, ""),
            ("series_2", L("上次 A-1", "Previous A-1"), True, ""),
        ]
    )
    center = _column(
        guide,
        legend,
        ch,
        P.readout_bar(
            [
                (
                    L(
                        "指着 110 Hz：这次 +16.1 dB · 上次 +25.4 dB",
                        "At 110 Hz: this one +16.1 dB · previous +25.4 dB",
                    ),
                    "text",
                )
            ],
            right=L("想看更多参数？切到“专业”", "More detail? Switch to Pro"),
        ),
        stretch_index=2,
    )

    def step(n, title, body, tone="muted", link=""):
        return vbox(
            hbox(
                lab(str(n), "num_strong", "accent_fg", width=14),
                lab(title, "control_strong"),
                "stretch",
                lab(link, "control", "accent_fg") if link else None,
                spacing=6,
            ),
            lab(body, "caption", "muted"),
            spacing=1,
        )

    body = vbox(
        P.section(L("这次测得怎么样", "How this went")),
        hbox(
            pk.status_icon("warn", 13),
            lab(L("能用，有 1 个提醒", "Usable, 1 thing to check"), "control_strong", "warn"),
            spacing=6,
        ),
        lab(
            L(
                "录音太响，差点削波。下次把音量调小一点。",
                "The recording was nearly too loud. Turn it down a bit next time.",
            ),
            "caption",
            "muted",
        ),
        hline(),
        P.section(L("房间的三件事", "Three things about the room")),
        step(
            1,
            L("低音堆积 110 Hz", "Bass build-up at 110 Hz"),
            L("会让人声和贝斯发闷", "Makes voice and bass boomy"),
            link=L("在图上 →", "Show →"),
        ),
        step(
            2,
            L("余音 0.51 秒", "Room echo 0.51 s"),
            L(
                "对录人声略长（人声配置上限 0.5 s）",
                "A bit long for voice (vocal profile: up to 0.5 s)",
            ),
            link=L("混响 →", "Reverb →"),
        ),
        step(
            3,
            L("50 Hz 电源嗡声", "50 Hz mains hum"),
            L("先查线材和电源，再做声学处理", "Check cables and power before treatment"),
            link=L("看看 →", "Look →"),
        ),
        hline(),
        P.section(L("下一步", "Next")),
        btn(L("在另一个位置测量", "Measure at another spot"), "btn", "", "plus"),
        btn(L("和上次对比", "Compare with previous"), "btn", "", "git-compare"),
        "stretch",
        spacing=6,
    )
    return P.window(
        P.toolbar("fr", title=t, subtitle=s, plain=True),
        center,
        P.measurement_list(plain=True),
        P.panel(0, body, tabs=[L("解读", "Explain"), L("帮助", "Help")]),
        P.control_bar(plain=True),
    )


# ====================================================================== 07 measuring
def screen_measuring() -> QWidget:
    t, s = _title()
    banner = pk.frame("banner")
    bl = pk.QHBoxLayout(banner)
    bl.setContentsMargins(10, 4, 10, 4)
    bl.setSpacing(8)
    bl.addWidget(ico("activity", 14, "accent_fg"))
    bl.addWidget(
        lab(
            L("正在测量 B-2（位置 B）", "Measuring B-2 (position B)"), "control_strong", "accent_fg"
        )
    )
    bl.addWidget(
        lab(
            L(
                "完成后自动分析并加入叠加 · 切换视图不会中断 · Esc 停止并静音输出",
                "Analysed and overlaid when done · switching views does not stop it · Esc stops and silences the output",
            ),
            "control",
            "muted",
        )
    )
    bl.addStretch(1)
    wrap = hbox(banner, margins=(8, 6, 8, 6))
    wrap.setStyleSheet(f"background:{C('plot_bg')};")
    w = fr_center(stacked=True)
    center = _column(wrap, w, stretch_index=1)
    return P.window(
        P.toolbar("fr", title=t, subtitle=s, measuring=True),
        center,
        P.measurement_list(measuring=True),
        inspector_main(),
        P.control_bar("measuring"),
    )


# ====================================================================== 08 narrow, 09 minimum
def screen_narrow() -> QWidget:
    t, s = _title()
    return P.window(
        P.toolbar("fr", title=t, subtitle=s, panel_open=False, compact=1),
        fr_center(
            compact=1,
            hint=L(
                "窗口 < 1280：检查器已收起 · ⇧⌘→ 以浮层打开",
                "Window < 1280: inspector hidden · ⇧⌘→ opens it as an overlay",
            ),
        ),
        P.measurement_list(),
        None,
        P.control_bar(compact=1),
    )


def screen_minimum() -> QWidget:
    t, s = _title()
    return P.window(
        P.toolbar("fr", title=t, subtitle=s, list_open=False, panel_open=False, compact=2),
        fr_center(compact=2, hint=L("< 1024：列表收为图标栏", "< 1024: list collapsed to a rail")),
        P.rail(),
        None,
        P.control_bar(compact=2),
    )


# ====================================================================== 10 component states
def screen_states() -> QWidget:
    from PySide6.QtWidgets import QGridLayout, QProgressBar

    root = QWidget()
    root.setObjectName("window")
    root.setFixedSize(S.W, S.H)
    root.setStyleSheet(pk.qss())
    outer = QVBoxLayout(root)
    outer.setContentsMargins(24, 18, 24, 18)
    outer.setSpacing(10)
    outer.addWidget(
        hbox(
            lab(L("组件状态", "Component states"), "heading", size=15),
            lab(
                L(
                    "浅色" if S.theme == "light" else "深色",
                    "Light" if S.theme == "light" else "Dark",
                ),
                "control",
                "muted",
            ),
            "stretch",
            lab(
                "IBM Plex Sans / Source Han Sans CN · IBM Plex Mono · Lucide 1.75",
                "caption",
                "faint",
            ),
            spacing=10,
        )
    )

    card = pk.frame("popover")
    g = QGridLayout(card)
    g.setContentsMargins(16, 12, 16, 12)
    g.setHorizontalSpacing(18)
    g.setVerticalSpacing(10)
    states = [
        ("", L("默认", "Default")),
        ("hover", L("悬停", "Hover")),
        ("pressed", L("按下", "Pressed")),
        ("disabled", L("禁用", "Disabled")),
        ("focus", L("键盘焦点", "Focus")),
        ("on", L("开启（切换）", "On (toggle)")),
    ]
    g.addWidget(lab("", "label"), 0, 0)
    for c, (_s, name) in enumerate(states):
        g.addWidget(lab(name, "label", "muted"), 0, c + 1)
    rows = [
        (L("次要按钮", "Secondary"), lambda st: btn(L("导出", "Export"), "btn", st, "download")),
        (
            L("主按钮（每屏最多 1 个）", "Primary (max 1)"),
            lambda st: (
                btn(L("开始测量", "Measure"), "primary", st, "play")
                if st != "on"
                else lab("—", "control", "faint")
            ),
        ),
        (L("工具按钮", "Tool"), lambda st: tool("maximize", L("适配", "Fit"), st)),
        (L("图标工具", "Icon tool"), lambda st: tool("crosshair", "", st)),
    ]
    for r, (name, make) in enumerate(rows, start=1):
        g.addWidget(lab(name, "control"), r, 0)
        for c, (st, _n) in enumerate(states):
            g.addWidget(make(st), r, c + 1, Qt.AlignmentFlag.AlignLeft)
    r = len(rows) + 1
    g.addWidget(lab(L("分段控件", "Segmented"), "control"), r, 0)
    g.addWidget(
        pk.seg(["1/3", "1/6", "1/12", L("无", "none")], 1), r, 1, 1, 3, Qt.AlignmentFlag.AlignLeft
    )
    g.addWidget(P.layout_switch(1), r, 4, Qt.AlignmentFlag.AlignLeft)
    g.addWidget(
        lab(L("紫点 = 未实现的选项", "Purple dot = planned option"), "caption", "muted"), r, 5, 1, 2
    )
    r += 1
    g.addWidget(lab(L("输入", "Inputs"), "control"), r, 0)
    g.addWidget(combo("1/6 oct", 84, mono=True), r, 1, Qt.AlignmentFlag.AlignLeft)
    le = pk.QLineEdit("B-1")
    le.setFixedSize(110, 24)
    g.addWidget(le, r, 2, Qt.AlignmentFlag.AlignLeft)
    lf = pk.QLineEdit("−130")
    lf.setFixedSize(84, 24)
    lf.setStyleSheet(
        f"border: 2px solid {C('focus')}; border-radius: 4px; font-family: 'IBM Plex Mono';"
    )
    g.addWidget(lf, r, 3, Qt.AlignmentFlag.AlignLeft)
    le2 = pk.QLineEdit("3.0 s")
    le2.setFixedSize(84, 24)
    le2.setStyleSheet(
        f"border: 1px solid {C('bad')}; border-radius: 4px; background:{C('bad_soft')};"
    )
    g.addWidget(le2, r, 4, Qt.AlignmentFlag.AlignLeft)
    g.addWidget(
        hbox(check(L("关", "Off"), False), check(L("开", "On"), True), spacing=10),
        r,
        5,
        1,
        2,
        Qt.AlignmentFlag.AlignLeft,
    )
    outer.addWidget(card)

    mid = QWidget()
    mh = pk.QHBoxLayout(mid)
    mh.setContentsMargins(0, 0, 0, 0)
    mh.setSpacing(12)
    # list rows
    lr = pk.frame("popover")
    lv = QVBoxLayout(lr)
    lv.setContentsMargins(10, 10, 10, 10)
    lv.setSpacing(3)
    lv.addWidget(lab(L("测量列表行", "Measurement rows"), "heading"))
    for txt, kw in (
        (L("默认", "default"), {}),
        (L("悬停", "hover"), {"hover": True}),
        (L("选中", "selected"), {"sel": True}),
        (L("未保存", "unsaved"), {"unsaved": True}),
        (L("测量中", "measuring"), {"measuring": True}),
    ):
        row = P._meas_row(
            "B-1" if not kw.get("measuring") else "B-2",
            "series_1" if not kw.get("measuring") else "series_3",
            "0.51 s" if not kw.get("measuring") else "—",
            "warn" if not kw.get("measuring") else "",
            sel=kw.get("sel", False),
            unsaved=kw.get("unsaved", False) or kw.get("measuring", False),
            extra=ico("activity", 12, "accent") if kw.get("measuring") else None,
        )
        if kw.get("hover"):
            row.setProperty("hover", "true")
        row.setFixedWidth(220)
        lv.addWidget(hbox(lab(txt, "caption", "muted", width=48), row, spacing=6))
    lv.addStretch(1)
    mh.addWidget(lr)
    # badges / validity
    bd = pk.frame("popover")
    bv = QVBoxLayout(bd)
    bv.setContentsMargins(10, 10, 10, 10)
    bv.setSpacing(6)
    bv.addWidget(lab(L("徽章、状态与有效性", "Badges, status, validity"), "heading"))
    bv.addWidget(
        hbox(
            planned_badge(),
            pk.synthetic_badge(),
            badge(L("新布局", "New layout"), "neutral"),
            "stretch",
            spacing=6,
        )
    )
    for tone, txt in (
        ("good", L("良好", "Good")),
        ("warn", L("提醒", "Warning")),
        ("bad", L("无效", "Invalid")),
        ("info", L("提示", "Notice")),
    ):
        bv.addWidget(hbox(pk.status_icon(tone), lab(txt, "control", tone), "stretch", spacing=6))
    bv.addWidget(
        hbox(
            lab(L("不可靠", "Unreliable"), "control", "muted", width=70),
            num("(0.69)?", "warn"),
            lab(L("灰括号 + ?，悬停说明原因", "brackets + ?, reason on hover"), "caption", "faint"),
            "stretch",
            spacing=6,
        )
    )
    bv.addWidget(
        hbox(
            lab(L("未计算", "Not computed"), "control", "muted", width=70),
            num("—", "faint"),
            "stretch",
            spacing=6,
        )
    )
    bv.addStretch(1)
    mh.addWidget(bd, 1)
    # feedback
    fb = pk.frame("popover")
    fv = QVBoxLayout(fb)
    fv.setContentsMargins(10, 10, 10, 10)
    fv.setSpacing(6)
    fv.addWidget(
        lab(
            L("反馈：进行中、警告、错误、完成", "Feedback: running, warning, error, done"),
            "heading",
        )
    )

    def banner(tone, icon, title, body):
        f = pk.frame("banner", tone=tone)
        h = pk.QHBoxLayout(f)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(6)
        col = {"": "accent_fg", "warn": "warn", "bad": "bad"}[tone]
        h.addWidget(ico(icon, 13, col))
        h.addWidget(lab(title, "control_strong", col))
        h.addWidget(lab(body, "caption", "muted"))
        h.addStretch(1)
        return f

    fv.addWidget(
        banner(
            "",
            "activity",
            L("正在分析 B-2", "Analysing B-2"),
            L("播放已结束 · 结果完成后自动显示", "playback finished · shown when done"),
        )
    )
    pb = QProgressBar()
    pb.setRange(0, 100)
    pb.setValue(62)
    pb.setTextVisible(False)
    pb.setFixedHeight(4)
    fv.addWidget(pb)
    fv.addWidget(
        banner(
            "warn",
            "triangle-alert",
            L("峰值 +2.6 dBFS", "Peak +2.6 dBFS"),
            L(
                "余量不足 1 dB → 降低约 6 dB 后重测",
                "under 1 dB headroom → lower ~6 dB, measure again",
            ),
        )
    )
    fv.addWidget(
        banner(
            "bad",
            "circle-x",
            L("无法分析", "Cannot analyse"),
            L(
                "录音比参考扫频短；该文件没有包含完整的扫频",
                "recording is shorter than the reference sweep",
            ),
        )
    )
    toast = pk.frame("popover")
    th = pk.QHBoxLayout(toast)
    th.setContentsMargins(10, 5, 8, 5)
    th.setSpacing(8)
    th.addWidget(pk.status_icon("good"))
    th.addWidget(lab(L("已保存 B-1", "Saved B-1"), "control"))
    th.addWidget(lab(L("在 Finder 中显示", "Show in Finder"), "control", "accent_fg"))
    th.addStretch(1)
    fv.addWidget(hbox(lab("Toast", "caption", "faint", width=40), toast, "stretch", spacing=6))
    fv.addStretch(1)
    mh.addWidget(fb, 1)
    outer.addWidget(mid)

    bot = QWidget()
    bh = pk.QHBoxLayout(bot)
    bh.setContentsMargins(0, 0, 0, 0)
    bh.setSpacing(12)
    from charts import overlay

    def empty_chart(icon, title, body, action):
        ch = Chart("freq", L("频率（Hz）", "Frequency (Hz)"), "dB")
        ch.x_freq(20, 20000, sparse=True)
        ch.y_lin(-20, 30, 10, 10)
        es = QWidget()
        ev = QVBoxLayout(es)
        ev.setContentsMargins(0, 0, 0, 0)
        ev.setSpacing(4)
        ev.addWidget(ico(icon, 20, "muted"), 0, Qt.AlignmentFlag.AlignHCenter)
        ev.addWidget(lab(title, "control_strong"), 0, Qt.AlignmentFlag.AlignHCenter)
        ev.addWidget(lab(body, "caption", "muted"), 0, Qt.AlignmentFlag.AlignHCenter)
        if action:
            ev.addWidget(action, 0, Qt.AlignmentFlag.AlignHCenter)
        es.setStyleSheet(f"background:{C('plot_bg')};")
        overlay(ch, es, "c")
        box = _column(P.pane_header(title), ch, stretch_index=1)
        f = pk.frame("popover")
        fl = QVBoxLayout(f)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.addWidget(box)
        return f

    bh.addWidget(
        empty_chart(
            "chart-line",
            L("还没有测量", "No measurement yet"),
            L("⌘↩ 开始测量，或 ⌘O 打开已保存的测量", "⌘↩ to measure, or ⌘O to open a saved one"),
            btn(L("打开…", "Open…"), "btn", "", "folder-open"),
        ),
        1,
    )
    bh.addWidget(
        empty_chart(
            "circle-slash",
            L("这个测量没有保存频率响应", "No frequency response stored with this session"),
            L(
                "其他视图仍可用；重新分析录音可以补上",
                "Other views still work; re-analyse the recording to add it",
            ),
            None,
        ),
        1,
    )
    cur = Chart("lin", "ms", "dB")
    cur.x_lin(0, 20, 5, 1)
    cur.y_lin(-40, 5, 10, 5)
    e = D.etc("b")
    k = (e.time_ms >= 0) & (e.time_ms <= 20)
    cur.curve(e.time_ms[k], e.level_db[k], "series_1", 1.3)
    cur.crosshair(4.0, -27.0)
    cur.cursor(0.0, "A", 0.0, ytop=5)
    cur.cursor(9.29, "B", -14.5, dashed=True, ytop=5)
    cf = pk.frame("popover")
    cl = QVBoxLayout(cf)
    cl.setContentsMargins(1, 1, 1, 1)
    cl.addWidget(
        _column(
            P.pane_header(
                L(
                    "悬停十字线（已实现）· 放置光标 A/B（未实现）",
                    "Hover crosshair (implemented) · cursors A/B (planned)",
                )
            ),
            cur,
            stretch_index=1,
        )
    )
    bh.addWidget(cf, 1)
    outer.addWidget(bot, 1)
    return root
