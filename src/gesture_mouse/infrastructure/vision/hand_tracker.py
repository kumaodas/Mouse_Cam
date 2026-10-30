"""
MediaPipe Hand Tracker Adapter.
Implements IHandTracker using Google MediaPipe Tasks HandLandmarker.
"""

from __future__ import annotations

import os
import urllib.request
from typing import Optional, Dict, Tuple, List, Any
import cv2
import numpy as np

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    HandLandmarker,
    HandLandmarkerOptions,
    RunningMode,
)

from gesture_mouse.domain.interfaces import IHandTracker
from gesture_mouse.domain.models import Hand, NormalizedPoint, HandLandmarkId, Handedness


# Official MediaPipe connections for drawing hand skeletons
HAND_CONNECTIONS: List[Tuple[int, int]] = [
    # Thumb
    (0, 1), (1, 2), (2, 3), (3, 4),
    # Index
    (0, 5), (5, 6), (6, 7), (7, 8),
    # Middle
    (5, 9), (9, 10), (10, 11), (11, 12),
    # Ring
    (9, 13), (13, 14), (14, 15), (15, 16),
    # Pinky
    (13, 17), (17, 18), (18, 19), (19, 20),
    # Palm base
    (0, 17)
]

MODEL_DOWNLOAD_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
)


class MediaPipeHandTracker(IHandTracker):
    """MediaPipe Tasks HandLandmarker adapter."""

    def __init__(
        self,
        model_path: str,
        min_detection_confidence: float = 0.6,
        min_presence_confidence: float = 0.6,
        min_tracking_confidence: float = 0.6,
        num_hands: int = 1,
    ):
        self.model_path = model_path
        self._ensure_model_exists()

        base_options = BaseOptions(model_asset_path=self.model_path)
        options = HandLandmarkerOptions(
            base_options=base_options,
            running_mode=RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

        self._landmarker = HandLandmarker.create_from_options(options)
        self._last_timestamp_ms = -1

    def _ensure_model_exists(self) -> None:
        """Download model asset if not present locally."""
        if not os.path.exists(self.model_path):
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            print(f"[HandTracker] Downloading MediaPipe hand landmarker model to: {self.model_path}...")
            urllib.request.urlretrieve(MODEL_DOWNLOAD_URL, self.model_path)
            print("[HandTracker] Download completed successfully.")

    def track_all(self, frame: np.ndarray, timestamp_ms: int) -> List[Hand]:
        """
        Process a BGR video frame and extract all detected hand landmarks (up to 2).
        Timestamp must be strictly monotonically increasing.
        """
        if timestamp_ms <= self._last_timestamp_ms:
            timestamp_ms = self._last_timestamp_ms + 1
        self._last_timestamp_ms = timestamp_ms

        # Convert OpenCV BGR frame to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)

        if not result.hand_landmarks or len(result.hand_landmarks) == 0:
            return []

        hands: List[Hand] = []
        for i, raw_landmarks in enumerate(result.hand_landmarks):
            handedness = Handedness.RIGHT
            score = 1.0
            if result.handedness and i < len(result.handedness) and len(result.handedness[i]) > 0:
                cat = result.handedness[i][0]
                score = cat.score
                if cat.category_name.lower() == "left":
                    handedness = Handedness.LEFT
                elif cat.category_name.lower() == "right":
                    handedness = Handedness.RIGHT

            landmarks_dict: Dict[HandLandmarkId, NormalizedPoint] = {}
            for idx, lm in enumerate(raw_landmarks):
                if idx in HandLandmarkId._value2member_map_:
                    landmark_id = HandLandmarkId(idx)
                    landmarks_dict[landmark_id] = NormalizedPoint(
                        x=float(lm.x),
                        y=float(lm.y),
                        z=float(lm.z)
                    )

            hands.append(Hand(
                landmarks=landmarks_dict,
                handedness=handedness,
                score=score
            ))

        return hands

    def track(self, frame: np.ndarray, timestamp_ms: int) -> Optional[Hand]:
        """
        Process a BGR video frame and extract primary hand landmarks.
        """
        hands = self.track_all(frame, timestamp_ms)
        return hands[0] if hands else None

    def draw_landmarks(
        self,
        frame: np.ndarray,
        hand: Hand,
        color_joints: Tuple[int, int, int] = (0, 255, 255),
        color_bones: Tuple[int, int, int] = (50, 180, 50),
        color_tips: Tuple[int, int, int] = (0, 165, 255),
    ) -> np.ndarray:
        """Render hand landmarks and connecting skeleton over OpenCV frame."""
        h, w, _ = frame.shape
        pixel_coords: Dict[int, Tuple[int, int]] = {}

        for lm_id, pt in hand.landmarks.items():
            px = int(pt.x * w)
            py = int(pt.y * h)
            pixel_coords[lm_id.value] = (px, py)

        # Draw skeleton bones
        for start_idx, end_idx in HAND_CONNECTIONS:
            if start_idx in pixel_coords and end_idx in pixel_coords:
                cv2.line(frame, pixel_coords[start_idx], pixel_coords[end_idx], color_bones, 2, cv2.LINE_AA)

        # Draw joints
        for lm_idx, (px, py) in pixel_coords.items():
            # Highlight index and thumb tip specially
            if lm_idx in (HandLandmarkId.INDEX_FINGER_TIP.value, HandLandmarkId.THUMB_TIP.value):
                cv2.circle(frame, (px, py), 7, color_tips, -1, cv2.LINE_AA)
                cv2.circle(frame, (px, py), 9, (255, 255, 255), 1, cv2.LINE_AA)
            elif lm_idx == HandLandmarkId.MIDDLE_FINGER_TIP.value:
                cv2.circle(frame, (px, py), 6, (255, 0, 255), -1, cv2.LINE_AA)
            else:
                cv2.circle(frame, (px, py), 4, color_joints, -1, cv2.LINE_AA)

        return frame

    def close(self) -> None:
        """Release underlying MediaPipe landmarker."""
        if hasattr(self, "_landmarker") and self._landmarker:
            self._landmarker.close()
