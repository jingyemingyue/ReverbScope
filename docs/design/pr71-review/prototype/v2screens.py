# ruff: noqa: N802, N806, N812, ARG001
# Design-phase mockup renderer (docs only, not product code).
"""PR #71 review v2: PR #71's task IA (项目/测量/分析/对比 + stepwise measuring)
on PR #79's dense chart canvas. Every screen is a DESIGN MOCKUP, not the app."""

from __future__ import annotations

import pk
import pscreens as PS
import pshell as P
import v2tokens
from pk import (
    SIZE,
    C,
    L,
    S,
    badge,
    btn,
    check,
    combo,
    frame,
    hbox,
    hline,
    ico,
    lab,
    num,
    planned_badge,
    seg,
    status_icon,
    synthetic_badge,
    tool,
    vbox,
    vline,
)
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QVBoxLayout, QWidget

V2_APPBAR_H = 44
V2_ACTION_H = 48
V2_TASKBAR_H = 40
STEPPER_W = 232

TASKS = [
    ("project", ("项目", "Project")),
    ("measure", ("测量", "Measure")),
    ("analysis", ("分析", "Analysis")),
    ("compare", ("对比", "Compare")),
]
# English uses the short tab labels of SPEC §8 (full names live in the View menu / tooltips)
VIEWS = [
    ("overview", ("总览", "Overview")),
    ("fr", ("频响", "Freq.")),
    ("etc", ("时域", "Time")),
    ("decay", ("衰减", "Decay")),
    ("noise", ("噪声", "Noise")),
    ("spectrogram", ("声谱", "Spectro.")),
    ("waterfall", ("瀑布", "Waterfall")),
    ("room", ("房间", "Room")),
    ("report", ("报告", "Report")),
]


def _extra_qss() -> str:
    t = S.T
    return f"""
QToolButton[role="task"] {{ border: none; border-bottom: 2px solid transparent; border-radius: 0;
    padding: 0 10px; color: {t["muted"]}; font-size: 13px; }}
QToolButton[role="task"][on="true"] {{ color: {t["text"]}; border-bottom: 2px solid {t["accent"]}; font-weight: 600; }}
QToolButton[role="viewtab"] {{ border: none; border-radius: 4px; padding: 2px 8px; color: {t["muted"]}; }}
QToolButton[role="viewtab"][on="true"] {{ background: {t["surface_alt"]}; color: {t["text"]}; font-weight: 600; }}
QFrame[role="actionbar"] {{ background: {t["toolbar"]}; border-top: 1px solid {t["border"]}; }}
QFrame[role="taskbar"] {{ background: {t["toolbar"]}; border-top: 2px solid {t["accent"]}; }}
QFrame[role="stepper"] {{ background: {t["sidebar"]}; border-right: 1px solid {t["border"]}; }}
QFrame[role="form"] {{ background: {t["bg"]}; }}
QFrame[role="step"] {{ border-radius: 4px; }}
QFrame[role="step"][sel="true"] {{ background: {t["selected"]}; }}
QFrame[role="stopbig"] {{ background: {t["bad"]}; border-radius: 6px; }}
QFrame[role="phasebox"] {{ background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 6px; }}
"""


def _task_button(text: str, on: bool) -> QToolButton:
    b = QToolButton()
    b.setProperty("role", "task")
    b.setProperty("on", "true" if on else "false")
    b.setText(text)
    b.setFont(pk.font("control_strong" if on else "control", size=13))
    b.setFixedHeight(V2_APPBAR_H)
    return b


def _view_tabs(current: str, compact: int) -> QWidget:
    views = VIEWS
    more = False
    if compact >= 2:
        keep = {"overview", "fr", "decay", "waterfall", current}
        views = [v for v in VIEWS if v[0] in keep]
        more = True
    items = []
    for key, names in views:
        b = QToolButton()
        b.setProperty("role", "viewtab")
        b.setProperty("on", "true" if key == current else "false")
        b.setText(L(*names))
        b.setFont(pk.font("control_strong" if key == current else "control"))
        b.setFixedHeight(24)
        items.append(b)
    if more:
        items.append(tool("ellipsis", icon_color="muted"))
    return hbox(*items, spacing=2)


def app_bar(
    task: str,
    view: str = "fr",
    *,
    compact: int = 0,
    measuring: bool = False,
    list_open: bool = True,
    panel_open: bool = True,
    center: QWidget | None = None,
    doc: str | None = None,
    unsaved: bool = False,
) -> QWidget:
    """One 44 px bar replaces PR #71's task bar (46) + context bar (52) + status bar (22)."""
    tb = frame("toolbar")
    tb.setFixedHeight(V2_APPBAR_H)
    lay = QHBoxLayout(tb)
    lay.setContentsMargins(14, 0, 10, 0)
    lay.setSpacing(4)
    lay.addWidget(pk.traffic_lights())
    lay.addSpacing(8)
    if task in ("analysis", "compare"):
        lay.addWidget(
            tool(
                "panel-left",
                state="on" if list_open else "",
                icon_color="accent_fg" if list_open else "muted",
            )
        )
    if compact == 0 and S.lang == "zh":
        lay.addWidget(lab("ReverbScope", "window_title"))
        lay.addSpacing(6)
    for key, names in TASKS:
        lay.addWidget(_task_button(L(*names), key == task))
    lay.addSpacing(6)
    lay.addWidget(vline(20))
    lay.addSpacing(6)
    if task == "analysis":
        lay.addWidget(_view_tabs(view, compact))
    elif center is not None:
        lay.addWidget(center)
    lay.addStretch(1)
    if measuring:
        lay.addWidget(badge(L("测量中", "Measuring"), "synthetic", "activity"))
    lay.addWidget(
        synthetic_badge()
        if compact < 2
        else badge(L("合成", "Synth."), "synthetic", "flask-conical")
    )
    if task in ("analysis", "compare"):
        d = doc or ("B-1 · " + L("位置 B", "Position B") if compact < 2 else "B-1")
        lay.addWidget(combo(d, 132 if compact < 2 else 92, flat=True))
    if unsaved:
        lay.addWidget(btn(L("保存", "Save"), "primary", "", "save"))
    else:
        lay.addWidget(tool("save", icon_color="muted"))
    lay.addWidget(tool("settings", icon_color="muted"))
    if task in ("analysis", "compare"):
        lay.addWidget(
            tool(
                "panel-right",
                state="on" if panel_open else "",
                icon_color="accent_fg" if panel_open else "muted",
            )
        )
    return tb


def task_strip(phase: str, elapsed: str, total: str, frac: float, what: str) -> QWidget:
    """The global task bar (GUIDELINES §11.1): only while a take/analysis runs."""
    f = frame("taskbar")
    f.setFixedHeight(V2_TASKBAR_H)
    lay = QHBoxLayout(f)
    lay.setContentsMargins(12, 0, 12, 0)
    lay.setSpacing(10)
    lay.addWidget(pk.dot("bad", 8))
    lay.addWidget(lab(phase, "control_strong", "text"))
    lay.addWidget(num(f"{elapsed} / {total}", "text"))
    pb = pk.QProgressBar()
    pb.setRange(0, 1000)
    pb.setValue(int(frac * 1000))
    pb.setTextVisible(False)
    pb.setFixedSize(160, 4)
    lay.addWidget(pb)
    lay.addWidget(vline(18))
    lay.addWidget(ico("lock", 13, "muted"))
    lay.addWidget(lab(what, "caption", "muted"))
    lay.addStretch(1)
    lay.addWidget(btn(L("停止  Esc", "Stop  Esc"), "danger", "", "square"))
    return f


def _empty_bottom() -> QWidget:
    w = QWidget()
    w.setFixedHeight(0)
    return w


def _shell(root: QWidget) -> QWidget:
    root.setStyleSheet(pk.qss() + _extra_qss())
    return root


# ------------------------------------------------------------------ patch PR #79 shell
def _toolbar_adapter(
    view,
    *,
    title="",
    subtitle="",
    list_open=True,
    panel_open=True,
    compact=0,
    plain=False,
    measuring=False,
):
    task = "compare" if view == "compare" else "analysis"
    return app_bar(
        task, view, compact=compact, measuring=measuring, list_open=list_open, panel_open=panel_open
    )


def _control_adapter(state="idle", compact=0, plain=False):
    if state == "measuring":
        return task_strip(
            L("正在播放扫频", "Playing sweep"),
            "3.8",
            "10.0 s",
            0.38,
            L("设备、路径与上一步已锁定", "Devices, path and Previous are locked"),
        )
    return _empty_bottom()


if not hasattr(P, "_orig_window"):
    P._orig_window = P.window


def _window_adapter(toolbar_w, center, left, right, bottom):
    return _shell(P._orig_window(toolbar_w, center, left, right, bottom))


if not hasattr(P, "_orig_panel"):
    P._orig_panel = P.panel


def _panel_adapter(tab, body, tabs=None, width=None):
    tabs = tabs or [L("检查", "Inspect"), L("参数", "Params"), L("对比", "Compare")]
    return P._orig_panel(tab, body, tabs, width)


def install() -> None:
    v2tokens.apply()
    P.panel = _panel_adapter
    P.toolbar = _toolbar_adapter
    P.control_bar = _control_adapter
    P.window = _window_adapter


# ------------------------------------------------------------------ measure: stepper
def _step_row(n: int, title: str, sub: str, state: str) -> QWidget:
    f = frame("step", sel="true" if state in ("current", "running") else "false")
    f.setFixedHeight(48)
    lay = QHBoxLayout(f)
    lay.setContentsMargins(10, 6, 8, 6)
    lay.setSpacing(10)
    icon = {
        "done": ("circle-check", "good"),
        "current": ("circle-dot", "accent_fg"),
        "running": ("activity", "accent_fg"),
        "todo": ("circle", "muted"),
        "locked": ("lock", "text_disabled"),
    }[state]
    lay.addWidget(ico(icon[0], 16, icon[1]), 0, Qt.AlignmentFlag.AlignTop)
    col = "text_disabled" if state == "locked" else "text"
    txt = vbox(
        lab(
            f"{n}  {title}", "control_strong" if state in ("current", "running") else "control", col
        ),
        lab(sub, "caption", "faint" if state != "locked" else "text_disabled"),
        spacing=1,
    )
    lay.addWidget(txt, 1)
    return f


def stepper(path: str, current: int, *, running: bool = False, compact: bool = False) -> QWidget:
    sb = frame("stepper")
    sb.setFixedWidth(STEPPER_W if not compact else 184)
    lay = QVBoxLayout(sb)
    lay.setContentsMargins(8, 12, 8, 10)
    lay.setSpacing(4)
    lay.addWidget(lab(L("新测量", "New measurement"), "label", "faint"))
    lay.addSpacing(2)
    if compact:
        lay.addWidget(combo(L("音频接口", "Audio interface"), 168))
    else:
        lay.addWidget(
            seg(
                [L("音频接口", "Interface"), "DAW"],
                0 if path == "interface" else 1,
                icons=["audio-lines", "file-audio"],
            )
        )
    lay.addSpacing(8)
    steps = [
        (L("连接设备", "Connection"), "Fake interface · 48 kHz"),
        (L("信号与电平", "Signal & level"), L("−9 dBFS · 10 s · 人声", "−9 dBFS · 10 s · vocal")),
        (L("测量", "Measure"), L("位置 B · B-2", "Position B · B-2")),
    ]
    for i, (t, s) in enumerate(steps, start=1):
        if running:
            st = "running" if i == 3 else "locked"
        else:
            st = "done" if i < current else "current" if i == current else "todo"
        lay.addWidget(_step_row(i, t, s, st))
    lay.addStretch(1)
    lay.addWidget(hline())
    lay.addWidget(
        hbox(
            ico("folder-open", 12, "muted"),
            lab(L("从项目进入 · 位置 B", "From project · Position B"), "caption", "muted"),
            "stretch",
            spacing=6,
        )
    )
    return sb


# ------------------------------------------------------------------ level slider (custom)
def level_slider(value: float, safe: float = -12.0, width: int = 360) -> QWidget:
    w = QWidget()
    w.setFixedSize(width, 40)

    def paint(ev, w=w):
        p = QPainter(w)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x0, x1, y = 8, w.width() - 8, 14

        def X(db: float) -> float:
            return x0 + (db + 40.0) / 40.0 * (x1 - x0)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C("surface_alt")))
        p.drawRoundedRect(QRectF(x0, y - 3, x1 - x0, 6), 3, 3)
        warn = QColor(C("warn"))
        warn.setAlpha(110)
        p.setBrush(warn)
        p.drawRoundedRect(QRectF(X(safe), y - 3, x1 - X(safe), 6), 3, 3)
        p.setBrush(QColor(C("accent")))
        p.drawRoundedRect(QRectF(x0, y - 3, X(value) - x0, 6), 3, 3)
        p.setPen(QPen(QColor(C("warn")), 1.5))
        p.drawLine(int(X(safe)), y - 8, int(X(safe)), y + 8)
        p.setPen(QPen(QColor(C("border_strong")), 1))
        p.setBrush(QColor(C("text")))
        p.drawEllipse(QRectF(X(value) - 7, y - 7, 14, 14))
        p.setFont(pk.font("tick"))
        p.setPen(QColor(C("plot_text")))
        for db in (-40, -30, -20, -12, 0):
            t = f"{db}".replace("-", "−")
            fm = p.fontMetrics()
            p.drawText(int(X(db) - fm.horizontalAdvance(t) / 2), 37, t)
        p.end()

    w.paintEvent = paint  # type: ignore[assignment]
    return w


def _form_row(label: str, *widgets, label_w: int = 112) -> QWidget:
    return hbox(
        lab(
            label,
            "control",
            "muted",
            width=label_w,
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        ),
        12,
        *widgets,
        "stretch",
        spacing=8,
    )


def _check_row(tone: str, title: str, value: str = "", planned: bool = False) -> QWidget:
    items = [status_icon(tone, 13), lab(title, "control"), "stretch"]
    if planned:
        items.append(planned_badge())
    if value:
        items.append(num(value, "muted"))
    w = hbox(*items, spacing=6)
    w.setFixedHeight(22)
    return w


def ready_panel(level_ok: bool, *, running: bool = False, width: int | None = None) -> QWidget:
    body = vbox(
        P.section(L("就绪检查", "Readiness")),
        _check_row("good", L("设备已连接", "Devices connected"), "Fake interface"),
        _check_row("good", L("采样率一致", "Sample rates match"), "48 kHz"),
        _check_row(
            "good" if level_ok else "warn",
            L("电平在安全线内", "Level within safe limit")
            if level_ok
            else L("电平高于安全线，需确认", "Above safe limit: confirm"),
            "−9 > −12 dBFS" if not level_ok else "−20 dBFS",
        ),
        _check_row("neutral", L("输入电平预检", "Input level pre-check"), planned=True),
        _check_row("good", L("位置", "Position"), "B · B-2"),
        hline(),
        P.section(L("本次将使用", "This take uses")),
        P.kv(L("输入", "Input"), "Fake in 1", value_w=120),
        P.kv(L("输出", "Output"), "Fake out 1", value_w=120),
        P.kv(L("采样率", "Rate"), "48 000", "Hz"),
        P.kv(L("扫频", "Sweep"), "10.0", "s"),
        P.kv(
            L("电平", "Level"),
            "−9.0" if not level_ok else "−20.0",
            "dBFS",
            tone="warn" if not level_ok else None,
        ),
        "stretch",
        spacing=6,
    )
    p = frame("panel")
    p.setFixedWidth(width or SIZE["panel_w"])
    lay = QVBoxLayout(p)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.addWidget(body)
    return p


def action_bar(
    *,
    prev: bool,
    status: tuple[str, str],
    primary: str,
    primary_state: str = "",
    stop: bool = False,
) -> QWidget:
    f = frame("actionbar")
    f.setFixedHeight(V2_ACTION_H)
    lay = QHBoxLayout(f)
    lay.setContentsMargins(16, 0, 16, 0)
    lay.setSpacing(10)
    lay.addWidget(btn(L("上一步", "Previous"), "btn", "" if prev else "disabled", "chevron-left"))
    tone, text = status
    if tone:
        lay.addWidget(status_icon(tone, 13))
    lay.addWidget(lab(text, "control", tone if tone in ("warn", "bad") else "muted"))
    lay.addStretch(1)
    if stop:
        lay.addWidget(btn(L("停止  Esc", "Stop  Esc"), "danger", "", "square"))
    lay.addWidget(
        btn(
            primary,
            "primary",
            primary_state,
            "play" if "测量" in primary or "Measure" in primary else "chevron-right",
        )
    )
    return f


def _seg_presets() -> QWidget:
    return seg(
        [
            L("短 5 s", "Short 5 s"),
            L("标准 10 s", "Std 10 s"),
            L("长 20 s", "Long 20 s"),
            L("自定义", "Custom"),
        ],
        1,
    )


def measure_level_center(compact: bool = False) -> QWidget:
    f = frame("form")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(32 if not compact else 20, 24 if not compact else 16, 24, 12)
    lay.setSpacing(14 if not compact else 10)
    lay.addWidget(lab(L("2  信号与电平", "2  Signal and level"), "heading", size=18))
    lay.addWidget(
        lab(
            L(
                "设定扫频的播放电平和时长。先低后高：录音太轻时，再在两次测量之间逐步提高。",
                "Set sweep level and length. Start low; raise between takes only if the recording is too quiet.",
            ),
            "control",
            "muted",
            wrap=True,
        )
    )
    lay.addSpacing(4)
    sw = 300 if compact else 360
    lay.addWidget(
        _form_row(
            L("播放电平", "Playback level"),
            level_slider(-9.0, width=sw),
            combo("−9.0 dBFS", 104, mono=True),
            label_w=96 if compact else 112,
        )
    )
    warn = hbox(
        pk.spacer_w(108 if compact else 124),
        ico("triangle-alert", 13, "warn"),
        lab(
            L(
                "高于 −12 dBFS：请先把监听音量调低，并在下方确认（仅对本次测量有效）。",
                "Above −12 dBFS: turn monitors down first and confirm below (this take only).",
            ),
            "caption",
            "warn",
            wrap=True,
        ),
        "stretch",
        spacing=6,
    )
    lay.addWidget(warn)
    lay.addWidget(
        hbox(
            pk.spacer_w(108 if compact else 124),
            check(L("我已把监听音量调低", "I have turned the monitor level down"), False),
            "stretch",
        )
    )
    lay.addSpacing(6)
    lay.addWidget(
        _form_row(L("扫频时长", "Sweep length"), _seg_presets(), label_w=96 if compact else 112)
    )
    lay.addWidget(
        _form_row(
            L("录音配置", "Profile"),
            combo(L("人声", "Vocal"), 160),
            tool(None, L("它关注什么", "What it checks")),
            label_w=96 if compact else 112,
        )
    )
    lay.addSpacing(6)
    lay.addWidget(hline())
    lay.addWidget(
        hbox(
            ico("chevron-right", 14, "muted"),
            lab(L("房间与摆位（可选）", "Room and placement (optional)"), "control_strong"),
            lab(L("距离、话筒高度、温度", "distance, mic height, temperature"), "caption", "faint"),
            "stretch",
            spacing=6,
        )
    )
    lay.addStretch(1)
    return f


def screen_measure_level() -> QWidget:
    compact = S.W < 1100
    root = QWidget()
    root.setObjectName("window")
    root.setFixedSize(S.W, S.H)
    v = QVBoxLayout(root)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    pos = hbox(pk.labelled(L("位置", "Position"), combo("B", 56)), spacing=6)
    v.addWidget(app_bar("measure", center=pos, compact=2 if compact else 0))
    mid = QWidget()
    h = QHBoxLayout(mid)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)
    h.addWidget(stepper("interface", 2, compact=compact))
    h.addWidget(measure_level_center(compact), 1)
    if not compact:
        h.addWidget(ready_panel(False))
    v.addWidget(mid, 1)
    v.addWidget(
        action_bar(
            prev=True,
            status=(
                "warn",
                L(
                    "先勾选“我已把监听音量调低”",
                    "Tick “I have turned the monitor level down” first",
                ),
            ),
            primary=L("继续  ⌘↩", "Continue  ⌘↩"),
            primary_state="disabled",
        )
    )
    return _shell(root)


def capture_preview() -> QWidget:
    """Recorded-input envelope so far (design only; needs a level callback = not implemented)."""
    import math

    outer = frame("phasebox")
    ol = QVBoxLayout(outer)
    ol.setContentsMargins(14, 10, 14, 10)
    ol.setSpacing(6)
    ol.addWidget(
        hbox(
            lab(L("录音输入（包络）", "Recorded input (envelope)"), "label", "muted"),
            planned_badge(),
            "stretch",
            lab(
                L("峰值 −18.4 dBFS · 余量 18 dB", "peak −18.4 dBFS · 18 dB headroom"),
                "num",
                "muted",
            ),
            spacing=6,
        )
    )
    w = QWidget()
    w.setMinimumHeight(160)

    def paint(ev, w=w):
        p = QPainter(w)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(w.rect(), QColor(C("plot_bg")))
        W, H = w.width(), w.height()
        p.setPen(QPen(QColor(C("plot_grid_major")), 1))
        for db in (0, -12, -24, -36, -48):
            y = int(8 + (-db) / 54 * (H - 16))
            p.drawLine(40, y, W - 4, y)
            p.setPen(QColor(C("plot_text")))
            p.setFont(pk.font("tick"))
            p.drawText(4, y + 4, f"{db}".replace("-", "−"))
            p.setPen(QPen(QColor(C("plot_grid_major")), 1))
        p.setPen(QPen(QColor(C("warn")), 1, Qt.PenStyle.DashLine))
        yc = int(8 + 1 / 54 * (H - 16))
        p.drawLine(40, yc, W - 4, yc)
        xe = 40 + int((W - 44) * 0.38)
        col = QColor(C("series_1"))
        p.setPen(QPen(col, 1.2))
        for x in range(40, xe):
            t = (x - 40) / (W - 44)
            lvl = -18.4 - 3 * math.sin(t * 40) * math.exp(-t * 2) - 2 * (1 - t)
            amp = (54 + lvl) / 54 * (H - 16) / 2
            mid = H / 2
            p.drawLine(
                x,
                int(mid - amp * (0.6 + 0.4 * abs(math.sin(x * 0.7)))),
                x,
                int(mid + amp * (0.6 + 0.4 * abs(math.sin(x * 0.7)))),
            )
        p.setPen(QPen(QColor(C("cursor")), 1))
        p.drawLine(xe, 4, xe, H - 4)
        p.end()

    w.paintEvent = paint  # type: ignore[assignment]
    ol.addWidget(w, 1)
    return outer


def measuring_center() -> QWidget:
    f = frame("form")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(32, 24, 24, 12)
    lay.setSpacing(14)
    lay.addWidget(lab(L("3  测量", "3  Measure"), "heading", size=18))
    box = frame("phasebox")
    bl = QVBoxLayout(box)
    bl.setContentsMargins(18, 16, 18, 16)
    bl.setSpacing(12)
    bl.addWidget(
        hbox(
            ico("activity", 16, "accent_fg"),
            lab(L("正在播放扫频", "Playing sweep"), "heading", size=16),
            "stretch",
            num("3.8 / 10.0 s", "text", size=15),
            spacing=8,
        )
    )
    pb = pk.QProgressBar()
    pb.setRange(0, 1000)
    pb.setValue(380)
    pb.setTextVisible(False)
    pb.setFixedHeight(6)
    bl.addWidget(pb)
    phases = hbox(
        hbox(status_icon("info", 13), lab(L("播放扫频", "Sweep"), "control_strong"), spacing=4),
        18,
        hbox(status_icon("neutral", 13), lab(L("录制尾音", "Tail"), "control", "muted"), spacing=4),
        18,
        hbox(
            status_icon("neutral", 13),
            lab(
                L("分析（不确定进度，不可取消）", "Analyse (indeterminate, not cancellable)"),
                "control",
                "muted",
            ),
            spacing=4,
        ),
        "stretch",
        spacing=0,
    )
    bl.addWidget(phases)
    bl.addWidget(hline())
    bl.addWidget(
        hbox(
            lab(L("输入", "Input"), "control", "muted"),
            P.meter(),
            planned_badge(L("实时电平表 未实现", "Live meter planned")),
            "stretch",
            btn(L("停止  Esc", "Stop  Esc"), "danger", "", "square"),
            spacing=8,
        )
    )
    lay.addWidget(box)
    lay.addWidget(capture_preview(), 1)
    lay.addWidget(
        hbox(
            ico("lock", 13, "muted"),
            lab(
                L(
                    "测量进行中：设备、路径、上一步、设置和打开文件已锁定；可以切到“分析”浏览，停止入口在底部任务条。",
                    "Take running: devices, path, Previous, Settings and Open are locked; Analysis stays browsable, Stop stays in the task bar.",
                ),
                "caption",
                "muted",
                wrap=True,
            ),
            spacing=6,
        )
    )
    return f


def screen_measuring_v2() -> QWidget:
    root = QWidget()
    root.setObjectName("window")
    root.setFixedSize(S.W, S.H)
    v = QVBoxLayout(root)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    pos = hbox(
        ico("lock", 12, "muted"), lab(L("位置 B", "Position B"), "control", "muted"), spacing=6
    )
    v.addWidget(app_bar("measure", center=pos, measuring=True))
    mid = QWidget()
    h = QHBoxLayout(mid)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)
    h.addWidget(stepper("interface", 3, running=True))
    h.addWidget(measuring_center(), 1)
    h.addWidget(ready_panel(True, running=True))
    v.addWidget(mid, 1)
    v.addWidget(
        task_strip(
            L("正在播放扫频", "Playing sweep"),
            "3.8",
            "10.0 s",
            0.38,
            L(
                "B-2 · 音频接口 · Fake interface · 48 kHz · −20 dBFS",
                "B-2 · Interface · Fake interface · 48 kHz · −20 dBFS",
            ),
        )
    )
    return _shell(root)


# ------------------------------------------------------------------ analysis screens
def screen_fr() -> QWidget:
    return PS.screen_fr_pro()


def screen_decay() -> QWidget:
    return PS.screen_rt60()


def screen_waterfall() -> QWidget:
    return PS.screen_waterfall()


def screen_compare() -> QWidget:
    return PS.screen_compare()


def screen_narrow() -> QWidget:
    return PS.screen_minimum()
