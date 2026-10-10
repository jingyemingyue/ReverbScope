"""An orbit camera for the room view, in plain numbers (no Qt, no OpenGL).

``project`` turns room coordinates (m; x length, y width, z up) into widget
pixels. The 3D mode is a perspective camera orbiting a target; the plan mode
looks straight down with an orthographic scale, so distances on screen are
true to scale and devices can be dragged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

DEFAULT_YAW_DEG = -55.0
DEFAULT_PITCH_DEG = 28.0
FIELD_OF_VIEW_DEG = 45.0
#: Points closer to the eye than this (m) are not drawn.
NEAR_M = 0.05
MIN_DISTANCE_M = 0.3
MAX_DISTANCE_M = 2000.0


@dataclass
class OrbitCamera:
    yaw_deg: float = DEFAULT_YAW_DEG
    pitch_deg: float = DEFAULT_PITCH_DEG
    distance_m: float = 10.0
    target: tuple[float, float, float] = (0.0, 0.0, 0.0)
    #: True: look straight down, orthographic (the plan view).
    plan: bool = False
    #: Pixels per metre in the plan view.
    plan_scale: float = 60.0
    width: int = 640
    height: int = 480

    # --- basis ------------------------------------------------------------------------

    @property
    def focal_px(self) -> float:
        return 0.5 * min(self.width, self.height) / math.tan(math.radians(FIELD_OF_VIEW_DEG) / 2)

    def eye(self) -> NDArray[np.float64]:
        yaw = math.radians(self.yaw_deg)
        pitch = math.radians(self.pitch_deg)
        offset = np.array(
            [
                math.cos(pitch) * math.cos(yaw),
                math.cos(pitch) * math.sin(yaw),
                math.sin(pitch),
            ]
        )
        return np.asarray(self.target, dtype=np.float64) + self.distance_m * offset

    def basis(self) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
        """``(right, up, forward)`` unit vectors of the 3D camera."""
        forward = np.asarray(self.target, dtype=np.float64) - self.eye()
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, np.array([0.0, 0.0, 1.0]))
        norm = float(np.linalg.norm(right))
        right = right / norm if norm > 1e-9 else np.array([1.0, 0.0, 0.0])
        up = np.cross(right, forward)
        return right, up, forward

    # --- projection ---------------------------------------------------------------------

    def project(self, points: NDArray[np.float64]) -> tuple[NDArray[np.float64], NDArray[np.bool_]]:
        """Pixel coordinates ``(n, 2)`` of ``points`` ``(n, 3)`` and which are drawable."""
        pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        cx, cy = self.width / 2.0, self.height / 2.0
        if self.plan:
            tx, ty, _tz = self.target
            screen = np.column_stack(
                (cx + self.plan_scale * (pts[:, 0] - tx), cy - self.plan_scale * (pts[:, 1] - ty))
            )
            return screen, np.ones(pts.shape[0], dtype=bool)
        right, up, forward = self.basis()
        rel = pts - self.eye()
        x = rel @ right
        y = rel @ up
        z = rel @ forward
        visible = z > NEAR_M
        safe = np.where(visible, z, 1.0)
        focal = self.focal_px
        screen = np.column_stack((cx + focal * x / safe, cy - focal * y / safe))
        return screen, visible

    def unproject_plan(self, sx: float, sy: float) -> tuple[float, float]:
        """Room ``(x, y)`` under pixel ``(sx, sy)`` in the plan view."""
        tx, ty, _tz = self.target
        return (
            tx + (sx - self.width / 2.0) / self.plan_scale,
            ty - (sy - self.height / 2.0) / self.plan_scale,
        )

    def metres_per_pixel(self) -> float:
        """At the target's depth (3D) or everywhere (plan): for the scale bar and panning."""
        if self.plan:
            return 1.0 / self.plan_scale
        return self.distance_m / self.focal_px

    # --- moving ---------------------------------------------------------------------------

    def orbit(self, dx_px: float, dy_px: float) -> None:
        if self.plan:
            self.pan(dx_px, dy_px)
            return
        self.yaw_deg = (self.yaw_deg - 0.4 * dx_px) % 360.0
        self.pitch_deg = max(-85.0, min(85.0, self.pitch_deg + 0.4 * dy_px))

    def pan(self, dx_px: float, dy_px: float) -> None:
        scale = self.metres_per_pixel()
        if self.plan:
            tx, ty, tz = self.target
            self.target = (tx - dx_px * scale, ty + dy_px * scale, tz)
            return
        right, up, _forward = self.basis()
        shift = (-dx_px * right + dy_px * up) * scale
        self.target = tuple(float(v) for v in np.asarray(self.target) + shift)  # type: ignore[assignment]

    def zoom_at(self, sx: float, sy: float, factor: float) -> None:
        """Zoom by ``factor`` (<1 closer) keeping the point under ``(sx, sy)`` in place."""
        if self.plan:
            before = self.unproject_plan(sx, sy)
            self.plan_scale = max(2.0, min(5000.0, self.plan_scale / factor))
            after = self.unproject_plan(sx, sy)
            tx, ty, tz = self.target
            self.target = (tx + before[0] - after[0], ty + before[1] - after[1], tz)
            return
        right, up, forward = self.basis()
        focal = self.focal_px
        cx, cy = self.width / 2.0, self.height / 2.0
        ray = forward + right * (sx - cx) / focal - up * (sy - cy) / focal
        under = self.eye() + ray * self.distance_m
        new_distance = max(MIN_DISTANCE_M, min(MAX_DISTANCE_M, self.distance_m * factor))
        applied = new_distance / self.distance_m
        target = under + (np.asarray(self.target) - under) * applied
        self.target = (float(target[0]), float(target[1]), float(target[2]))
        self.distance_m = new_distance

    def fit(self, low: NDArray[np.float64], high: NDArray[np.float64]) -> None:
        """Frame the box ``low``..``high`` (m)."""
        low = np.asarray(low, dtype=np.float64)
        high = np.asarray(high, dtype=np.float64)
        centre = (low + high) / 2.0
        radius = max(0.5, float(np.linalg.norm(high - low)) / 2.0)
        self.target = (float(centre[0]), float(centre[1]), float(centre[2]))
        self.distance_m = radius / math.sin(math.radians(FIELD_OF_VIEW_DEG) / 2.0) * 1.05
        span_x = max(0.5, float(high[0] - low[0]))
        span_y = max(0.5, float(high[1] - low[1]))
        self.plan_scale = 0.85 * min(self.width / span_x, self.height / span_y)

    def reset(self, low: NDArray[np.float64], high: NDArray[np.float64]) -> None:
        self.yaw_deg = DEFAULT_YAW_DEG
        self.pitch_deg = DEFAULT_PITCH_DEG
        self.fit(low, high)
