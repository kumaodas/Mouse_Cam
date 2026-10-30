"""
Domain Value Objects for Gesture Mouse.
Immutable, self-validating data structures representing mathematical and spatial concepts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from gesture_mouse.domain.models import NormalizedPoint


class MouseButton(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


@dataclass(frozen=True)
class ScreenCoordinate:
    """Screen pixel coordinate (x, y)."""
    x: int
    y: int

    def to_tuple(self) -> Tuple[int, int]:
        return (self.x, self.y)

    def clamp(self, min_x: int, min_y: int, max_x: int, max_y: int) -> ScreenCoordinate:
        clamped_x = max(min_x, min(self.x, max_x))
        clamped_y = max(min_y, min(self.y, max_y))
        return ScreenCoordinate(clamped_x, clamped_y)


@dataclass(frozen=True)
class ScreenSize:
    """Resolution of target display."""
    width: int
    height: int

    def __post_init__(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Screen dimensions must be positive, got {self.width}x{self.height}")


@dataclass(frozen=True)
class Distance:
    """Euclidean distance utility."""
    @staticmethod
    def euclidean_2d(p1: NormalizedPoint, p2: NormalizedPoint) -> float:
        """Calculate 2D Euclidean distance between two points."""
        dx = p1.x - p2.x
        dy = p1.y - p2.y
        return math.hypot(dx, dy)

    @staticmethod
    def euclidean_3d(p1: NormalizedPoint, p2: NormalizedPoint) -> float:
        """Calculate 3D Euclidean distance between two points."""
        dx = p1.x - p2.x
        dy = p1.y - p2.y
        dz = p1.z - p2.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)


@dataclass(frozen=True)
class InteractionZone:
    """
    Active bounding box in normalized camera space [0.0, 1.0].
    Allows controlling full screen range comfortably without reaching physical camera boundaries.
    Uses asymmetric vertical margins (larger bottom margin) because the wrist and arm enter from below.
    """
    margin_x: Optional[float] = None
    margin_y: Optional[float] = None
    margin_left: float = 0.18
    margin_right: float = 0.18
    margin_top: float = 0.12
    margin_bottom: float = 0.35

    def __post_init__(self):
        # Backward compatibility if legacy margin_x or margin_y provided
        if self.margin_x is not None:
            object.__setattr__(self, "margin_left", self.margin_x)
            object.__setattr__(self, "margin_right", self.margin_x)
        if self.margin_y is not None:
            object.__setattr__(self, "margin_top", self.margin_y)
            object.__setattr__(self, "margin_bottom", self.margin_y)

        if not (0.0 <= self.margin_left < 0.45 and 0.0 <= self.margin_right < 0.45):
            raise ValueError(f"Horizontal margins must be between 0.0 and 0.45, got ({self.margin_left}, {self.margin_right})")
        if not (0.0 <= self.margin_top < 0.45 and 0.0 <= self.margin_bottom < 0.60):
            raise ValueError(f"Vertical margins invalid, got top={self.margin_top}, bottom={self.margin_bottom}")

    @property
    def x_min(self) -> float:
        return self.margin_left

    @property
    def x_max(self) -> float:
        return 1.0 - self.margin_right

    @property
    def y_min(self) -> float:
        return self.margin_top

    @property
    def y_max(self) -> float:
        return 1.0 - self.margin_bottom

    def map_to_screen(self, point: NormalizedPoint, screen_size: ScreenSize) -> ScreenCoordinate:
        """
        Linearly interpolate normalized point within the active zone to target screen coordinates.
        Clamps values outside the active zone to screen borders so all corners and edges are reachable.
        """
        span_x = max(0.01, self.x_max - self.x_min)
        span_y = max(0.01, self.y_max - self.y_min)

        # Normalized position within zone [0, 1]
        norm_x = (point.x - self.x_min) / span_x
        norm_y = (point.y - self.y_min) / span_y

        # Clamping ensures the cursor reaches edges and stays locked at the border
        norm_x = max(0.0, min(1.0, norm_x))
        norm_y = max(0.0, min(1.0, norm_y))

        # Project to target screen resolution
        screen_x = int(round(norm_x * (screen_size.width - 1)))
        screen_y = int(round(norm_y * (screen_size.height - 1)))

        return ScreenCoordinate(screen_x, screen_y)
