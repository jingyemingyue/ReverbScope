# ruff: noqa: ARG001, N812, RUF034
# Design-phase mockup renderer (docs only, not product code).
"""Window skeleton for the pro mockups: toolbar, measurement list, chart column,
inspector panel, control bar. Layout values are pk.SIZE (see DESIGN_SYSTEM.md)."""

from __future__ import annotations

import pdata as D
import pk
from pk import (
    SIZE,
    C,
    L,
    S,
    badge,
    btn,
    check,
    combo,
    dot,
    frame,
    hbox,
    hline,
    ico,
    lab,
    num,
    planned_badge,
    seg,
    status_icon,
    swatch,
    synthetic_badge,
    tool,
    vbox,
    vline,
)
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QToolButton, QVBoxLayout, QWidget

# ------------------------------------------------------------------ view switcher
VIEWS_PRO = [
    ("overview", ("概览", "Overview")),
    ("fr", ("频率响应", "Frequency")),
    ("etc", ("ETC", "ETC")),
    ("decay", ("RT60", "RT60")),
    ("noise", ("噪声", "Noise")),
    ("spectrogram", ("声谱图", "Spectrogram")),
    ("waterfall", ("瀑布图", "Waterfall")),
]
VIEWS_PLAIN = [
    ("overview", ("结论", "Summary")),
    ("fr", ("频率", "Frequency")),
    ("decay", ("混响", "Reverb")),
    ("etc", ("反射", "Reflections")),
]


def view_switcher(current: str, compact: int = 0, plain: bool = False) -> QFrame:
    views = VIEWS_PLAIN if plain else VIEWS_PRO
    if compact >= 2 and not plain:
        views = [v for v in views if v[0] not in ("overview", "spectrogram", "noise")]
    names = [L(*v[1]) for v in views]
    idx = [v[0] for v in views].index(current)
    f = seg(names, idx)
    if compact >= 2 and not plain:
        more = QToolButton()
        more.setProperty("role", "segbtn")
        more.setIcon(pk.ipix("ellipsis", 14, "muted"))
        more.setFixedHeight(22)
        f.layout().addWidget(more)
    return f


def toolbar(
    view: str,
    *,
    title: str,
    subtitle: str,
    list_open: bool = True,
    panel_open: bool = True,
    compact: int = 0,
    plain: bool = False,
    measuring: bool = False,
) -> QFrame:
    tb = frame("toolbar")
    tb.setFixedHeight(SIZE["toolbar_h"])
    lay = QHBoxLayout(tb)
    lay.setContentsMargins(16, 0, 10, 0)
    lay.setSpacing(6)
    lay.addWidget(pk.traffic_lights())
    lay.addSpacing(10)
    lay.addWidget(tool("panel-left", state="" if list_open else "", icon_color="muted"))
    lay.addSpacing(4)
    tw = 200 if compact == 0 else 150 if compact == 1 else 120
    tblock = vbox(lab(title, "window_title"), lab(subtitle, "caption", "muted"), spacing=0)
    for w in tblock.findChildren(type(lab(""))):
        w.setFixedWidth(tw)
        fm = w.fontMetrics()
        w.setText(fm.elidedText(w.text(), Qt.TextElideMode.ElideRight, tw))
    lay.addWidget(tblock)
    lay.addStretch(1)
    lay.addWidget(view_switcher(view, compact, plain))
    lay.addStretch(1)
    if measuring:
        lay.addWidget(badge(L("测量中", "Measuring"), "synthetic", "activity"))
    lay.addWidget(
        synthetic_badge()
        if compact < 2
        else badge(L("合成", "Synth."), "synthetic", "flask-conical")
    )
    lay.addSpacing(4)
    mode = seg([L("普通", "Guided"), L("专业", "Pro")], 0 if plain else 1)
    lay.addWidget(mode)
    lay.addWidget(planned_badge())
    lay.addSpacing(2)
    lay.addWidget(
        tool(
            "panel-right",
            state="on" if panel_open else "",
            icon_color="accent_fg" if panel_open else "muted",
        )
    )
    return tb


# ------------------------------------------------------------------ measurement list
def _meas_row(
    name: str,
    color: str,
    value: str,
    tone: str,
    *,
    sel: bool = False,
    overlay: bool = True,
    baseline: bool = False,
    dashed: bool = False,
    extra: QWidget | None = None,
    unsaved: bool = False,
) -> QFrame:
    r = frame("row", sel="true" if sel else "false")
    r.setFixedHeight(SIZE["row_h"])
    lay = QHBoxLayout(r)
    lay.setContentsMargins(18, 0, 6, 0)
    lay.setSpacing(6)
    cb = check("", overlay)
    cb.setFixedWidth(16)
    lay.addWidget(cb)
    lay.addWidget(swatch(color, dashed))
    lay.addWidget(lab(name, "control_strong" if sel else "control"))
    if baseline:
        lay.addWidget(ico("star", 11, "muted"))
        lay.addWidget(lab(L("基准", "Base"), "caption", "muted"))
    if unsaved:
        lay.addWidget(lab(L("未保存", "Unsaved"), "caption", "warn"))
    lay.addStretch(1)
    if extra:
        lay.addWidget(extra)
    lay.addWidget(num(value, "muted" if not sel else "text", width=44))
    lay.addWidget(status_icon(tone, 12) if tone else pk.spacer_w(12))
    return r


def _group_row(
    text: str, icon: str | None = None, indent: int = 6, strong: bool = False
) -> QWidget:
    items = [pk.spacer_w(indent)]
    if icon:
        items.append(ico(icon, 13, "muted"))
    items.append(
        lab(text, "control_strong" if strong else "control", "text" if strong else "muted")
    )
    items.append("stretch")
    w = hbox(*items, spacing=5)
    w.setFixedHeight(22)
    return w


def measurement_list(
    selected: str = "B-1", *, measuring: bool = False, overlay_a: bool = True, plain: bool = False
) -> QFrame:
    sb = frame("sidebar")
    sb.setFixedWidth(SIZE["list_w"])
    lay = QVBoxLayout(sb)
    lay.setContentsMargins(6, 8, 6, 8)
    lay.setSpacing(2)
    head = hbox(
        pk.spacer_w(4),
        lab(L("测量", "Measurements"), "heading"),
        lab("3" if measuring else "2", "num", "faint"),
        "stretch",
        tool("plus", icon_color="muted"),
        tool("sliders-horizontal", icon_color="muted"),
        spacing=6,
    )
    lay.addWidget(head)
    se = pk.QLineEdit()
    se.setPlaceholderText(L("筛选测量  ⌘F", "Filter  ⌘F"))
    se.setFixedHeight(24)
    se.setFont(pk.font("control"))
    lay.addWidget(se)
    lay.addSpacing(4)
    if not plain:
        colh = hbox(
            pk.spacer_w(40),
            lab(L("名称", "Name"), "label", "faint"),
            "stretch",
            lab("T30", "label", "faint"),
            pk.spacer_w(22),
            spacing=4,
        )
        lay.addWidget(colh)
    lay.addWidget(
        _group_row(L("合成演示房间", "Synthetic demo room"), "folder-open", 4, strong=True)
    )
    lay.addWidget(_group_row(L("A · 靠近桌面和侧墙", "A · Near desk and side wall"), None, 16))
    a_t30 = D.broadband("a")["t30"]["seconds"]
    b_t30 = D.broadband("b")["t30"]["seconds"]
    lay.addWidget(
        _meas_row(
            "A-1",
            "series_2",
            "" if plain else f"{a_t30:.2f} s",
            "warn",
            sel=selected == "A-1",
            overlay=overlay_a,
            baseline=True,
            dashed=True,
        )
    )
    lay.addWidget(_group_row(L("B · 从桌面向后移动 1 m", "B · 1 m back from desk"), None, 16))
    lay.addWidget(
        _meas_row(
            "B-1", "series_1", "" if plain else f"{b_t30:.2f} s", "warn", sel=selected == "B-1"
        )
    )
    if measuring:
        sp = pk.ico("activity", 12, "accent")
        lay.addWidget(
            _meas_row("B-2", "series_3", "—", "", sel=False, overlay=False, unsaved=True, extra=sp)
        )
    lay.addStretch(1)
    lay.addWidget(hline())
    n = 2 if overlay_a else 1
    foot = hbox(
        pk.spacer_w(4),
        lab(L(f"叠加 {n} · 基准 A-1", f"Overlay {n} · baseline A-1"), "caption", "muted"),
        "stretch",
        tool("ellipsis", icon_color="muted"),
        spacing=4,
    )
    lay.addWidget(foot)
    return sb


def rail(selected: str = "B-1") -> QFrame:
    sb = frame("sidebar")
    sb.setFixedWidth(SIZE["rail_w"])
    lay = QVBoxLayout(sb)
    lay.setContentsMargins(6, 8, 6, 8)
    lay.setSpacing(4)
    lay.addWidget(tool("plus", icon_color="muted"), 0, Qt.AlignmentFlag.AlignHCenter)
    lay.addWidget(tool("search", icon_color="muted"), 0, Qt.AlignmentFlag.AlignHCenter)
    lay.addWidget(hline())
    for name, color, dashed in (("A-1", "series_2", True), ("B-1", "series_1", False)):
        f = frame("row", sel="true" if name == selected else "false")
        f.setFixedSize(36, 40)
        v = QVBoxLayout(f)
        v.setContentsMargins(0, 4, 0, 4)
        v.setSpacing(3)
        v.addWidget(swatch(color, dashed, 18), 0, Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(
            lab(name, "label", "text" if name == selected else "muted"),
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        lay.addWidget(f, 0, Qt.AlignmentFlag.AlignHCenter)
    lay.addStretch(1)
    lay.addWidget(tool("panel-left-open", icon_color="muted"), 0, Qt.AlignmentFlag.AlignHCenter)
    return sb


# ------------------------------------------------------------------ chart column parts
def chart_bar(*left, right=()) -> QFrame:
    f = frame("chartbar")
    f.setFixedHeight(SIZE["chartbar_h"])
    lay = QHBoxLayout(f)
    lay.setContentsMargins(8, 0, 8, 0)
    lay.setSpacing(6)
    for w in left:
        pk._add(lay, w)
    lay.addStretch(1)
    for w in right:
        pk._add(lay, w)
    return f


def pointer_tools(cursor_on: bool = False, compact: bool = False) -> QWidget:
    f = pk.frame("seg")
    lay = QHBoxLayout(f)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(0)
    for i, (icon, _tip) in enumerate((("move", "pan"), ("scan", "box"), ("crosshair", "cursor"))):
        on = (i == 2) if cursor_on else (i == 0)
        b = QToolButton()
        b.setProperty("role", "segbtn")
        b.setProperty("on", "true" if on else "false")
        b.setProperty("icononly", "true")
        b.setIcon(pk.ipix(icon, 14, "text" if on else "muted"))
        b.setIconSize(QSize(14, 14))
        b.setFixedSize(28, 22)
        lay.addWidget(b)
        if i == 2:
            d = pk.QLabel(b)
            d.setFixedSize(6, 6)
            d.setStyleSheet(f"background:{C('planned')}; border-radius:3px;")
            d.move(20, 2)
    return f


def layout_switch(index: int = 0, compact: bool = False) -> QWidget:
    names = ["", "", ""]
    f = seg(names, index, icons=["square", "rows-2", "columns-2"], planned={2})
    for b in f.findChildren(QToolButton):
        b.setFixedSize(28, 22)
    return f


def fit_export(compact: bool = False) -> list:
    if compact:
        return [tool("maximize", icon_color="muted"), tool("download", icon_color="muted")]
    return [
        tool("maximize", L("适配", "Fit"), icon_color="muted"),
        tool(None, L("范围…", "Range…")),
        tool("download", L("导出", "Export"), icon_color="muted"),
    ]


def legend_strip(
    items: list[tuple[str, str, bool, str]], right: str = "", right_widget: QWidget | None = None
) -> QWidget:
    """items: (color token, name, dashed, suffix)."""
    parts = [pk.spacer_w(52)]
    for color, name, dashed, suffix in items:
        chip = hbox(
            swatch(color, dashed),
            lab(name, "control_strong"),
            lab(suffix, "caption", "muted") if suffix else None,
            spacing=5,
        )
        parts += [chip, 12]
    parts.append("stretch")
    if right:
        parts.append(lab(right, "caption", "muted"))
    if right_widget:
        parts.append(right_widget)
    parts.append(pk.spacer_w(10))
    w = hbox(*parts, spacing=0)
    w.setFixedHeight(24)
    w.setStyleSheet(f"background:{C('plot_bg')};")
    return w


def readout_bar(segments: list[tuple[str, str]], right: str = "", planned: bool = False) -> QFrame:
    """segments: (text, color token); mono."""
    f = frame("readout")
    f.setFixedHeight(SIZE["readout_h"])
    lay = QHBoxLayout(f)
    lay.setContentsMargins(10, 0, 10, 0)
    lay.setSpacing(0)
    for i, (txt, col) in enumerate(segments):
        if i:
            lay.addSpacing(8)
            lay.addWidget(vline(12))
            lay.addSpacing(8)
        lay.addWidget(lab(txt, "readout", col))
    if planned:
        lay.addSpacing(8)
        lay.addWidget(planned_badge(L("光标 A/B 未实现", "Cursors A/B planned")))
    lay.addStretch(1)
    if right:
        lay.addWidget(lab(right, "caption", "faint"))
    return f


def pane_header(text: str, *extra) -> QWidget:
    w = hbox(pk.spacer_w(10), lab(text, "label", "muted"), *extra, "stretch", spacing=6)
    w.setFixedHeight(22)
    w.setStyleSheet(f"background:{C('plot_bg')};")
    return w


# ------------------------------------------------------------------ inspector
def section(title: str, *right) -> QWidget:
    w = hbox(lab(title, "heading"), "stretch", *right, spacing=6)
    w.setFixedHeight(26)
    return w


def kv(
    label: str,
    value: str,
    unit: str = "",
    *,
    tone: str | None = None,
    note: str = "",
    value_w: int = 64,
    mark: str | None = None,
) -> QWidget:
    items = [lab(label, "control", "muted"), "stretch"]
    if mark:
        items.append(ico(mark, 11, "warn"))
    items.append(num(value, tone or "text", width=value_w))
    items.append(lab(unit, "caption", "muted", width=30))
    w = hbox(*items, spacing=4)
    w.setFixedHeight(20)
    if note:
        w.setToolTip(note)
    return w


def panel(
    tab: int, body: QWidget, tabs: list[str] | None = None, width: int | None = None
) -> QFrame:
    p = frame("panel")
    p.setFixedWidth(width or SIZE["panel_w"])
    lay = QVBoxLayout(p)
    lay.setContentsMargins(12, 8, 12, 10)
    lay.setSpacing(6)
    tabs = tabs or [L("检查", "Inspect"), L("参数", "Parameters"), L("对比", "Compare")]
    tabseg = seg(tabs, tab)
    tabseg.setStyleSheet("QToolButton { padding: 2px 7px; }")
    top = hbox(tabseg, "stretch", tool("x", icon_color="muted"), spacing=4)
    lay.addWidget(top)
    lay.addWidget(body, 1)
    return p


def quality_block() -> QWidget:
    return vbox(
        section(L("测量质量", "Measurement quality"), lab("9/10", "num", "muted")),
        hbox(
            status_icon("warn", 13),
            lab(L("可用 · 1 项提醒", "Usable · 1 warning"), "control_strong", "warn"),
            "stretch",
            spacing=6,
        ),
        lab(
            L(
                "电平：峰值 +2.6 dBFS，余量不足 1 dB\n→ 降低约 6 dB 后重测",
                "Level: peak +2.6 dBFS, under 1 dB headroom\n→ lower about 6 dB and measure again",
            ),
            "caption",
            "muted",
        ),
        hbox(
            status_icon("good", 12),
            lab(
                L("其余 9 项良好 · 直达声置信度 高", "9 other checks good · direct sound: high"),
                "caption",
                "muted",
            ),
            "stretch",
            ico("chevron-down", 12, "faint"),
            spacing=6,
        ),
        spacing=4,
    )


def key_figures(pos: str = "b") -> QWidget:
    bb = D.broadband(pos)
    n = D.result(pos)["noise"]
    return vbox(
        section(L("关键数据", "Key figures"), lab(L("宽带", "Broadband"), "caption", "faint")),
        kv("RT60 (T30)", f"{bb['t30']['seconds']:.2f}", "s"),
        kv("EDT", f"{bb['edt']['seconds']:.2f}", "s"),
        kv("T20", f"{bb['t20']['seconds']:.2f}", "s"),
        kv("C50", D.signed(bb["c50"]["value"]), "dB"),
        kv("C80", D.signed(bb["c80"]["value"]), "dB"),
        kv("D50", f"{bb['d50']['value']:.0f}", "%"),
        kv("Ts", f"{bb['centre_time']['value'] * 1000:.0f}", "ms"),
        kv(L("本底噪声 RMS", "Noise floor RMS"), D.neg(n["rms_dbfs"]), "dBFS"),
        kv(L("曲率", "Curvature"), f"{bb['curvature_percent']:.1f}", "%"),
        spacing=1,
    )


def detections(pos: str = "b", highlight: str = "") -> QWidget:
    r = D.result(pos)
    res = r["resonances"]["candidates"][0]
    hum = r["noise"]["hum"][0]
    refl = r["reflections"]["reflections"][0]

    def row(icon, tone, title, value, key):
        w = hbox(
            ico(icon, 13, tone),
            lab(title, "control"),
            "stretch",
            num(value, "text"),
            ico("arrow-right", 12, "accent_fg" if key == highlight else "faint"),
            spacing=6,
        )
        w.setFixedHeight(22)
        if key == highlight:
            w.setStyleSheet(f"background:{C('selected')}; border-radius:4px;")
        return w

    return vbox(
        section(L("检测到", "Detected"), lab("3", "num", "faint")),
        row(
            "info",
            "info",
            L("共振候选", "Resonance"),
            f"{res['frequency_hz']:.1f} Hz  {D.signed(res['level_above_baseline_db'])} dB",
            "res",
        ),
        row(
            "triangle-alert",
            "warn",
            L("交流声 50 Hz", "Hum 50 Hz"),
            f"{D.signed(hum['strongest_prominence_db'], 0)} dB",
            "hum",
        ),
        row(
            "radio",
            "muted",
            L("早期反射", "Early reflection"),
            f"{refl['delay_ms']:.1f} ms  {D.neg(refl['relative_db'])} dB",
            "refl",
        ),
        spacing=1,
    )


def fr_params() -> QWidget:
    r = D.result("b")["frequency_response"]
    lo, hi = D.excitation("b")
    return vbox(
        section(L("显示与分析参数", "Display & analysis")),
        kv(L("显示平滑", "Display smoothing"), "1/6", "oct"),
        kv(L("分析平滑（已存）", "Stored smoothing"), f"1/{r['smoothing_fraction']}", "oct"),
        kv(L("窗长", "Window"), f"{r['window_s']:.2f}", "s"),
        kv(L("分辨率", "Resolution"), f"{r['resolution_hz']:.1f}", "Hz"),
        kv(L("扫频范围", "Excitation band"), f"{lo:.1f}–{hi / 1000:.1f}k", "Hz", value_w=96),
        kv(L("对齐频带（关）", "Align band (off)"), "500–2k", "Hz", value_w=96),
        spacing=1,
    )


# ------------------------------------------------------------------ control bar
def control_bar(state: str = "idle", compact: int = 0, plain: bool = False) -> QFrame:
    f = frame("controlbar", measuring="true" if state == "measuring" else "false")
    f.setFixedHeight(SIZE["control_bar_h"] + (1 if state == "measuring" else 0))
    lay = QHBoxLayout(f)
    lay.setContentsMargins(12, 0, 12, 0)
    lay.setSpacing(8)
    if state == "measuring":
        lay.addWidget(btn(L("开始", "Start"), "primary", "disabled", "play"))
        lay.addWidget(btn(L("停止  Esc", "Stop  Esc"), "danger", "", "square"))
    else:
        lay.addWidget(
            btn(
                L("开始测量  ⌘↩", "Measure  ⌘↩") if not plain else L("开始测量", "Start measuring"),
                "primary",
                "",
                "play",
            )
        )
        if not plain:
            lay.addWidget(btn(L("停止", "Stop"), "btn", "disabled", "square"))
    lay.addWidget(vline(20))
    if state == "measuring":
        lay.addWidget(ico("lock", 13, "muted"))
        lay.addWidget(
            lab(
                L(
                    "音频接口 · ReverbScope fake interface · 话筒 1 · 48 kHz · 扫频 5 s · −20 dBFS · 位置 B",
                    "Audio interface · ReverbScope fake interface · mic 1 · 48 kHz · sweep 5 s · −20 dBFS · pos. B",
                ),
                "control",
                "muted",
            )
        )
    elif plain:
        lay.addWidget(
            lab(
                L(
                    "用音频接口 · ReverbScope fake interface · 位置 B",
                    "Audio interface · ReverbScope fake interface · position B",
                ),
                "control",
                "muted",
            )
        )
        lay.addWidget(tool(None, L("更改…", "Change…")))
    else:
        lay.addWidget(combo(L("音频接口", "Audio interface"), 96 if S.lang == "zh" else 116))
        if compact < 2:
            lay.addWidget(
                pk.labelled(
                    L("输入", "In"),
                    combo("ReverbScope fake interface", 176 if compact == 0 else 128),
                )
            )
            lay.addWidget(pk.labelled(L("话筒", "Mic"), combo("1", 44, mono=True)))
        if compact == 0:
            lay.addWidget(pk.labelled(L("输出", "Out"), combo("Fake out 1/2", 110)))
        lay.addWidget(combo("48 kHz", 76, mono=True))
        if compact == 0:
            lay.addWidget(lab(L("扫频 5 s · −20 dBFS", "Sweep 5 s · −20 dBFS"), "num", "muted"))
        lay.addWidget(pk.labelled(L("位置", "Pos."), combo("B", 44)))
        lay.addWidget(tool(None, L("设置…", "Set up…") if compact < 2 else "…"))
    lay.addStretch(1)
    if state == "measuring":
        lay.addWidget(meter())
        lay.addWidget(planned_badge(L("电平表 未实现", "Meter planned")))
        lay.addWidget(vline(20))
        lay.addWidget(lab(L("正在播放扫频", "Playing sweep"), "control_strong", "accent_fg"))
        lay.addWidget(num("3.8 / 8.5 s", "text"))
        pb = pk.QProgressBar()
        pb.setRange(0, 1000)
        pb.setValue(443)
        pb.setTextVisible(False)
        pb.setFixedSize(140, 4)
        lay.addWidget(pb)
    else:
        lay.addWidget(dot("good", 7))
        lay.addWidget(lab(L("就绪", "Ready"), "control", "muted"))
        if compact == 0:
            lay.addWidget(lab(L("上次 10月18日 21:10", "Last Oct 18 21:10"), "caption", "faint"))
    return f


def meter() -> QWidget:
    from PySide6.QtGui import QColor, QPainter

    w = QWidget()
    w.setFixedSize(150, 18)

    def paint(ev, w=w):
        p = QPainter(w)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(pk.font("tick", size=10))
        p.setPen(QColor(C("muted")))
        p.drawText(0, 13, "IN")
        x0, x1 = 20, 108
        p.fillRect(x0, 6, x1 - x0, 6, QColor(C("surface_alt")))
        frac = (60 - 18.4) / 60
        p.fillRect(x0, 6, int((x1 - x0) * frac), 6, QColor(C("good")))
        p.fillRect(x0 + int((x1 - x0) * (48 / 60)), 4, 1, 10, QColor(C("warn")))
        p.setPen(QColor(C("text")))
        p.setFont(pk.font("num", size=11))
        p.drawText(112, 13, "−18.4")
        p.end()

    w.paintEvent = paint  # type: ignore[assignment]
    return w


# ------------------------------------------------------------------ window
def window(
    toolbar_w: QWidget,
    center: QWidget,
    left: QWidget | None,
    right: QWidget | None,
    bottom: QWidget,
) -> QWidget:
    root = QWidget()
    root.setObjectName("window")
    root.setFixedSize(S.W, S.H)
    root.setStyleSheet(pk.qss())
    v = QVBoxLayout(root)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    v.addWidget(toolbar_w)
    mid = QWidget()
    h = QHBoxLayout(mid)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)
    if left:
        h.addWidget(left)
    cf = frame("center")
    cl = QVBoxLayout(cf)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)
    cl.addWidget(center)
    cf.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    h.addWidget(cf, 1)
    if right:
        h.addWidget(right)
    v.addWidget(mid, 1)
    v.addWidget(bottom)
    return root
