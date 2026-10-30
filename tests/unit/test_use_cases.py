"""
Unit tests for Application Use Cases (Option A: Physical Finger Flexion Air Mouse).
"""

from typing import List, Tuple

from gesture_mouse.domain.models import Hand, NormalizedPoint, HandLandmarkId, Handedness, GestureType
from gesture_mouse.domain.value_objects import (
    ScreenCoordinate,
    ScreenSize,
    InteractionZone,
    MouseButton,
)
from gesture_mouse.domain.interfaces import IMouseController, ISmoother, IHandTracker
from gesture_mouse.infrastructure.config.settings import GestureSettings
from gesture_mouse.application.use_cases import (
    MoveCursorUseCase,
    DetectClickUseCase,
    ScrollGestureUseCase,
    CalibrationUseCase,
    DwellClickUseCase,
    LeftHandMacroUseCase,
)


class MockMouseController(IMouseController):
    def __init__(self, width: int = 1920, height: int = 1080):
        self.screen_size = ScreenSize(width, height)
        self.cursor_pos = ScreenCoordinate(0, 0)
        self.clicks: List[MouseButton] = []
        self.pressed: List[MouseButton] = []
        self.released: List[MouseButton] = []
        self.scrolls: List[Tuple[int, int]] = []

    def move_to(self, coordinate: ScreenCoordinate) -> None:
        self.cursor_pos = coordinate

    def get_position(self) -> ScreenCoordinate:
        return self.cursor_pos

    def click(self, button: MouseButton) -> None:
        self.clicks.append(button)

    def press(self, button: MouseButton) -> None:
        self.pressed.append(button)

    def release(self, button: MouseButton) -> None:
        self.released.append(button)

    def scroll(self, dx: int, dy: int) -> None:
        self.scrolls.append((dx, dy))

    def get_screen_size(self) -> ScreenSize:
        return self.screen_size


class PassThroughSmoother(ISmoother):
    def filter(self, x: float, y: float, timestamp: float) -> Tuple[float, float]:
        return (x, y)

    def reset(self) -> None:
        pass


def make_hand(
    index_bent: bool = False,
    middle_bent: bool = False,
    index_tip_xy: Tuple[float, float] = (0.5, 0.3),
) -> Hand:
    """Helper to build a Hand model with controlled finger flexion for Option A."""
    # Index finger
    base_x = index_tip_xy[0]
    base_y = index_tip_xy[1]

    if index_bent:
        idx_pip = NormalizedPoint(base_x, base_y)
        idx_mcp = NormalizedPoint(base_x, base_y + 0.15)
        idx_tip = NormalizedPoint(base_x, base_y + 0.05)  # Tip curled near MCP
    else:
        idx_tip = NormalizedPoint(base_x, base_y)
        idx_pip = NormalizedPoint(base_x, base_y + 0.15)
        idx_mcp = NormalizedPoint(base_x, base_y + 0.30)  # Ratio = 0.30 / 0.15 = 2.0 (extended)

    # Middle finger
    mid_x = base_x + 0.05
    if middle_bent:
        mid_pip = NormalizedPoint(mid_x, base_y)
        mid_mcp = NormalizedPoint(mid_x, base_y + 0.15)
        mid_tip = NormalizedPoint(mid_x, base_y + 0.05)
    else:
        mid_tip = NormalizedPoint(mid_x, base_y)
        mid_pip = NormalizedPoint(mid_x, base_y + 0.15)
        mid_mcp = NormalizedPoint(mid_x, base_y + 0.30)

    lms = {
        HandLandmarkId.WRIST: NormalizedPoint(0.5, 0.85),
        HandLandmarkId.THUMB_TIP: NormalizedPoint(0.35, 0.55),
        HandLandmarkId.INDEX_FINGER_MCP: idx_mcp,
        HandLandmarkId.INDEX_FINGER_PIP: idx_pip,
        HandLandmarkId.INDEX_FINGER_TIP: idx_tip,
        HandLandmarkId.MIDDLE_FINGER_MCP: mid_mcp,
        HandLandmarkId.MIDDLE_FINGER_PIP: mid_pip,
        HandLandmarkId.MIDDLE_FINGER_TIP: mid_tip,
        # Folded ring and pinky
        HandLandmarkId.RING_FINGER_MCP: NormalizedPoint(0.65, 0.60),
        HandLandmarkId.RING_FINGER_PIP: NormalizedPoint(0.65, 0.55),
        HandLandmarkId.RING_FINGER_TIP: NormalizedPoint(0.65, 0.70),
        HandLandmarkId.PINKY_MCP: NormalizedPoint(0.75, 0.60),
        HandLandmarkId.PINKY_PIP: NormalizedPoint(0.75, 0.55),
        HandLandmarkId.PINKY_TIP: NormalizedPoint(0.75, 0.70),
    }
    return Hand(landmarks=lms, handedness=Handedness.RIGHT)


def test_move_cursor_use_case():
    mouse = MockMouseController(width=1000, height=1000)
    smoother = PassThroughSmoother()
    zone = InteractionZone(margin_x=0.0, margin_y=0.0)

    use_case = MoveCursorUseCase(mouse, smoother, zone)
    hand = make_hand(index_tip_xy=(0.5, 0.5))

    target = use_case.execute(hand, timestamp=1.0)
    assert abs(target.x - 500) <= 1
    assert abs(target.y - 500) <= 1
    assert mouse.cursor_pos == target


def test_detect_click_use_case_tap():
    """Option A: Bending index finger for N consecutive frames then releasing triggers Left Click."""
    mouse = MockMouseController()
    settings = GestureSettings(
        click_confirm_frames=4,
        neutral_frames_after_click=3,
        click_debounce_seconds=0.2,
        drag_hold_seconds=0.4,
    )
    use_case = DetectClickUseCase(mouse, settings)

    hand_bent = make_hand(index_bent=True, middle_bent=False)
    hand_extended = make_hand(index_bent=False, middle_bent=False)

    # Frames 1–3: bent but NOT yet confirmed (< 4 frames)
    for i in range(3):
        gesture, _, _ = use_case.execute(hand_bent, timestamp=1.0 + i * 0.033)
        assert gesture == GestureType.MOVE, f"Should not confirm before frame 4 (frame {i+1})"
    assert len(mouse.clicks) == 0

    # Frame 4: confirmed! Left click state active
    gesture, _, _ = use_case.execute(hand_bent, timestamp=1.1)
    assert gesture == GestureType.LEFT_CLICK
    assert len(mouse.clicks) == 0  # Click fires on RELEASE (tap detection)

    # Release finger -> click fires
    gesture_rel, _, _ = use_case.execute(hand_extended, timestamp=1.15)
    assert len(mouse.clicks) == 1
    assert mouse.clicks[0] == MouseButton.LEFT


def test_detect_click_use_case_drag():
    """Option A: Holding index finger bent past threshold engages Drag Mode, releasing drops."""
    mouse = MockMouseController()
    settings = GestureSettings(
        click_confirm_frames=2,   # lower for test speed
        drag_hold_seconds=0.3,
    )
    use_case = DetectClickUseCase(mouse, settings)

    hand_bent = make_hand(index_bent=True, middle_bent=False)

    # Frame 1: bent, not yet confirmed
    use_case.execute(hand_bent, timestamp=1.0)
    assert len(mouse.pressed) == 0

    # Frame 2: confirmed (2 frames). Hold start captured.
    use_case.execute(hand_bent, timestamp=1.033)
    assert len(mouse.pressed) == 0

    # Continue hold past drag threshold at t=1.4 (> 0.3s) -> enters DRAGGING
    gesture, _, _ = use_case.execute(hand_bent, timestamp=1.4)
    assert gesture == GestureType.DRAGGING
    assert len(mouse.pressed) == 1
    assert mouse.pressed[0] == MouseButton.LEFT

    # Release finger at t=1.6 -> drops/releases drag
    hand_extended = make_hand(index_bent=False, middle_bent=False)
    use_case.execute(hand_extended, timestamp=1.6)
    assert len(mouse.released) == 1
    assert mouse.released[0] == MouseButton.LEFT


def test_detect_right_click():
    """Option A: Bending middle finger for N frames while index is FULLY extended triggers Right Click."""
    mouse = MockMouseController()
    settings = GestureSettings(
        click_confirm_frames=3,
        right_click_index_min_ratio=1.80,
        click_debounce_seconds=0.2,
    )
    use_case = DetectClickUseCase(mouse, settings)

    # Extended index: ratio = 2.0 (> 1.80 guard) — middle bent
    hand_right = make_hand(index_bent=False, middle_bent=True)

    # Frames 1-2: not yet confirmed
    use_case.execute(hand_right, timestamp=1.0)
    use_case.execute(hand_right, timestamp=1.033)
    assert len(mouse.clicks) == 0

    # Frame 3: confirmed — right click fires immediately (no release needed)
    gesture, _, _ = use_case.execute(hand_right, timestamp=1.066)
    assert gesture == GestureType.RIGHT_CLICK
    assert len(mouse.clicks) == 1
    assert mouse.clicks[0] == MouseButton.RIGHT


def test_right_click_blocked_when_index_not_fully_extended():
    """A2: Right-click must NOT fire when index ratio is between bent and fully-extended thresholds."""
    mouse = MockMouseController()
    settings = GestureSettings(
        click_confirm_frames=1,    # immediate for this test
        right_click_index_min_ratio=1.80,
        enable_pinch_alternative=False,
    )
    use_case = DetectClickUseCase(mouse, settings)

    # Build a hand where index ratio is ~1.60 (just at extended threshold but below 1.80 fully-extended guard).
    # ratio = d(TIP, MCP) / d(PIP, MCP)
    # We want ratio ≈ 1.65: d_tip_mcp=0.165, d_pip_mcp=0.10
    # tip=(0.5, 0.30), pip=(0.5, 0.40), mcp=(0.5, 0.465)  → d_tip_mcp=0.165, d_pip_mcp=0.065... adjust
    # Easier: mcp=(0.5, 0.465), pip=(0.5, 0.365), tip=(0.5, 0.30)
    # d_tip_mcp = 0.465-0.30 = 0.165, d_pip_mcp = 0.465-0.365 = 0.10 → ratio = 1.65
    hand = make_hand(index_bent=False, middle_bent=True)
    hand.landmarks[HandLandmarkId.INDEX_FINGER_MCP] = NormalizedPoint(0.5, 0.465)
    hand.landmarks[HandLandmarkId.INDEX_FINGER_PIP] = NormalizedPoint(0.5, 0.365)
    hand.landmarks[HandLandmarkId.INDEX_FINGER_TIP] = NormalizedPoint(0.5, 0.30)

    gesture, r_idx, _ = use_case.execute(hand, timestamp=1.0)
    assert 1.60 <= r_idx < 1.80, f"Expected ratio between 1.60 and 1.80, got {r_idx:.3f}"
    assert gesture != GestureType.RIGHT_CLICK, "Right-click must be blocked when index is not fully extended"
    assert len(mouse.clicks) == 0


def test_neutral_zone_prevents_double_click():
    """A3: After a click fires, the finger must return to neutral (N extended frames) before next click."""
    mouse = MockMouseController()
    settings = GestureSettings(
        click_confirm_frames=2,
        neutral_frames_after_click=3,
        click_debounce_seconds=0.01,   # minimal debounce to isolate A3 behavior
        drag_hold_seconds=0.5,
    )
    use_case = DetectClickUseCase(mouse, settings)

    hand_bent = make_hand(index_bent=True, middle_bent=False)
    hand_ext = make_hand(index_bent=False, middle_bent=False)

    # Confirm first click (2 bent frames)
    use_case.execute(hand_bent, timestamp=1.00)
    use_case.execute(hand_bent, timestamp=1.033)

    # Release -> click fires, enters neutral zone
    use_case.execute(hand_ext, timestamp=1.07)
    assert len(mouse.clicks) == 1

    # Immediately try to click again (only 1 extended frame elapsed — neutral not cleared)
    use_case.execute(hand_bent, timestamp=1.08)
    use_case.execute(hand_bent, timestamp=1.10)  # 2 bent frames again
    use_case.execute(hand_ext, timestamp=1.12)
    # Still only 1 click because we haven't done 3 extended frames yet
    assert len(mouse.clicks) == 1, "Second click should be blocked by neutral zone"

    # Now do 3 extended frames to clear neutral zone
    use_case.execute(hand_ext, timestamp=1.14)
    use_case.execute(hand_ext, timestamp=1.17)  # 3rd extended frame -> neutral cleared

    # Now click should succeed
    use_case.execute(hand_bent, timestamp=1.20)
    use_case.execute(hand_bent, timestamp=1.23)  # 2 bent frames confirmed
    use_case.execute(hand_ext, timestamp=1.27)
    assert len(mouse.clicks) == 2, "Second click should succeed after neutral zone cleared"


def test_scroll_gesture_use_case():
    mouse = MockMouseController()
    settings = GestureSettings(
        scroll_threshold_y=0.01,
        scroll_speed=3,
        scroll_cooldown_seconds=0.01,
    )
    use_case = ScrollGestureUseCase(mouse, settings)

    # Hand with index and middle extended together
    hand_scroll = make_hand(index_tip_xy=(0.50, 0.40))

    # First frame initializes reference
    is_scroll, amt = use_case.execute(hand_scroll, timestamp=1.0)
    assert is_scroll is True
    assert amt == 0

    # Hand moves UP (y decreases from 0.40 to 0.35)
    hand_scroll_up = make_hand(index_tip_xy=(0.50, 0.35))
    is_scroll2, amt2 = use_case.execute(hand_scroll_up, timestamp=1.05)
    assert is_scroll2 is True
    assert amt2 > 0  # Scrolled UP
    assert len(mouse.scrolls) == 1


class MockHandTracker(IHandTracker):
    def __init__(self, hand_to_return=None, hands_to_return=None):
        self.hand = hand_to_return
        self.hands = hands_to_return

    def track(self, frame, timestamp_ms: int):
        return self.hand

    def track_all(self, frame, timestamp_ms: int):
        if self.hands is not None:
            return self.hands
        return [self.hand] if self.hand else []

    def close(self):
        pass


def test_gesture_service_edge_safety_lock():
    """When a hand touches the camera edge, actions are frozen and out of bounds is reported."""
    from gesture_mouse.application.services.gesture_service import GestureService

    # Hand at the extreme edge: index_tip.x = 0.01 (< safety_edge_margin=0.04)
    edge_hand = make_hand()
    edge_hand.landmarks[HandLandmarkId.INDEX_FINGER_TIP] = NormalizedPoint(0.01, 0.5)

    tracker = MockHandTracker(edge_hand)
    mouse = MockMouseController()
    smoother = PassThroughSmoother()
    zone = InteractionZone(margin_x=0.08, margin_y=0.08)
    settings = GestureSettings()

    move_uc = MoveCursorUseCase(mouse, smoother, zone)
    click_uc = DetectClickUseCase(mouse, settings)
    scroll_uc = ScrollGestureUseCase(mouse, settings)

    service = GestureService(
        hand_tracker=tracker,
        move_cursor_uc=move_uc,
        detect_click_uc=click_uc,
        scroll_gesture_uc=scroll_uc,
        safety_edge_margin=0.04,
    )

    import numpy as np
    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    res = service.process_frame(dummy_frame, timestamp=1.0)

    assert res.is_out_of_bounds is True
    assert res.gesture == GestureType.OUT_OF_BOUNDS
    assert res.cursor_position is None
    assert len(mouse.clicks) == 0
    assert len(mouse.pressed) == 0


def test_gesture_service_reentry_stabilization():
    """When a hand enters the camera, clicks are disabled during stabilization window."""
    from gesture_mouse.application.services.gesture_service import GestureService

    # Hand with bent index finger
    bent_hand = make_hand(index_bent=True)
    tracker = MockHandTracker(bent_hand)
    mouse = MockMouseController()
    smoother = PassThroughSmoother()
    zone = InteractionZone(margin_x=0.08, margin_y=0.08)
    settings = GestureSettings(
        reentry_stabilization_seconds=0.20,
        click_confirm_frames=1,  # 1 frame for test speed (hysteresis tested separately)
    )

    move_uc = MoveCursorUseCase(mouse, smoother, zone)
    click_uc = DetectClickUseCase(mouse, settings)
    scroll_uc = ScrollGestureUseCase(mouse, settings)

    service = GestureService(
        hand_tracker=tracker,
        move_cursor_uc=move_uc,
        detect_click_uc=click_uc,
        scroll_gesture_uc=scroll_uc,
        safety_edge_margin=0.04,
        reentry_stabilization_seconds=0.20,
    )

    import numpy as np
    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # Frame 1 at t=1.00 (0 ms elapsed -> stabilizing)
    res1 = service.process_frame(dummy_frame, timestamp=1.00)
    assert res1.is_stabilizing is True
    assert res1.gesture == GestureType.STABILIZING
    assert len(mouse.clicks) == 0

    # Frame 2 at t=1.10 (100 ms elapsed < 200 ms -> still stabilizing)
    res2 = service.process_frame(dummy_frame, timestamp=1.10)
    assert res2.is_stabilizing is True
    assert len(mouse.clicks) == 0

    # Frame 3 at t=1.25 (250 ms elapsed > 200 ms -> stabilized, clicks allowed)
    res3 = service.process_frame(dummy_frame, timestamp=1.25)
    assert res3.is_stabilizing is False
    assert res3.gesture in (GestureType.LEFT_CLICK, GestureType.DRAGGING)


def test_pre_click_anchor_locking():
    """Cursor snaps to the pre-motion anchor from lookback_seconds ago during click, eliminating slip."""
    mouse = MockMouseController(width=1000, height=1000)
    smoother = PassThroughSmoother()
    zone = InteractionZone(margin_x=0.0, margin_y=0.0)
    use_case = MoveCursorUseCase(mouse, smoother, zone, lookback_seconds=0.10)

    # 1. At t=1.00, user is steadily aiming at (0.50, 0.30) -> Screen (500, 300)
    hand_aim = make_hand(index_tip_xy=(0.50, 0.30))
    pos1 = use_case.execute(hand_aim, timestamp=1.00, lock_position=False)
    assert abs(pos1.x - 500) <= 1
    assert abs(pos1.y - 300) <= 1

    # 2. At t=1.10, finger starts curling down to click, drifting to (0.50, 0.35) -> Screen (500, 350)
    hand_curl = make_hand(index_tip_xy=(0.50, 0.35))
    use_case.execute(hand_curl, timestamp=1.10, lock_position=False)

    # 3. At t=1.12, click is triggered. With lock_position=True, it snaps back to (500, 300) from t=1.00!
    hand_click = make_hand(index_tip_xy=(0.50, 0.36), index_bent=True)
    pos_locked = use_case.execute(hand_click, timestamp=1.12, lock_position=True)
    assert abs(pos_locked.y - 300) <= 1
    assert mouse.cursor_pos == pos_locked


def test_dual_trigger_pinch():
    """Micro-pinch (Vision Pro style) also triggers left/right click interchangeably."""
    mouse = MockMouseController()
    settings = GestureSettings(
        enable_pinch_alternative=True,
        click_pinch_threshold=0.05,
        right_click_pinch_threshold=0.05,
        click_debounce_seconds=0.2,
    )
    use_case = DetectClickUseCase(mouse, settings)

    # 1. Micro-pinch Left Click: Thumb and Index tips touching (dist 0.02 < 0.05)
    hand_pinch = make_hand()
    hand_pinch.landmarks[HandLandmarkId.THUMB_TIP] = NormalizedPoint(0.50, 0.30)
    hand_pinch.landmarks[HandLandmarkId.INDEX_FINGER_TIP] = NormalizedPoint(0.51, 0.31)

    gesture, _, _ = use_case.execute(hand_pinch, timestamp=1.00)
    assert gesture == GestureType.LEFT_CLICK

    # Release pinch -> left click emitted
    hand_open = make_hand()
    hand_open.landmarks[HandLandmarkId.THUMB_TIP] = NormalizedPoint(0.40, 0.50)
    use_case.execute(hand_open, timestamp=1.10)
    assert len(mouse.clicks) == 1
    assert mouse.clicks[0] == MouseButton.LEFT


def test_calibration_use_case():
    """Calibration collects hand samples over duration and returns personalized thresholds."""
    calib = CalibrationUseCase(duration_seconds=2.0)
    hand = make_hand(index_bent=False, middle_bent=False)  # baseline ratio is ~2.0

    calib.start(current_time=1.0)
    assert calib.is_active is True
    assert calib.is_completed is False

    # Sample at t=1.5 (remaining 1.5s -> not done)
    is_done, remaining, res = calib.sample(hand, current_time=1.5)
    assert is_done is False
    assert 1.4 <= remaining <= 1.6
    assert res is None

    # Sample at t=3.0 (elapsed 2.0s -> done)
    is_done, remaining, res = calib.sample(hand, current_time=3.0)
    assert is_done is True
    assert remaining == 0.0
    assert res is not None
    assert "baseline_ratio" in res
    assert "finger_bent_ratio" in res
    assert "finger_extended_ratio" in res
    assert "right_click_index_min_ratio" in res
    assert res["finger_bent_ratio"] < res["finger_extended_ratio"]
    assert calib.is_completed is True


def test_dwell_click_use_case():
    """Holding cursor still triggers an automatic left click after dwell duration."""
    mouse = MockMouseController()
    dwell_uc = DwellClickUseCase(mouse, dwell_duration=1.0, movement_threshold_px=15)

    pos = ScreenCoordinate(500, 500)

    # First frame initializes anchor
    trig1, prog1 = dwell_uc.execute(pos, timestamp=1.0)
    assert trig1 is False
    assert prog1 == 0.0
    assert len(mouse.clicks) == 0

    # Hovering still after 0.5s -> 50% progress
    trig2, prog2 = dwell_uc.execute(ScreenCoordinate(505, 503), timestamp=1.5)
    assert trig2 is False
    assert 0.45 <= prog2 <= 0.55
    assert len(mouse.clicks) == 0

    # Hovering still at 1.0s elapsed -> fires click!
    trig3, prog3 = dwell_uc.execute(ScreenCoordinate(502, 501), timestamp=2.0)
    assert trig3 is True
    assert prog3 == 1.0
    assert len(mouse.clicks) == 1
    assert mouse.clicks[0] == MouseButton.LEFT

    # Drifting away (>15px) resets dwell
    trig4, prog4 = dwell_uc.execute(ScreenCoordinate(600, 600), timestamp=2.1)
    assert trig4 is False
    assert prog4 == 0.0


def test_left_hand_macro_use_case():
    """Sprint D: Secondary hand gestures trigger immediate macro actions."""
    macro_uc = LeftHandMacroUseCase(debounce_seconds=1.0)

    # Fist hand (all curled)
    fist_lms = {
        HandLandmarkId.INDEX_FINGER_TIP: NormalizedPoint(0.4, 0.5),
        HandLandmarkId.INDEX_FINGER_PIP: NormalizedPoint(0.4, 0.3),
        HandLandmarkId.MIDDLE_FINGER_TIP: NormalizedPoint(0.5, 0.5),
        HandLandmarkId.MIDDLE_FINGER_PIP: NormalizedPoint(0.5, 0.3),
        HandLandmarkId.RING_FINGER_TIP: NormalizedPoint(0.6, 0.5),
        HandLandmarkId.RING_FINGER_PIP: NormalizedPoint(0.6, 0.3),
        HandLandmarkId.PINKY_TIP: NormalizedPoint(0.7, 0.5),
        HandLandmarkId.PINKY_PIP: NormalizedPoint(0.7, 0.3),
    }
    hand_fist = Hand(landmarks=fist_lms, handedness=Handedness.LEFT)

    # 1. Fist triggers TOGGLE_MUTE
    action1, desc1 = macro_uc.execute(hand_fist, timestamp=1.0)
    assert action1 == "TOGGLE_MUTE"
    assert "Audio" in desc1

    # 2. Debounce prevents immediate re-trigger (< 1.0s)
    action2, _ = macro_uc.execute(hand_fist, timestamp=1.5)
    assert action2 is None

    # 3. After debounce (timestamp=2.1 > 2.0), open palm triggers TOGGLE_PAUSE
    palm_lms = {
        HandLandmarkId.INDEX_FINGER_TIP: NormalizedPoint(0.4, 0.2),
        HandLandmarkId.INDEX_FINGER_PIP: NormalizedPoint(0.4, 0.4),
        HandLandmarkId.MIDDLE_FINGER_TIP: NormalizedPoint(0.5, 0.2),
        HandLandmarkId.MIDDLE_FINGER_PIP: NormalizedPoint(0.5, 0.4),
        HandLandmarkId.RING_FINGER_TIP: NormalizedPoint(0.6, 0.2),
        HandLandmarkId.RING_FINGER_PIP: NormalizedPoint(0.6, 0.4),
        HandLandmarkId.PINKY_TIP: NormalizedPoint(0.7, 0.2),
        HandLandmarkId.PINKY_PIP: NormalizedPoint(0.7, 0.4),
    }
    hand_palm = Hand(landmarks=palm_lms, handedness=Handedness.LEFT)
    action3, desc3 = macro_uc.execute(hand_palm, timestamp=2.1)
    assert action3 == "TOGGLE_PAUSE"
    assert "Tracking" in desc3


def test_gesture_service_dual_hand_macro():
    """GestureService coordinates dual hands: Right for cursor, Left for macros."""
    from gesture_mouse.application.services.gesture_service import GestureService
    import numpy as np

    # Primary cursor hand (Right)
    right_hand = make_hand(index_tip_xy=(0.5, 0.4))
    right_hand.handedness = Handedness.RIGHT

    # Secondary macro hand (Left) making open palm (pause tracking)
    palm_lms = {
        HandLandmarkId.INDEX_FINGER_TIP: NormalizedPoint(0.2, 0.2),
        HandLandmarkId.INDEX_FINGER_PIP: NormalizedPoint(0.2, 0.4),
        HandLandmarkId.MIDDLE_FINGER_TIP: NormalizedPoint(0.3, 0.2),
        HandLandmarkId.MIDDLE_FINGER_PIP: NormalizedPoint(0.3, 0.4),
        HandLandmarkId.RING_FINGER_TIP: NormalizedPoint(0.4, 0.2),
        HandLandmarkId.RING_FINGER_PIP: NormalizedPoint(0.4, 0.4),
        HandLandmarkId.PINKY_TIP: NormalizedPoint(0.5, 0.2),
        HandLandmarkId.PINKY_PIP: NormalizedPoint(0.5, 0.4),
    }
    left_hand = Hand(landmarks=palm_lms, handedness=Handedness.LEFT)

    tracker = MockHandTracker(hands_to_return=[right_hand, left_hand])
    mouse = MockMouseController()
    smoother = PassThroughSmoother()
    zone = InteractionZone(margin_x=0.08, margin_y=0.08)
    settings = GestureSettings()

    move_uc = MoveCursorUseCase(mouse, smoother, zone)
    click_uc = DetectClickUseCase(mouse, settings)
    scroll_uc = ScrollGestureUseCase(mouse, settings)
    macro_uc = LeftHandMacroUseCase(debounce_seconds=0.5)

    service = GestureService(
        hand_tracker=tracker,
        move_cursor_uc=move_uc,
        detect_click_uc=click_uc,
        scroll_gesture_uc=scroll_uc,
        macro_uc=macro_uc,
    )

    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    res = service.process_frame(dummy_frame, timestamp=1.0)

    assert res.secondary_hand is not None
    assert res.secondary_hand.handedness == Handedness.LEFT
    assert res.macro_triggered == "TOGGLE_PAUSE"
    assert res.is_tracking_paused is True
    assert res.cursor_position is None
