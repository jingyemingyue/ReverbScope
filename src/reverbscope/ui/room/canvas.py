"""The room canvas: a QPainter drawing of the room scene, with an orbit camera.

Three layers, each with its own line style (docs/design/GUI_2_ARCHITECTURE.md
§6.4): entered (solid), measured constraint (dashed), geometric assumption
(dotted). An axis triad and a metre scale bar keep the drawing readable;
nothing here uses OpenGL, so it renders offscreen and in screenshots.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from reverbscope.geometry.paths import PredictedPath
from reverbscope.geometry.room import Point, RoomBox
from reverbscope.i18n import N_, _
from reverbscope.ui.room.camera import OrbitCamera
from reverbscope.ui.theme import tokens

LAYER_ENTERED = "entered"
LAYER_MEASURED = "measured"
LAYER_ASSUMED = "assumed"
LAYER_NAMES = {
    LAYER_ENTERED: N_("Entered"),
    LAYER_MEASURED: N_("Measured constraint"),
    LAYER_ASSUMED: N_("Geometric assumption"),
}
LAYER_STYLE = {
    LAYER_ENTERED: Qt.PenStyle.SolidLine,
    LAYER_MEASURED: Qt.PenStyle.DashLine,
    LAYER_ASSUMED: Qt.PenStyle.DotLine,
}


def view_caption(name: str) -> str:
    """What the camera is doing, in the active language.

    ``name`` is :attr:`OrbitCamera.preset_name`. An empty name is a free orbit.
    """
    captions = {
        "top": _("Plan, true to scale · front is the lower edge"),
        "front": _("Front · the face at y = 0 is nearest"),
        "side": _("Side · the face at x = 0 is nearest"),
    }
    return captions.get(name, _("Perspective · drag to orbit, right-drag to pan"))


def _metres(value: float) -> str:
    return _("{metres:.2f} m").format(metres=value)


#: Pixels within which a click picks a device or a reflection point.
PICK_PX = 12.0

#: Corner order matches :meth:`RoomCanvas._draw_box`.
_FACE_CORNERS = {
    "x0": (0, 2, 6, 4),
    "x1": (1, 3, 7, 5),
    "y0": (0, 1, 5, 4),
    "y1": (2, 3, 7, 6),
    "z0": (0, 1, 3, 2),
    "z1": (4, 5, 7, 6),
}


def _box_corners(box: RoomBox) -> NDArray[np.float64]:
    length, width, height = box.dimensions
    return np.array(
        [[x, y, z] for z in (0.0, height) for y in (0.0, width) for x in (0.0, length)],
        dtype=np.float64,
    )


def _point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        crosses = (yi > y) != (yj > y)
        if crosses and yj != yi and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@dataclass
class RoomScene:
    """What the canvas draws; the view builds it from the geometry and the result."""

    box: RoomBox | None = None
    source: Point | None = None
    microphones: dict[str, Point] = field(default_factory=dict)
    #: The position of the current measurement (its microphone is highlighted).
    current_microphone: str = ""
    #: ``"source"``, a microphone label, or ``"face:<id>"`` of the entered box.
    selection: str = ""
    scan_points: NDArray[np.float64] | None = None
    #: ``(centre, radius)``: the measured direct distance around the loudspeaker.
    sphere: tuple[Point, float] | None = None
    #: ``(centre, radius)``: the horizontal ring of loudspeaker positions the
    #: placement result allows (centred above the microphone at the measured
    #: loudspeaker height). One microphone cannot say where on it.
    placement_ring: tuple[Point, float] | None = None
    #: ``(focus a, focus b, semi-major)`` of the selected reflection.
    ellipsoid: tuple[Point, Point, float] | None = None
    predicted: list[PredictedPath] = field(default_factory=list)
    #: Faces of predicted paths matched by the selected reflection.
    highlighted_faces: set[str] = field(default_factory=set)
    #: Off: the selected reflection only, drawn with a few lines. On: the sphere,
    #: the full ellipsoid and every predicted path the assumption layer allows.
    constraints_full: bool = False
    layers: dict[str, bool] = field(
        default_factory=lambda: {LAYER_ENTERED: True, LAYER_MEASURED: True, LAYER_ASSUMED: True}
    )

    def bounds(self) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        points: list[tuple[float, float, float]] = []
        if self.box is not None:
            points += [(0.0, 0.0, 0.0), self.box.dimensions]
        if self.source is not None:
            points.append(self.source.as_tuple())
        points += [mic.as_tuple() for mic in self.microphones.values()]
        if self.scan_points is not None and self.scan_points.size:
            points += [
                tuple(self.scan_points.min(axis=0)),
                tuple(self.scan_points.max(axis=0)),
            ]
        if not points:
            return np.zeros(3), np.array([4.0, 3.0, 2.5])
        array = np.asarray(points, dtype=np.float64)
        return array.min(axis=0), array.max(axis=0)


def ellipsoid_lines(
    a: Point, b: Point, semi_major: float, *, detail: bool = True
) -> list[NDArray[np.float64]]:
    """Meridians and parallels of the prolate spheroid with foci ``a``, ``b``."""
    pa = np.array(a.as_tuple())
    pb = np.array(b.as_tuple())
    gap = float(np.linalg.norm(pb - pa))
    if semi_major <= gap / 2.0:
        return []
    semi_minor = math.sqrt(semi_major**2 - (gap / 2.0) ** 2)
    centre = (pa + pb) / 2.0
    e1 = (pb - pa) / gap if gap > 1e-9 else np.array([1.0, 0.0, 0.0])
    helper = np.array([0.0, 0.0, 1.0]) if abs(e1[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e2 = np.cross(e1, helper)
    e2 /= np.linalg.norm(e2)
    e3 = np.cross(e1, e2)
    theta = np.linspace(0.0, math.pi, 40)
    lines = []
    meridians = np.linspace(0.0, 2 * math.pi, 8 if detail else 2, endpoint=False)
    for phi in meridians:
        ring = np.cos(phi) * e2 + np.sin(phi) * e3
        lines.append(
            centre
            + np.outer(semi_major * np.cos(theta), e1)
            + np.outer(semi_minor * np.sin(theta), ring)
        )
    phis = np.linspace(0.0, 2 * math.pi, 48 if detail else 24)
    parallels = (math.pi / 4, math.pi / 2, 3 * math.pi / 4) if detail else (math.pi / 2,)
    for t in parallels:
        ring = np.outer(np.cos(phis), e2) + np.outer(np.sin(phis), e3)
        lines.append(centre + semi_major * math.cos(t) * e1 + semi_minor * math.sin(t) * ring)
    return lines


def circle_lines(centre: Point, radius: float) -> list[NDArray[np.float64]]:
    """Three great circles of the sphere of ``radius`` around ``centre``."""
    c = np.array(centre.as_tuple())
    t = np.linspace(0.0, 2 * math.pi, 72)
    cos, sin = np.cos(t) * radius, np.sin(t) * radius
    zero = np.zeros_like(t)
    return [
        c + np.column_stack((cos, sin, zero)),
        c + np.column_stack((cos, zero, sin)),
        c + np.column_stack((zero, cos, sin)),
    ]


def ring_line(centre: Point, radius: float) -> NDArray[np.float64]:
    """The horizontal circle of ``radius`` around ``centre``."""
    c = np.array(centre.as_tuple())
    t = np.linspace(0.0, 2 * math.pi, 96)
    return c + np.column_stack((np.cos(t) * radius, np.sin(t) * radius, np.zeros_like(t)))


class RoomCanvas(QWidget):
    """Orbit (left drag), pan (right or middle drag), zoom about the cursor (wheel),
    fit (double-click, F). In the plan view, devices are dragged with the left button."""

    #: ``(name, point)``: a device was clicked (``"source"`` or a microphone label).
    device_clicked = Signal(str, object)
    #: ``(name, point)``: a device was dragged to ``point`` in the plan view.
    device_moved = Signal(str, object)
    #: A predicted reflection point was clicked (its face).
    face_clicked = Signal(str)
    #: An entered room face was clicked (``x0`` … ``z1``). Not a measured surface.
    surface_clicked = Signal(str)
    #: The named view changed (orbit, a preset, plan, reset).
    camera_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(False)
        self.camera = OrbitCamera()
        self.scene = RoomScene()
        self._press: QPointF | None = None
        self._last: QPointF | None = None
        self._button = Qt.MouseButton.NoButton
        self._dragging_device = ""
        self._moved = False
        self.empty_text = ""
        #: Coordinates of the last picked object, drawn on the canvas.
        self.hud = ""
        self.camera.reset(*self.scene.bounds())
        self._sync_tooltip()

    # --- content ------------------------------------------------------------------------

    def set_scene(self, scene: RoomScene, *, refit: bool = False) -> None:
        self.scene = scene
        if refit:
            self.fit()
        self.update()

    def set_plan(self, plan: bool) -> None:
        if plan:
            self.camera.preset("top")
        else:
            self.camera.plan = False
            if self.camera.preset_name == "top":
                self.camera.preset_name = ""
        self.fit()
        self._sync_tooltip()
        self.camera_changed.emit()

    def fit(self) -> None:
        self.camera.width, self.camera.height = self.width(), self.height()
        low, high = self.scene.bounds()
        # The front-edge mark and the dimension labels sit outside the box.
        pad = np.array([0.55, 1.2, 0.5])
        self.camera.fit(low - pad, high + pad)
        self.update()

    def reset(self) -> None:
        self.camera.width, self.camera.height = self.width(), self.height()
        self.camera.reset(*self.scene.bounds())
        self._sync_tooltip()
        self.camera_changed.emit()
        self.update()

    def look(self, preset: str) -> None:
        """Frame the room from ``top``, ``front`` or ``side``."""
        self.camera.width, self.camera.height = self.width(), self.height()
        self.camera.preset(preset)
        self.fit()
        self._sync_tooltip()
        self.camera_changed.emit()

    def _sync_tooltip(self) -> None:
        if self.camera.plan:
            self.setToolTip(
                _("Drag to pan. Drag a loudspeaker or microphone to move it. The wheel zooms.")
            )
            return
        self.setToolTip(
            _(
                "Drag to orbit, right-drag to pan, wheel to zoom. "
                "F frames the room, R resets the angle."
            )
        )

    # --- painting -----------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        first = self.camera.width == 640 and self.camera.height == 480
        self.camera.width, self.camera.height = self.width(), self.height()
        if first:
            self.camera.fit(*self.scene.bounds())

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        t = tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(t["surface"]))
        self.camera.width, self.camera.height = self.width(), self.height()
        scene = self.scene
        layers = scene.layers
        text = QColor(t["text"])
        entered = QColor(t["accent"])
        measured = QColor(t["warn"])
        assumed = QColor(t["muted"])
        self._draw_floor_grid(painter, QColor(t["border"]))
        if layers.get(LAYER_ENTERED, True) and scene.box is not None:
            self._draw_floor(painter, scene.box)
        if layers.get(LAYER_ENTERED, True):
            if scene.scan_points is not None and scene.scan_points.size:
                self._draw_points(painter, scene.scan_points, QColor(t["muted"]))
            if scene.box is not None:
                self._draw_box(painter, scene.box, QPen(entered, 1.6, LAYER_STYLE[LAYER_ENTERED]))
        if layers.get(LAYER_ASSUMED, True) and scene.source is not None:
            mic = scene.microphones.get(scene.current_microphone)
            if mic is not None:
                for path in scene.predicted:
                    highlighted = path.face in scene.highlighted_faces
                    # Unselected paths are the assumption, and only when asked for in full.
                    if not highlighted and not scene.constraints_full:
                        continue
                    color = QColor(measured if highlighted else assumed)
                    if not highlighted:
                        color.setAlpha(70)
                    pen = QPen(
                        color,
                        2.2 if highlighted else 1.0,
                        LAYER_STYLE[LAYER_ASSUMED],
                    )
                    self._draw_polyline(
                        painter,
                        np.array([scene.source.as_tuple(), path.point.as_tuple(), mic.as_tuple()]),
                        pen,
                    )
                    self._draw_dot(painter, path.point, color, 5 if highlighted else 3)
        if layers.get(LAYER_MEASURED, True):
            pen = QPen(measured, 1.3, LAYER_STYLE[LAYER_MEASURED])
            if scene.constraints_full and scene.sphere is not None:
                for line in circle_lines(*scene.sphere):
                    self._draw_polyline(painter, line, pen)
            if scene.ellipsoid is not None:
                for line in ellipsoid_lines(*scene.ellipsoid, detail=scene.constraints_full):
                    self._draw_polyline(painter, line, QPen(measured, 1.8, pen.style()))
            if scene.placement_ring is not None:
                ring_color = QColor(measured)
                if not scene.constraints_full:
                    ring_color.setAlpha(110)
                self._draw_polyline(
                    painter,
                    ring_line(*scene.placement_ring),
                    QPen(ring_color, 2.0 if scene.constraints_full else 1.2, pen.style()),
                )
        if layers.get(LAYER_ENTERED, True):
            if scene.source is not None:
                self._draw_device(
                    painter,
                    scene.source,
                    _("Loudspeaker"),
                    entered,
                    square=True,
                    key="source",
                )
            for name, mic in scene.microphones.items():
                current = name == scene.current_microphone
                self._draw_device(
                    painter,
                    mic,
                    _("Microphone {position}").format(position=name),
                    entered if current else assumed,
                    square=False,
                    key=name,
                )
            if scene.box is not None and scene.selection.startswith("face:"):
                self._draw_face(
                    painter, scene.box, scene.selection.removeprefix("face:"), QColor(t["bad"])
                )
        self._draw_dimensions(painter, text)
        if layers.get(LAYER_ENTERED, True) and scene.box is not None:
            self._draw_edge_labels(painter, scene.box, text)
            self._draw_front_edge(painter, scene.box, entered)
        self._draw_triad(painter)
        self._draw_scale_bar(painter, text)
        legend_bottom = self._draw_legend(painter, text, entered, measured, assumed)
        self._draw_view_caption(painter, text, legend_bottom)
        if self.hud:
            painter.setPen(text)
            painter.drawText(
                QRectF(12, legend_bottom + 36, max(40.0, self.width() * 0.62), 40),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                self.hud,
            )
        if self.empty_text:
            painter.setPen(QColor(t["muted"]))
            painter.drawText(
                QRectF(self.rect()).adjusted(30, 30, -30, -30),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self.empty_text,
            )
        painter.end()

    def _draw_polyline(self, painter: QPainter, points: NDArray[np.float64], pen: QPen) -> None:
        screen, visible = self.camera.project(points)
        painter.setPen(pen)
        run: list[QPointF] = []
        for (sx, sy), ok in zip(screen, visible, strict=True):
            if ok and math.isfinite(sx) and math.isfinite(sy):
                run.append(QPointF(float(sx), float(sy)))
                continue
            if len(run) > 1:
                painter.drawPolyline(QPolygonF(run))
            run = []
        if len(run) > 1:
            painter.drawPolyline(QPolygonF(run))

    def _draw_box(self, painter: QPainter, box: RoomBox, pen: QPen) -> None:
        corners = _box_corners(box)
        edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7)]
        edges += [(0, 4), (1, 5), (2, 6), (3, 7)]
        for a, b in edges:
            self._draw_polyline(painter, corners[[a, b]], pen)

    def _draw_floor_grid(self, painter: QPainter, color: QColor) -> None:
        low, high = self.scene.bounds()
        step = 1.0
        x0, x1 = math.floor(low[0]) - 1, math.ceil(high[0]) + 1
        y0, y1 = math.floor(low[1]) - 1, math.ceil(high[1]) + 1
        pen = QPen(color, 0.8)
        for x in np.arange(x0, x1 + step / 2, step):
            self._draw_polyline(painter, np.array([[x, y0, 0.0], [x, y1, 0.0]]), pen)
        for y in np.arange(y0, y1 + step / 2, step):
            self._draw_polyline(painter, np.array([[x0, y, 0.0], [x1, y, 0.0]]), pen)

    def _draw_points(self, painter: QPainter, points: NDArray[np.float64], color: QColor) -> None:
        screen, visible = self.camera.project(points)
        color = QColor(color)
        color.setAlpha(140)
        painter.setPen(QPen(color, 1.6))
        painter.drawPoints(
            QPolygonF(
                [
                    QPointF(float(x), float(y))
                    for (x, y), ok in zip(screen, visible, strict=True)
                    if ok
                ]
            )
        )

    def _draw_dot(self, painter: QPainter, point: Point, color: QColor, radius: float) -> None:
        screen, visible = self.camera.project(np.array([point.as_tuple()]))
        if not visible[0]:
            return
        painter.setPen(QPen(color, 1.0))
        painter.setBrush(color)
        painter.drawEllipse(QPointF(*screen[0]), radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_dimensions(self, painter: QPainter, text: QColor) -> None:
        box = self.scene.box
        if box is None:
            return
        length, width, height = box.dimensions
        painter.setPen(text)
        painter.drawText(
            QRectF(self.width() - 230, 8, 218, 32),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            _("{length:.2f} × {width:.2f} × {height:.2f} m").format(
                length=length, width=width, height=height
            ),
        )

    def _draw_face(self, painter: QPainter, box: RoomBox, face: str, color: QColor) -> None:
        corners = _box_corners(box)
        indices = _FACE_CORNERS.get(face)
        if indices is None:
            return
        self._draw_polyline(painter, corners[list(indices + indices[:1])], QPen(color, 2.6))

    def _draw_device(
        self,
        painter: QPainter,
        point: Point,
        name: str,
        color: QColor,
        *,
        square: bool,
        key: str,
    ) -> None:
        screen, visible = self.camera.project(np.array([point.as_tuple()]))
        if not visible[0]:
            return
        centre = QPointF(*screen[0])
        # A drop line to the floor shows the height in the 3D view.
        if not self.camera.plan:
            floor, ok = self.camera.project(np.array([[point.x, point.y, 0.0]]))
            if ok[0]:
                painter.setPen(QPen(color, 1.0, Qt.PenStyle.SolidLine))
                painter.drawLine(centre, QPointF(*floor[0]))
        painter.setPen(QPen(QColor(tokens()["surface"]), 1.5))
        painter.setBrush(color)
        if square:
            painter.drawRect(QRectF(centre.x() - 6, centre.y() - 6, 12, 12))
        else:
            painter.drawEllipse(centre, 6.5, 6.5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.scene.selection == key or key == self.scene.current_microphone:
            painter.setPen(QPen(color, 2.2))
            painter.drawEllipse(centre, 12, 12)
        # Other microphones stay dots. The loudspeaker and the current one are named.
        if key == "source" or key == self.scene.current_microphone or self.scene.selection == key:
            painter.setPen(QColor(tokens()["text"]))
            painter.drawText(centre + QPointF(9, -8), name)

    def _draw_triad(self, painter: QPainter) -> None:
        origin = QPointF(36, self.height() - 36)
        t = tokens()
        colors = {"x": QColor(t["bad"]), "y": QColor(t["good"]), "z": QColor(t["accent"])}
        if self.camera.plan:
            vectors = {"x": (1.0, 0.0), "y": (0.0, -1.0)}
        else:
            right, up, _forward = self.camera.basis()
            vectors = {
                name: (float(right[i]), float(-up[i])) for i, name in enumerate(("x", "y", "z"))
            }
        for name, (dx, dy) in vectors.items():
            end = origin + QPointF(dx * 32, dy * 32)
            painter.setPen(QPen(colors[name], 2.2))
            painter.drawLine(origin, end)
            painter.drawText(end + QPointF(3, 4), name)
        painter.setPen(QColor(t["text"]))
        painter.drawText(QPointF(78, self.height() - 28), _("x length · y width · z up"))

    def _draw_scale_bar(self, painter: QPainter, text: QColor) -> None:
        per_px = self.camera.metres_per_pixel()
        if not per_px > 0:
            return
        target_px = 110.0
        raw = per_px * target_px
        magnitude = 10 ** math.floor(math.log10(raw))
        nice = min((1, 2, 5, 10), key=lambda m: abs(m * magnitude - raw)) * magnitude
        length_px = nice / per_px
        right = self.width() - 20.0
        y = self.height() - 22.0
        painter.setPen(QPen(text, 2.0))
        painter.drawLine(QPointF(right - length_px, y), QPointF(right, y))
        painter.drawLine(QPointF(right - length_px, y - 4), QPointF(right - length_px, y + 4))
        painter.drawLine(QPointF(right, y - 4), QPointF(right, y + 4))
        label = f"{nice:g} m"
        if not self.camera.plan:
            label = _("{length} at the centre").format(length=label)
        painter.drawText(QPointF(right - length_px, y - 7), label)

    def _draw_legend(
        self, painter: QPainter, text: QColor, entered: QColor, measured: QColor, assumed: QColor
    ) -> float:
        """Draw the layer key and return the y under the last line."""
        y = 18.0
        for layer, color in (
            (LAYER_ENTERED, entered),
            (LAYER_MEASURED, measured),
            (LAYER_ASSUMED, assumed),
        ):
            if not self.scene.layers.get(layer, True):
                continue
            painter.setPen(QPen(color, 2.0, LAYER_STYLE[layer]))
            painter.drawLine(QPointF(12, y), QPointF(40, y))
            painter.setPen(text)
            painter.drawText(QPointF(46, y + 4), _(LAYER_NAMES[layer]))
            y += 18.0
        return y

    def _draw_view_caption(self, painter: QPainter, text: QColor, top: float) -> None:
        painter.setPen(text)
        painter.drawText(
            QRectF(12, top + 2, min(340.0, max(80.0, self.width() - 160.0)), 34),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            view_caption(self.camera.preset_name),
        )

    def _draw_floor(self, painter: QPainter, box: RoomBox) -> None:
        """A faint fill on the entered floor so the ground plane reads."""
        indices = _FACE_CORNERS["z0"]
        corners = _box_corners(box)
        screen, visible = self.camera.project(corners)
        if not all(bool(visible[i]) for i in indices):
            return
        color = QColor(tokens()["accent"])
        color.setAlpha(36)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(
            QPolygonF([QPointF(float(screen[i][0]), float(screen[i][1])) for i in indices])
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _label_world(self, painter: QPainter, point: tuple[float, float, float], text: str) -> None:
        screen, visible = self.camera.project(np.array([point]))
        if not bool(visible[0]) or not math.isfinite(screen[0][0]):
            return
        painter.drawText(QPointF(float(screen[0][0]) + 6, float(screen[0][1]) - 4), text)

    def _draw_edge_labels(self, painter: QPainter, box: RoomBox, text: QColor) -> None:
        """Length, width and height written on the edges they measure."""
        length, width, height = box.dimensions
        painter.setPen(text)
        # Length sits on the far edge so it does not cover the front mark.
        self._label_world(painter, (length / 2.0, width, 0.08), _metres(length))
        self._label_world(painter, (length, width / 2.0, 0.08), _metres(width))
        if not self.camera.plan:
            self._label_world(painter, (length, 0.0, height / 2.0), _metres(height))

    def _draw_front_edge(self, painter: QPainter, box: RoomBox, color: QColor) -> None:
        """Mark the entered face at y = 0. It is not a wall the measurement found."""
        length, _width, _height = box.dimensions
        pen = QPen(color, 1.8, Qt.PenStyle.SolidLine)
        self._draw_polyline(
            painter,
            np.array([[length / 2.0, -0.72, 0.0], [length / 2.0, -0.12, 0.0]]),
            pen,
        )
        painter.setPen(color)
        self._label_world(painter, (length / 2.0, -0.78, 0.0), _("Front edge"))

    # --- picking --------------------------------------------------------------------------

    def device_at(self, pos: QPointF) -> tuple[str, Point] | None:
        candidates: list[tuple[str, Point]] = []
        if self.scene.source is not None:
            candidates.append(("source", self.scene.source))
        candidates += list(self.scene.microphones.items())
        best: tuple[float, str, Point] | None = None
        for name, point in candidates:
            screen, visible = self.camera.project(np.array([point.as_tuple()]))
            if not visible[0]:
                continue
            distance = math.hypot(screen[0][0] - pos.x(), screen[0][1] - pos.y())
            if distance <= PICK_PX and (best is None or distance < best[0]):
                best = (distance, name, point)
        return None if best is None else (best[1], best[2])

    def surface_at(self, pos: QPointF) -> str:
        """The entered face under ``pos``, or ``""``.

        A hit names the box the user typed. It is not a surface a measurement
        located. In the plan view the footprint is the floor (z = 0).
        """
        box = self.scene.box
        if box is None or not self.scene.layers.get(LAYER_ENTERED, True):
            return ""
        if self.camera.plan:
            x, y = self.camera.unproject_plan(pos.x(), pos.y())
            length, width, _height = box.dimensions
            if 0.0 <= x <= length and 0.0 <= y <= width:
                return "z0"
            return ""
        corners = _box_corners(box)
        screen, visible = self.camera.project(corners)
        eye = self.camera.eye()
        _right, _up, forward = self.camera.basis()
        best: tuple[float, str] | None = None
        for face, indices in _FACE_CORNERS.items():
            if not all(bool(visible[i]) for i in indices):
                continue
            polygon = [(float(screen[i][0]), float(screen[i][1])) for i in indices]
            if not _point_in_polygon(pos.x(), pos.y(), polygon):
                continue
            depth = float(np.mean((corners[list(indices)] - eye) @ forward))
            if best is None or depth < best[0]:
                best = (depth, face)
        return "" if best is None else best[1]

    def face_at(self, pos: QPointF) -> str:
        if not self.scene.layers.get(LAYER_ASSUMED, True):
            return ""
        for path in self.scene.predicted:
            screen, visible = self.camera.project(np.array([path.point.as_tuple()]))
            if visible[0] and math.hypot(screen[0][0] - pos.x(), screen[0][1] - pos.y()) <= PICK_PX:
                return path.face
        return ""

    # --- mouse ----------------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        self._press = event.position()
        self._last = event.position()
        self._button = event.button()
        self._moved = False
        self._dragging_device = ""
        if self.camera.plan and event.button() == Qt.MouseButton.LeftButton:
            hit = self.device_at(event.position())
            if hit is not None:
                self._dragging_device = hit[0]
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if self._last is None:
            return
        delta = event.position() - self._last
        self._last = event.position()
        if self._press is not None and (event.position() - self._press).manhattanLength() > 3:
            self._moved = True
        if self._dragging_device:
            x, y = self.camera.unproject_plan(event.position().x(), event.position().y())
            point = self._device_point(self._dragging_device)
            if point is not None:
                moved = Point(round(x, 2), round(y, 2), point.z)
                self._set_device_point(self._dragging_device, moved)
                self.update()
            return
        if self._button == Qt.MouseButton.LeftButton:
            self.camera.orbit(delta.x(), delta.y())
        else:
            self.camera.pan(delta.x(), delta.y())
        self.camera_changed.emit()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if self._dragging_device and self._moved:
            point = self._device_point(self._dragging_device)
            if point is not None:
                self.device_moved.emit(self._dragging_device, point)
        elif not self._moved and event.button() == Qt.MouseButton.LeftButton:
            hit = self.device_at(event.position())
            if hit is not None:
                self.device_clicked.emit(hit[0], hit[1])
            else:
                face = self.face_at(event.position())
                if face:
                    self.face_clicked.emit(face)
                else:
                    surface = self.surface_at(event.position())
                    if surface:
                        self.surface_clicked.emit(surface)
        self._press = None
        self._last = None
        self._dragging_device = ""

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        self.fit()
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override
        steps = event.angleDelta().y() / 120.0
        if steps:
            pos = event.position()
            self.camera.zoom_at(pos.x(), pos.y(), 0.85**steps)
            self.camera_changed.emit()
            self.update()
        event.accept()

    def keyPressEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        from PySide6.QtGui import QKeyEvent

        assert isinstance(event, QKeyEvent)
        if event.key() in (Qt.Key.Key_F, Qt.Key.Key_R) and not event.modifiers():
            self.reset() if event.key() == Qt.Key.Key_R else self.fit()
            return
        super().keyPressEvent(event)

    def _device_point(self, name: str) -> Point | None:
        if name == "source":
            return self.scene.source
        return self.scene.microphones.get(name)

    def _set_device_point(self, name: str, point: Point) -> None:
        if name == "source":
            self.scene.source = point
        else:
            self.scene.microphones[name] = point
