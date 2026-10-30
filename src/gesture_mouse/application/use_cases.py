"""
Application Use Cases.
Encapsulates business operations:
- MoveCursorUseCase: Coordinate mapping, smoothing, and anti-slip pre-click anchor lock.
- DetectClickUseCase: Dual-trigger clicks (Physical Finger Flexion + Micro-Pinch), drag, and debounce.
- ScrollGestureUseCase: Two-finger parallel vertical scroll.
"""

from __future__ import annotations

from collections import deque
from typing import Tuple, Optional
from gesture_mouse.domain.models import Hand, GestureType, HandLandmarkId
from gesture_mouse.domain.value_objects import (
    ScreenCoordinate,
    ScreenSize,
    InteractionZone,
    MouseButton,
    Distance,
)
from gesture_mouse.domain.interfaces import ISmoother, IMouseController
from gesture_mouse.infrastructure.config.settings import GestureSettings


class MoveCursorUseCase:
    """Calculates screen coordinate mapping and smooths cursor movements with anti-slip anchor lock."""

    def __init__(
        self,
        mouse_controller: IMouseController,
        smoother: ISmoother,
        zone: InteractionZone,
        lookback_seconds: float = 0.12,
    ):
        self._mouse = mouse_controller
        self._smoother = smoother
        self._zone = zone
        self._lookback_seconds = lookback_seconds
        self._screen_size: ScreenSize = self._mouse.get_screen_size()
        self._last_cursor_pos: Optional[ScreenCoordinate] = None
        self._history: deque[Tuple[float, ScreenCoordinate]] = deque(maxlen=45)
        self._active_anchor: Optional[ScreenCoordinate] = None

    def execute(
        self,
        hand: Hand,
        timestamp: float,
        lock_position: bool = False,
        allow_drag_motion: bool = False,
    ) -> ScreenCoordinate:
        """
        Map hand position to smoothed screen coordinates and command cursor.
        - If lock_position is True and not dragging: locks/snaps cursor to the pre-motion anchor
          (cancels downward hand dip or wobble during click).
        - If allow_drag_motion is True: allows moving cursor while dragging using smooth joint tracking.
        """
        if lock_position and not allow_drag_motion:
            if self._active_anchor is None:
                self._active_anchor = self._find_pre_click_anchor(timestamp)
                self._mouse.move_to(self._active_anchor)
            return self._active_anchor

        # When not locked, clear active anchor
        self._active_anchor = None

        # Tracking point: during drag, track index_pip for smooth movement without tip curl
        tracking_point = hand.index_pip if allow_drag_motion else hand.index_tip

        raw_screen_coord = self._zone.map_to_screen(tracking_point, self._screen_size)

        smooth_x, smooth_y = self._smoother.filter(
            float(raw_screen_coord.x),
            float(raw_screen_coord.y),
            timestamp
        )

        target_coord = ScreenCoordinate(x=int(round(smooth_x)), y=int(round(smooth_y)))
        self._mouse.move_to(target_coord)
        self._last_cursor_pos = target_coord

        # Record position history for pre-click anchor lookback
        self._history.append((timestamp, target_coord))
        return target_coord

    def _find_pre_click_anchor(self, current_time: float) -> ScreenCoordinate:
        """Find the cursor position from lookback_seconds ago in the rolling history."""
        if not self._history:
            return self._last_cursor_pos or ScreenCoordinate(0, 0)

        target_time = current_time - self._lookback_seconds
        best_coord = self._history[0][1]
        best_diff = abs(self._history[0][0] - target_time)

        for t, coord in self._history:
            diff = abs(t - target_time)
            if diff < best_diff:
                best_diff = diff
                best_coord = coord

        return best_coord

    def reset_smoother(self) -> None:
        self._smoother.reset()
        self._last_cursor_pos = None
        self._active_anchor = None
        self._history.clear()


class DetectClickUseCase:
    """
    Evaluates dual-trigger clicking with a temporal hysteresis state machine:
    - Primary: Physical finger flexion (Option A: Air Mouse).
    - Alternative: Micro-pinch (Apple Vision Pro style).
    - Drag & Drop: Holding left click past threshold.

    Sprint A improvements:
    - A1: click_confirm_frames consecutive frames of flexion required before confirming.
    - A2: Right-click guard: index must be fully extended (ratio > right_click_index_min_ratio).
    - A3: Neutral zone: N frames of extension required after a click before the next.
    """

    def __init__(
        self,
        mouse_controller: IMouseController,
        settings: GestureSettings,
    ):
        self._mouse = mouse_controller
        self._settings = settings

        # --- A1: Hysteresis frame counters ---
        self._left_bent_frames = 0        # consecutive frames index is bent
        self._left_ext_frames = 0         # consecutive frames index is extended (post-click neutral)
        self._right_bent_frames = 0       # consecutive frames middle is bent
        self._right_ext_frames = 0        # consecutive frames middle is extended (post-click neutral)

        # State tracking for Left Click / Drag
        self._left_active = False
        self._left_start_time = 0.0
        self._is_dragging = False
        self._last_left_click_time = 0.0
        self._left_in_neutral = False     # A3: waiting for neutral zone post-click

        # State tracking for Right Click
        self._right_active = False
        self._last_right_click_time = 0.0
        self._right_in_neutral = False    # A3: waiting for neutral zone post-click

    @property
    def is_dragging(self) -> bool:
        return self._is_dragging

    @property
    def left_bent_frames(self) -> int:
        return self._left_bent_frames

    @property
    def right_bent_frames(self) -> int:
        return self._right_bent_frames

    @property
    def left_in_neutral(self) -> bool:
        return self._left_in_neutral

    @property
    def right_in_neutral(self) -> bool:
        return self._right_in_neutral

    def execute(self, hand: Hand, timestamp: float) -> Tuple[GestureType, float, float]:
        """
        Analyze finger flexion and optional micro-pinch to trigger mouse clicks/drags.
        Returns (current_gesture, index_ratio, middle_ratio).

        Hysteresis logic (A1):
          - A gesture is only *confirmed* after click_confirm_frames consecutive bent frames.
          - After a click fires, the finger must return to extended for neutral_frames_after_click
            consecutive frames (A3) before the next click can be considered.
        Right-click guard (A2):
          - Middle bent alone is not enough; index must also be clearly extended (ratio > right_click_index_min_ratio).
        """
        r_index = hand.finger_extension_ratio(
            HandLandmarkId.INDEX_FINGER_TIP,
            HandLandmarkId.INDEX_FINGER_PIP,
            HandLandmarkId.INDEX_FINGER_MCP,
        )
        r_middle = hand.finger_extension_ratio(
            HandLandmarkId.MIDDLE_FINGER_TIP,
            HandLandmarkId.MIDDLE_FINGER_PIP,
            HandLandmarkId.MIDDLE_FINGER_MCP,
        )

        # 1. Raw single-frame flexion detections (Option A)
        index_bent = hand.is_index_bent(self._settings.finger_bent_ratio)
        index_ext = hand.is_index_extended(self._settings.finger_extended_ratio)
        middle_bent = hand.is_middle_bent(self._settings.finger_bent_ratio)
        middle_ext = hand.is_middle_extended(self._settings.finger_extended_ratio)

        # A1: Update consecutive bent/extended frame counters
        # Left (index)
        if index_bent:
            self._left_bent_frames += 1
            self._left_ext_frames = 0
        elif index_ext:
            self._left_ext_frames += 1
            self._left_bent_frames = 0
        else:
            # Ambiguous zone — reset both to prevent stale accumulation
            self._left_bent_frames = 0
            self._left_ext_frames = 0

        # Right (middle)
        if middle_bent:
            self._right_bent_frames += 1
            self._right_ext_frames = 0
        elif middle_ext:
            self._right_ext_frames += 1
            self._right_bent_frames = 0
        else:
            self._right_bent_frames = 0
            self._right_ext_frames = 0

        # A1: Confirmed signals require N consecutive frames
        left_confirmed = self._left_bent_frames >= self._settings.click_confirm_frames
        right_confirmed = self._right_bent_frames >= self._settings.click_confirm_frames

        # A3: Neutral zone tracking — clear the "in neutral" flag once enough extended frames seen
        if self._left_in_neutral and self._left_ext_frames >= self._settings.neutral_frames_after_click:
            self._left_in_neutral = False
        if self._right_in_neutral and self._right_ext_frames >= self._settings.neutral_frames_after_click:
            self._right_in_neutral = False

        # 2. Micro-pinch detections (Optional alternative — bypass hysteresis, instant response)
        is_left_pinched = False
        is_right_pinched = False
        if self._settings.enable_pinch_alternative:
            d_lp = Distance.euclidean_2d(hand.thumb_tip, hand.index_tip)
            d_rp = Distance.euclidean_2d(hand.thumb_tip, hand.middle_tip)
            is_left_pinched = d_lp < self._settings.click_pinch_threshold
            is_right_pinched = d_rp < self._settings.right_click_pinch_threshold

        current_gesture = GestureType.MOVE

        # --- Right Click Evaluation ---
        # A2 guard: index ratio must exceed right_click_index_min_ratio (fully extended).
        # This prevents false right-clicks when bending index slightly drags middle down.
        index_fully_extended = r_index >= self._settings.right_click_index_min_ratio
        is_right_triggered = (
            (right_confirmed and index_fully_extended and not self._right_in_neutral)
            or (is_right_pinched and not is_left_pinched)
        )

        if is_right_triggered:
            if not self._right_active:
                if (timestamp - self._last_right_click_time) >= self._settings.click_debounce_seconds:
                    self._mouse.click(MouseButton.RIGHT)
                    self._last_right_click_time = timestamp
                    current_gesture = GestureType.RIGHT_CLICK
                    self._right_in_neutral = True   # A3: require neutral zone before next right-click
                    self._right_ext_frames = 0
            self._right_active = True
            return (current_gesture, r_index, r_middle)
        else:
            self._right_active = False

        # --- Left Click & Drag Evaluation ---
        # A3 guard: skip if still in post-click neutral zone (flexion trigger only; pinch bypasses)
        is_left_triggered = (
            (left_confirmed and not self._left_in_neutral)
            or (is_left_pinched and not is_right_pinched)
        )

        if is_left_triggered:
            if not self._left_active:
                self._left_active = True
                self._left_start_time = timestamp

            duration = timestamp - self._left_start_time

            # Hold duration check for Drag mode
            if duration >= self._settings.drag_hold_seconds:
                if not self._is_dragging:
                    self._mouse.press(MouseButton.LEFT)
                    self._is_dragging = True
                current_gesture = GestureType.DRAGGING
            else:
                current_gesture = GestureType.LEFT_CLICK

        else:
            # Trigger released
            if self._left_active:
                duration = timestamp - self._left_start_time

                if self._is_dragging:
                    self._mouse.release(MouseButton.LEFT)
                    self._is_dragging = False
                elif duration < self._settings.drag_hold_seconds:
                    # Quick tap -> trigger left click on release (only for flexion path, not drag)
                    if (timestamp - self._last_left_click_time) >= self._settings.click_debounce_seconds:
                        self._mouse.click(MouseButton.LEFT)
                        self._last_left_click_time = timestamp
                        current_gesture = GestureType.LEFT_CLICK
                        self._left_in_neutral = True   # A3: require neutral zone before next left-click
                        self._left_ext_frames = 0

                self._left_active = False

        return (current_gesture, r_index, r_middle)

    def abort_all(self) -> None:
        """Unconditionally abort all states without triggering clicks."""
        if self._is_dragging:
            self._mouse.release(MouseButton.LEFT)
            self._is_dragging = False
        self._left_active = False
        self._right_active = False
        self._left_start_time = 0.0
        # Reset hysteresis counters
        self._left_bent_frames = 0
        self._left_ext_frames = 0
        self._right_bent_frames = 0
        self._right_ext_frames = 0
        self._left_in_neutral = False
        self._right_in_neutral = False

    def release_all(self) -> None:
        self.abort_all()


class ScrollGestureUseCase:
    """
    Detects two-finger vertical scroll gesture (Index & Middle fingers extended together).
    """

    def __init__(
        self,
        mouse_controller: IMouseController,
        settings: GestureSettings,
    ):
        self._mouse = mouse_controller
        self._settings = settings
        self._last_y: Optional[float] = None
        self._last_scroll_time = 0.0

    def is_scroll_pose(self, hand: Hand) -> bool:
        """
        Criteria: Index and Middle are extended, Ring and Pinky are folded,
        and Index and Middle tips are relatively close to each other horizontally.
        """
        index_ext = hand.is_index_extended(self._settings.finger_extended_ratio)
        middle_ext = hand.is_middle_extended(self._settings.finger_extended_ratio)
        ring_ext = hand.is_ring_extended()
        pinky_ext = hand.is_pinky_extended()

        if index_ext and middle_ext and (not ring_ext) and (not pinky_ext):
            dx = abs(hand.index_tip.x - hand.middle_tip.x)
            return dx < 0.08
        return False

    def execute(self, hand: Hand, timestamp: float) -> Tuple[bool, int]:
        """Returns (is_scrolling, scroll_amount)."""
        if not self.is_scroll_pose(hand):
            self._last_y = None
            return (False, 0)

        current_y = (hand.index_tip.y + hand.middle_tip.y) / 2.0

        if self._last_y is None:
            self._last_y = current_y
            return (True, 0)

        dy = current_y - self._last_y
        scroll_amount = 0

        # Upwards hand motion (dy < 0) -> scroll positive (up)
        if abs(dy) >= self._settings.scroll_threshold_y:
            if (timestamp - self._last_scroll_time) >= self._settings.scroll_cooldown_seconds:
                direction = -1 if dy > 0 else 1
                scroll_amount = direction * self._settings.scroll_speed
                self._mouse.scroll(0, scroll_amount)
                self._last_scroll_time = timestamp
                self._last_y = current_y

        return (True, scroll_amount)

    def reset(self) -> None:
        self._last_y = None


class CalibrationUseCase:
    """
    Guides personalized user calibration.
    Samples hand posture in neutral (open/relaxed) pose over a calibration duration (e.g. 3.0s).
    Calculates average extension ratios for index and middle fingers,
    then computes custom thresholds relative to the user's natural finger dimensions.
    """

    def __init__(self, duration_seconds: float = 3.0):
        self._duration_seconds = duration_seconds
        self._start_time: Optional[float] = None
        self._samples_index: list[float] = []
        self._samples_middle: list[float] = []
        self._is_active: bool = False
        self._completed: bool = False
        self._last_result: Optional[dict[str, float]] = None

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def is_completed(self) -> bool:
        return self._completed

    @property
    def last_result(self) -> Optional[dict[str, float]]:
        return self._last_result

    def start(self, current_time: float) -> None:
        """Start a new calibration session."""
        self._start_time = current_time
        self._samples_index.clear()
        self._samples_middle.clear()
        self._is_active = True
        self._completed = False
        self._last_result = None

    def sample(self, hand: Hand, current_time: float) -> Tuple[bool, float, Optional[dict[str, float]]]:
        """
        Record a sample during calibration.
        Returns:
            (is_done, remaining_seconds, calibrated_thresholds_or_None)
        """
        if not self._is_active or self._start_time is None:
            return (True, 0.0, self._last_result)

        # Record ratios
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
        self._samples_index.append(r_idx)
        self._samples_middle.append(r_mid)

        elapsed = current_time - self._start_time
        remaining = max(0.0, self._duration_seconds - elapsed)

        if elapsed >= self._duration_seconds:
            # Complete calibration
            self._is_active = False
            self._completed = True

            mean_idx = float(sum(self._samples_index) / max(1, len(self._samples_index)))
            mean_mid = float(sum(self._samples_middle) / max(1, len(self._samples_middle)))
            baseline = (mean_idx + mean_mid) / 2.0

            # Proportional personalized thresholds
            calibrated = {
                "baseline_ratio": round(baseline, 3),
                "finger_bent_ratio": round(max(1.10, baseline * 0.70), 2),
                "finger_extended_ratio": round(max(1.30, baseline * 0.88), 2),
                "right_click_index_min_ratio": round(max(1.40, mean_idx * 0.90), 2),
            }
            self._last_result = calibrated
            return (True, 0.0, calibrated)

        return (False, remaining, None)

    def cancel(self) -> None:
        """Cancel ongoing calibration without saving."""
        self._is_active = False
        self._start_time = None
        self._samples_index.clear()
        self._samples_middle.clear()


class DwellClickUseCase:
    """
    Accessibility Dwell Click: triggers a left click when cursor hovers motionless over a target.
    """

    def __init__(
        self,
        mouse_controller: IMouseController,
        dwell_duration: float = 1.2,
        movement_threshold_px: int = 20,
    ):
        self._mouse = mouse_controller
        self._dwell_duration = dwell_duration
        self._threshold_px = movement_threshold_px

        self._anchor_pos: Optional[ScreenCoordinate] = None
        self._dwell_start: float = 0.0
        self._has_fired: bool = False

    def reset(self) -> None:
        self._anchor_pos = None
        self._dwell_start = 0.0
        self._has_fired = False

    def execute(
        self,
        cursor_pos: Optional[ScreenCoordinate],
        timestamp: float,
        is_gesture_clicking: bool = False,
    ) -> Tuple[bool, float]:
        """
        Evaluate dwell progress.
        Returns:
            (triggered: bool, progress: float from 0.0 to 1.0)
        """
        if cursor_pos is None or is_gesture_clicking:
            self.reset()
            return (False, 0.0)

        if self._anchor_pos is None:
            self._anchor_pos = cursor_pos
            self._dwell_start = timestamp
            self._has_fired = False
            return (False, 0.0)

        # Distance from initial hover anchor
        import math
        dx = cursor_pos.x - self._anchor_pos.x
        dy = cursor_pos.y - self._anchor_pos.y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist > self._threshold_px:
            # Cursor drifted away -> reset anchor to current spot
            self._anchor_pos = cursor_pos
            self._dwell_start = timestamp
            self._has_fired = False
            return (False, 0.0)

        if self._has_fired:
            # Already clicked at this anchor spot, waiting for movement
            return (False, 1.0)

        elapsed = timestamp - self._dwell_start
        progress = min(1.0, elapsed / max(0.01, self._dwell_duration))

        if progress >= 1.0:
            self._mouse.click(MouseButton.LEFT)
            self._has_fired = True
            return (True, 1.0)

        return (False, progress)


class LeftHandMacroUseCase:
    """
    Sprint D: Evaluates secondary (Left) hand gestures for instant shortcuts/macros.
    - Fist: Toggle audio mute/unmute
    - Open Palm: Toggle cursor tracking pause/resume
    - Peace Sign: Trigger Windows Start Key / Alt-Tab
    """

    def __init__(self, debounce_seconds: float = 1.0):
        self._debounce = debounce_seconds
        self._last_trigger_time = 0.0
        self._last_macro: Optional[str] = None

    def execute(self, hand: Optional[Hand], timestamp: float) -> Tuple[Optional[str], str]:
        """
        Evaluate macro gesture on secondary hand.
        Returns:
            (macro_key, description) e.g. ("TOGGLE_MUTE", "Silenciar/Activar Audio")
        """
        if hand is None:
            return (None, "")

        if (timestamp - self._last_trigger_time) < self._debounce:
            return (None, "")

        if hand.is_fist():
            self._last_trigger_time = timestamp
            self._last_macro = "TOGGLE_MUTE"
            return ("TOGGLE_MUTE", "Audio: Mute / Activar [Puno Izq]")

        if hand.is_open_palm():
            self._last_trigger_time = timestamp
            self._last_macro = "TOGGLE_PAUSE"
            return ("TOGGLE_PAUSE", "Tracking: Pausa / Reanudar [Palma Izq]")

        if hand.is_peace_sign():
            self._last_trigger_time = timestamp
            self._last_macro = "WIN_MENU"
            return ("WIN_MENU", "Menu Inicio Windows [Paz Izq]")

        return (None, "")
