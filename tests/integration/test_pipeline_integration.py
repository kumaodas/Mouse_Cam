"""
Integration test for full GestureService pipeline with MediaPipe HandTracker.
"""

import numpy as np
from gesture_mouse.infrastructure.config.settings import AppSettings
from gesture_mouse.infrastructure.vision.smoother import OneEuroSmoother
from gesture_mouse.infrastructure.vision.hand_tracker import MediaPipeHandTracker
from gesture_mouse.application.use_cases import (
    MoveCursorUseCase,
    DetectClickUseCase,
    ScrollGestureUseCase,
)
from gesture_mouse.application.services.gesture_service import GestureService
from gesture_mouse.domain.value_objects import InteractionZone
from gesture_mouse.domain.models import GestureType
from tests.unit.test_use_cases import MockMouseController


def test_gesture_service_pipeline_empty_frame():
    settings = AppSettings()
    tracker = MediaPipeHandTracker(model_path=settings.model_path, num_hands=1)
    mouse = MockMouseController()
    smoother = OneEuroSmoother()
    zone = InteractionZone(margin_x=0.15, margin_y=0.15)

    move_uc = MoveCursorUseCase(mouse, smoother, zone)
    click_uc = DetectClickUseCase(mouse, settings.gestures)
    scroll_uc = ScrollGestureUseCase(mouse, settings.gestures)

    service = GestureService(
        hand_tracker=tracker,
        move_cursor_uc=move_uc,
        detect_click_uc=click_uc,
        scroll_gesture_uc=scroll_uc,
    )

    # Synthetic black frame (no hands present)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # Process first frame
    result = service.process_frame(frame, timestamp=1.0)
    assert result.hand is None
    assert result.gesture == GestureType.IDLE
    assert result.cursor_position is None

    # Process second frame with monotonically increasing timestamp
    result2 = service.process_frame(frame, timestamp=1.033)
    assert result2.hand is None
    assert result2.gesture == GestureType.IDLE

    service.shutdown()
