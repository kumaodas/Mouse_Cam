"""
Gesture Service Orchestrator.
Coordinates hand tracking, cursor motion, finger flexion click detection (Option A), and scrolling.
Includes camera edge safety lock, stabilization timers, and fail-safe releases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import numpy as np

from gesture_mouse.domain.models import Hand, GestureType, HandLandmarkId, Handedness
from gesture_mouse.domain.value_objects import ScreenCoordinate, Distance
from gesture_mouse.domain.interfaces import IHandTracker
from gesture_mouse.application.use_cases import (
    MoveCursorUseCase,
    DetectClickUseCase,
    ScrollGestureUseCase,
    LeftHandMacroUseCase,
)


@dataclass
class ProcessResult:
    """Consolidated state output for each processed frame."""
    hand: Optional[Hand]
    gesture: GestureType
    cursor_position: Optional[ScreenCoordinate]
    index_ratio: float = 2.0
    middle_ratio: float = 2.0
    is_index_bent: bool = False
    is_middle_bent: bool = False
    scroll_amount: int = 0
    is_out_of_bounds: bool = False
    is_stabilizing: bool = False
    left_pinch_dist: float = 1.0
    right_pinch_dist: float = 1.0
    left_bent_frames: int = 0
    right_bent_frames: int = 0
    click_confirm_frames: int = 4
    left_in_neutral: bool = False
    right_in_neutral: bool = False
    secondary_hand: Optional[Hand] = None
    macro_triggered: Optional[str] = None
    macro_description: str = ""
    is_tracking_paused: bool = False


class GestureService:
    """Core domain orchestrator for gesture mouse processing."""

    def __init__(
        self,
        hand_tracker: IHandTracker,
        move_cursor_uc: MoveCursorUseCase,
        detect_click_uc: DetectClickUseCase,
        scroll_gesture_uc: ScrollGestureUseCase,
        safety_edge_margin: float = 0.04,
        reentry_stabilization_seconds: float = 0.20,
        macro_uc: Optional[LeftHandMacroUseCase] = None,
    ):
        self._tracker = hand_tracker
        self._move_cursor = move_cursor_uc
        self._detect_click = detect_click_uc
        self._scroll = scroll_gesture_uc
        self._safety_edge_margin = safety_edge_margin
        self._reentry_stabilization_seconds = reentry_stabilization_seconds
        self._macro_uc = macro_uc
        self._hand_present_since: Optional[float] = None
        self._is_paused: bool = False

    def process_frame(self, frame: np.ndarray, timestamp: float) -> ProcessResult:
        """
        Processes a single video frame with edge safety locks, stabilization, and finger click detection.
        Supports secondary (Left) hand shortcuts while primary (Right) controls cursor.
        """
        timestamp_ms = int(timestamp * 1000)
        hands = self._tracker.track_all(frame, timestamp_ms)

        # Distribute into primary (cursor) hand and secondary (macro) hand
        primary_hand: Optional[Hand] = None
        secondary_hand: Optional[Hand] = None

        if len(hands) == 1:
            primary_hand = hands[0]
        elif len(hands) >= 2:
            right_hands = [h for h in hands if h.handedness == Handedness.RIGHT]
            left_hands = [h for h in hands if h.handedness == Handedness.LEFT]
            if right_hands:
                primary_hand = right_hands[0]
                secondary_hand = left_hands[0] if left_hands else [h for h in hands if h != primary_hand][0]
            else:
                primary_hand = hands[0]
                secondary_hand = hands[1]

        # Evaluate secondary hand macros if available
        macro_key = None
        macro_desc = ""
        if secondary_hand and self._macro_uc:
            macro_key, macro_desc = self._macro_uc.execute(secondary_hand, timestamp)
            if macro_key == "TOGGLE_PAUSE":
                self._is_paused = not self._is_paused

        hand = primary_hand

        # If user toggled pause mode via Left Hand open palm: freeze tracking
        if self._is_paused:
            self._move_cursor.reset_smoother()
            self._detect_click.release_all()
            self._scroll.reset()
            return ProcessResult(
                hand=hand,
                gesture=GestureType.IDLE,
                cursor_position=None,
                secondary_hand=secondary_hand,
                macro_triggered=macro_key,
                macro_description="TRACKING PAUSADO [Palma Izq]" if not macro_desc else macro_desc,
                is_tracking_paused=True,
            )

        # Case 1: No primary hand detected in frame -> Immediate hard freeze & safety release
        if hand is None:
            self._hand_present_since = None
            self._move_cursor.reset_smoother()
            self._detect_click.release_all()
            self._scroll.reset()
            return ProcessResult(
                hand=None,
                gesture=GestureType.IDLE,
                cursor_position=None,
                secondary_hand=secondary_hand,
                macro_triggered=macro_key,
                macro_description=macro_desc,
                is_tracking_paused=False,
            )

        # Case 2: Hand is at or beyond camera safety edge -> Lock cursor & abort all actions
        if hand.is_near_camera_edge(self._safety_edge_margin):
            self._hand_present_since = None
            self._move_cursor.reset_smoother()
            self._detect_click.release_all()
            self._scroll.reset()
            return ProcessResult(
                hand=hand,
                gesture=GestureType.OUT_OF_BOUNDS,
                cursor_position=None,
                is_out_of_bounds=True,
                secondary_hand=secondary_hand,
                macro_triggered=macro_key,
                macro_description=macro_desc,
                is_tracking_paused=False,
            )

        # Track hand presence duration inside safe zone
        if self._hand_present_since is None:
            self._hand_present_since = timestamp

        presence_duration = timestamp - self._hand_present_since

        # Case 3: Re-entry stabilization period -> allow cursor positioning, lock all clicks
        if presence_duration < self._reentry_stabilization_seconds:
            self._detect_click.release_all()
            self._scroll.reset()
            cursor_pos = self._move_cursor.execute(hand, timestamp, lock_position=False)
            r_idx = hand.finger_extension_ratio(
                HandLandmarkId.INDEX_FINGER_TIP,
                HandLandmarkId.INDEX_FINGER_PIP,
                HandLandmarkId.INDEX_FINGER_MCP,
            )
            r_mid = hand.finger_extension_ratio(
                HandLandmarkId.MIDDLE_FINGER_TIP,
                HandLandmarkId.MIDDLE_FINGER_PIP,
                HandLandmarkId.MIDDLE_FINGER_MCP,
            )
            return ProcessResult(
                hand=hand,
                gesture=GestureType.STABILIZING,
                cursor_position=cursor_pos,
                index_ratio=r_idx,
                middle_ratio=r_mid,
                is_stabilizing=True,
                secondary_hand=secondary_hand,
                macro_triggered=macro_key,
                macro_description=macro_desc,
                is_tracking_paused=False,
            )

        # Case 4: Fully stable hand inside safe zone -> normal operation
        # 4.1 Evaluate Scroll Gesture
        is_scrolling, scroll_amount = self._scroll.execute(hand, timestamp)
        if is_scrolling:
            self._detect_click.release_all()
            return ProcessResult(
                hand=hand,
                gesture=GestureType.SCROLLING,
                cursor_position=None,
                scroll_amount=scroll_amount,
                secondary_hand=secondary_hand,
                macro_triggered=macro_key,
                macro_description=macro_desc,
                is_tracking_paused=False,
            )

        # 4.2 Click / Drag Evaluation (Option A: Physical Finger Flexion)
        gesture, r_idx, r_mid = self._detect_click.execute(hand, timestamp)

        # 4.3 Cursor Positioning (Anti-Slip Pre-Click Anchor Lock for Left & Right Clicks)
        is_clicking = gesture in (GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK)
        is_dragging = self._detect_click.is_dragging
        cursor_pos = self._move_cursor.execute(
            hand=hand,
            timestamp=timestamp,
            lock_position=is_clicking,
            allow_drag_motion=is_dragging,
        )

        d_lp = Distance.euclidean_2d(hand.thumb_tip, hand.index_tip)
        d_rp = Distance.euclidean_2d(hand.thumb_tip, hand.middle_tip)

        return ProcessResult(
            hand=hand,
            gesture=gesture,
            cursor_position=cursor_pos,
            index_ratio=r_idx,
            middle_ratio=r_mid,
            is_index_bent=hand.is_index_bent(self._detect_click._settings.finger_bent_ratio),
            is_middle_bent=hand.is_middle_bent(self._detect_click._settings.finger_bent_ratio),
            left_pinch_dist=d_lp,
            right_pinch_dist=d_rp,
            left_bent_frames=self._detect_click.left_bent_frames,
            right_bent_frames=self._detect_click.right_bent_frames,
            click_confirm_frames=self._detect_click._settings.click_confirm_frames,
            left_in_neutral=self._detect_click.left_in_neutral,
            right_in_neutral=self._detect_click.right_in_neutral,
            secondary_hand=secondary_hand,
            macro_triggered=macro_key,
            macro_description=macro_desc,
            is_tracking_paused=False,
        )

    def shutdown(self) -> None:
        """Safety release and resource cleanup."""
        self._detect_click.release_all()
        self._tracker.close()
