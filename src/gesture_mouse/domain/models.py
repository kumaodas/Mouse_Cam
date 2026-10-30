"""
Domain models for Gesture Mouse.
Represents pure business entities without external framework dependencies.
"""

from __future__ import annotations

from enum import Enum, IntEnum
from typing import Dict, Optional, Any
from dataclasses import dataclass, field


class HandLandmarkId(IntEnum):
    """MediaPipe 21 standard hand landmark indices."""
    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4
    INDEX_FINGER_MCP = 5
    INDEX_FINGER_PIP = 6
    INDEX_FINGER_DIP = 7
    INDEX_FINGER_TIP = 8
    MIDDLE_FINGER_MCP = 9
    MIDDLE_FINGER_PIP = 10
    MIDDLE_FINGER_DIP = 11
    MIDDLE_FINGER_TIP = 12
    RING_FINGER_MCP = 13
    RING_FINGER_PIP = 14
    RING_FINGER_DIP = 15
    RING_FINGER_TIP = 16
    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20


class Handedness(str, Enum):
    """Hand identity."""
    LEFT = "Left"
    RIGHT = "Right"
    UNKNOWN = "Unknown"


class GestureType(str, Enum):
    """Identified gesture states."""
    IDLE = "IDLE"
    MOVE = "MOVE"
    LEFT_CLICK = "LEFT_CLICK"
    RIGHT_CLICK = "RIGHT_CLICK"
    DRAGGING = "DRAGGING"
    SCROLLING = "SCROLLING"
    STABILIZING = "STABILIZING"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"


@dataclass(frozen=True)
class NormalizedPoint:
    """A 3D point normalized within [0.0, 1.0] relative to frame dimensions."""
    x: float
    y: float
    z: float = 0.0

    def to_tuple_2d(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class Hand:
    """Represents a tracked hand entity with all landmark points."""
    landmarks: Dict[HandLandmarkId, NormalizedPoint]
    handedness: Handedness = Handedness.RIGHT
    score: float = 1.0

    def get_landmark(self, landmark_id: HandLandmarkId) -> Optional[NormalizedPoint]:
        return self.landmarks.get(landmark_id)

    @property
    def index_tip(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.INDEX_FINGER_TIP]

    @property
    def thumb_tip(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.THUMB_TIP]

    @property
    def middle_tip(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.MIDDLE_FINGER_TIP]

    @property
    def ring_tip(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.RING_FINGER_TIP]

    @property
    def pinky_tip(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.PINKY_TIP]

    @property
    def wrist(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.WRIST]

    @property
    def index_pip(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.INDEX_FINGER_PIP]

    @property
    def index_mcp(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.INDEX_FINGER_MCP]

    @property
    def middle_pip(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.MIDDLE_FINGER_PIP]

    @property
    def middle_mcp(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.MIDDLE_FINGER_MCP]

    @property
    def ring_pip(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.RING_FINGER_PIP]

    @property
    def ring_mcp(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.RING_FINGER_MCP]

    @property
    def pinky_pip(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.PINKY_PIP]

    @property
    def pinky_mcp(self) -> NormalizedPoint:
        return self.landmarks[HandLandmarkId.PINKY_MCP]

    def finger_extension_ratio(
        self,
        tip_id: HandLandmarkId,
        pip_id: HandLandmarkId,
        mcp_id: HandLandmarkId,
    ) -> float:
        """
        Calculates scale-invariant ratio of (Tip to MCP distance) / (PIP to MCP distance).
        When extended: ratio is ~1.8 to 2.4.
        When bent/clicked: ratio drops below 1.3.
        """
        import math
        tip = self.landmarks.get(tip_id)
        pip = self.landmarks.get(pip_id)
        mcp = self.landmarks.get(mcp_id)
        if not tip or not pip or not mcp:
            return 2.0

        # Calculate 3D Euclidean distance for tilt-invariant finger tracking
        dx_tip = tip.x - mcp.x
        dy_tip = tip.y - mcp.y
        dz_tip = tip.z - mcp.z
        d_tip_mcp = math.sqrt(dx_tip * dx_tip + dy_tip * dy_tip + dz_tip * dz_tip)

        dx_pip = pip.x - mcp.x
        dy_pip = pip.y - mcp.y
        dz_pip = pip.z - mcp.z
        d_pip_mcp = math.sqrt(dx_pip * dx_pip + dy_pip * dy_pip + dz_pip * dz_pip)

        if d_pip_mcp < 0.001:
            return 2.0
        return d_tip_mcp / d_pip_mcp

    def is_finger_extended(self, tip_id: HandLandmarkId, pip_id: HandLandmarkId) -> bool:
        """Check if finger tip is above pip joint in frame coordinates."""
        tip = self.landmarks.get(tip_id)
        pip = self.landmarks.get(pip_id)
        if not tip or not pip:
            return False
        return tip.y < pip.y

    def is_index_extended(self, threshold_ratio: float = 1.55) -> bool:
        """Index is extended if tip is high and extension ratio >= threshold."""
        ratio = self.finger_extension_ratio(
            HandLandmarkId.INDEX_FINGER_TIP,
            HandLandmarkId.INDEX_FINGER_PIP,
            HandLandmarkId.INDEX_FINGER_MCP,
        )
        return self.is_finger_extended(HandLandmarkId.INDEX_FINGER_TIP, HandLandmarkId.INDEX_FINGER_PIP) and ratio >= threshold_ratio

    def is_index_bent(self, bent_ratio: float = 1.40) -> bool:
        """Index is bent/clicked if extension ratio drops or tip falls below pip."""
        tip = self.landmarks.get(HandLandmarkId.INDEX_FINGER_TIP)
        pip = self.landmarks.get(HandLandmarkId.INDEX_FINGER_PIP)
        if not tip or not pip:
            return False
        ratio = self.finger_extension_ratio(
            HandLandmarkId.INDEX_FINGER_TIP,
            HandLandmarkId.INDEX_FINGER_PIP,
            HandLandmarkId.INDEX_FINGER_MCP,
        )
        return ratio < bent_ratio or tip.y >= (pip.y - 0.015)

    def is_middle_extended(self, threshold_ratio: float = 1.55) -> bool:
        ratio = self.finger_extension_ratio(
            HandLandmarkId.MIDDLE_FINGER_TIP,
            HandLandmarkId.MIDDLE_FINGER_PIP,
            HandLandmarkId.MIDDLE_FINGER_MCP,
        )
        return self.is_finger_extended(HandLandmarkId.MIDDLE_FINGER_TIP, HandLandmarkId.MIDDLE_FINGER_PIP) and ratio >= threshold_ratio

    def is_middle_bent(self, bent_ratio: float = 1.40) -> bool:
        tip = self.landmarks.get(HandLandmarkId.MIDDLE_FINGER_TIP)
        pip = self.landmarks.get(HandLandmarkId.MIDDLE_FINGER_PIP)
        if not tip or not pip:
            return False
        ratio = self.finger_extension_ratio(
            HandLandmarkId.MIDDLE_FINGER_TIP,
            HandLandmarkId.MIDDLE_FINGER_PIP,
            HandLandmarkId.MIDDLE_FINGER_MCP,
        )
        return ratio < bent_ratio or tip.y >= (pip.y - 0.015)

    def is_ring_extended(self) -> bool:
        return self.is_finger_extended(HandLandmarkId.RING_FINGER_TIP, HandLandmarkId.RING_FINGER_PIP)

    def is_pinky_extended(self) -> bool:
        return self.is_finger_extended(HandLandmarkId.PINKY_TIP, HandLandmarkId.PINKY_PIP)

    def is_fist(self) -> bool:
        """True if all four main fingers (index, middle, ring, pinky) are curled/bent."""
        return (
            (not self.is_finger_extended(HandLandmarkId.INDEX_FINGER_TIP, HandLandmarkId.INDEX_FINGER_PIP))
            and (not self.is_finger_extended(HandLandmarkId.MIDDLE_FINGER_PIP, HandLandmarkId.MIDDLE_FINGER_MCP) if False else not self.is_finger_extended(HandLandmarkId.MIDDLE_FINGER_TIP, HandLandmarkId.MIDDLE_FINGER_PIP))
            and (not self.is_finger_extended(HandLandmarkId.RING_FINGER_TIP, HandLandmarkId.RING_FINGER_PIP))
            and (not self.is_finger_extended(HandLandmarkId.PINKY_TIP, HandLandmarkId.PINKY_PIP))
        )

    def is_open_palm(self) -> bool:
        """True if all four main fingers are extended."""
        return (
            self.is_finger_extended(HandLandmarkId.INDEX_FINGER_TIP, HandLandmarkId.INDEX_FINGER_PIP)
            and self.is_finger_extended(HandLandmarkId.MIDDLE_FINGER_TIP, HandLandmarkId.MIDDLE_FINGER_PIP)
            and self.is_finger_extended(HandLandmarkId.RING_FINGER_TIP, HandLandmarkId.RING_FINGER_PIP)
            and self.is_finger_extended(HandLandmarkId.PINKY_TIP, HandLandmarkId.PINKY_PIP)
        )

    def is_peace_sign(self) -> bool:
        """True if index and middle are extended while ring and pinky are curled."""
        return (
            self.is_finger_extended(HandLandmarkId.INDEX_FINGER_TIP, HandLandmarkId.INDEX_FINGER_PIP)
            and self.is_finger_extended(HandLandmarkId.MIDDLE_FINGER_TIP, HandLandmarkId.MIDDLE_FINGER_PIP)
            and (not self.is_finger_extended(HandLandmarkId.RING_FINGER_TIP, HandLandmarkId.RING_FINGER_PIP))
            and (not self.is_finger_extended(HandLandmarkId.PINKY_TIP, HandLandmarkId.PINKY_PIP))
        )

    def is_near_camera_edge(self, margin: float = 0.02) -> bool:
        """
        Check if the active control fingers (index tip/mcp) are touching the extreme camera borders.
        Does NOT check wrist near bottom to allow natural arm posture.
        """
        control_points = [
            self.index_tip,
            self.index_mcp,
            self.middle_tip
        ]
        for pt in control_points:
            # Check left, right, and top borders (bottom is allowed for arm)
            if pt.x <= margin or pt.x >= (1.0 - margin) or pt.y <= margin:
                return True
        return False


@dataclass
class GestureEvent:
    """Represents a generated gesture trigger event."""
    gesture_type: GestureType
    timestamp: float
    screen_x: int
    screen_y: int
    details: Dict[str, Any] = field(default_factory=dict)
