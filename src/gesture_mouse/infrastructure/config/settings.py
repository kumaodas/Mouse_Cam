"""
Configuration settings for Gesture Mouse using Pydantic.
Provides typed, validated parameters for computer vision, filtering, thresholds, and gestures.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


def get_default_model_path() -> str:
    """Find hand_landmarker.task whether running from source or PyInstaller bundle."""
    # 1. PyInstaller temp folder
    if hasattr(sys, "_MEIPASS"):
        for sub in [
            os.path.join(sys._MEIPASS, "gesture_mouse", "models", "hand_landmarker.task"),
            os.path.join(sys._MEIPASS, "models", "hand_landmarker.task"),
            os.path.join(sys._MEIPASS, "hand_landmarker.task"),
        ]:
            if os.path.exists(sub):
                return sub

    # 2. Portable folder next to executable
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        for sub in [
            os.path.join(exe_dir, "_internal", "gesture_mouse", "models", "hand_landmarker.task"),
            os.path.join(exe_dir, "_internal", "models", "hand_landmarker.task"),
            os.path.join(exe_dir, "models", "hand_landmarker.task"),
            os.path.join(exe_dir, "hand_landmarker.task"),
        ]:
            if os.path.exists(sub):
                return sub

    # 3. Development source tree
    return str(Path(__file__).resolve().parent.parent.parent / "models" / "hand_landmarker.task")


class CameraSettings(BaseModel):
    """Camera hardware and capture settings."""
    camera_index: int = Field(default=0, description="Webcam device index (0 for default)")
    width: int = Field(default=1280, description="Capture frame width")
    height: int = Field(default=720, description="Capture frame height")
    fps: int = Field(default=30, description="Target capture FPS")
    flip_horizontal: bool = Field(default=True, description="Mirror image horizontally for natural user interaction")


class InteractionZoneSettings(BaseModel):
    """Margins defining the active interaction rectangle inside the camera frame."""
    margin_left: float = Field(default=0.18, ge=0.0, lt=0.45, description="Left boundary margin")
    margin_right: float = Field(default=0.18, ge=0.0, lt=0.45, description="Right boundary margin")
    margin_top: float = Field(default=0.12, ge=0.0, lt=0.45, description="Top boundary margin")
    margin_bottom: float = Field(default=0.35, ge=0.0, lt=0.60, description="Bottom boundary margin accommodating forearm/wrist posture")
    safety_edge_margin: float = Field(default=0.02, ge=0.005, lt=0.10, description="Camera sensor border margin for safety freeze")

    # Optional legacy fallback
    margin_x: Optional[float] = None
    margin_y: Optional[float] = None


class FilterSettings(BaseModel):
    """Signal smoothing filter parameters."""
    smoother_type: str = Field(default="one_euro", description="'one_euro' or 'moving_average'")
    
    # One Euro Filter parameters
    one_euro_min_cutoff: float = Field(default=1.0, gt=0.0, description="Min cutoff frequency in Hz (lower = less jitter when still)")
    one_euro_beta: float = Field(default=0.007, ge=0.0, description="Speed coefficient (higher = less lag during rapid movement)")
    one_euro_d_cutoff: float = Field(default=1.0, gt=0.0, description="Derivative cutoff frequency in Hz")

    # Moving Average parameters
    moving_average_window: int = Field(default=5, ge=1, le=30, description="Window size for simple moving average")


class GestureSettings(BaseModel):
    """Detection thresholds and debounce parameters."""
    # Physical Air Mouse Flexion Settings (Option A)
    finger_bent_ratio: float = Field(default=1.40, gt=0.0, description="Length ratio threshold for bent/clicked finger")
    finger_extended_ratio: float = Field(default=1.60, gt=0.0, description="Length ratio threshold for extended finger")

    # --- Sprint A: Temporal Hysteresis State Machine ---
    # A1: Require N consecutive frames of flexion before confirming a click gesture.
    click_confirm_frames: int = Field(default=4, ge=1, le=20, description="Consecutive frames of flexion required to confirm a click (anti-false-positive)")
    # Frames the finger must stay extended after a click before the next one is allowed.
    neutral_frames_after_click: int = Field(default=3, ge=1, le=20, description="Consecutive frames extended required after a click before another can fire")

    # A2: Right-click guard — index must be fully extended (higher threshold) to avoid false right-clicks.
    right_click_index_min_ratio: float = Field(default=1.80, gt=0.0, description="Minimum index extension ratio required for right-click to be valid")

    # Anti-Slip Pre-Click Anchor Lock
    pre_click_lookback_seconds: float = Field(default=0.12, ge=0.0, le=0.30, description="Lookback window in seconds to lock cursor onto target before finger motion starts")

    # Dual Trigger: Micro-Pinch Alternative
    enable_pinch_alternative: bool = Field(default=True, description="Enable micro-pinch as an alternative/hybrid trigger for clicks")
    click_pinch_threshold: float = Field(default=0.045, gt=0.0, description="Distance threshold for thumb-index pinch")
    right_click_pinch_threshold: float = Field(default=0.050, gt=0.0, description="Distance threshold for thumb-middle pinch")

    # Debounce / Hold timings (seconds)
    click_debounce_seconds: float = Field(default=0.25, gt=0.0, description="Minimum duration between consecutive clicks")
    drag_hold_seconds: float = Field(default=0.35, gt=0.0, description="Pinch/bent hold duration before transitioning to drag mode")
    reentry_stabilization_seconds: float = Field(default=0.20, ge=0.0, description="Stabilization time required after re-entering camera before clicks can trigger")

    # Scroll parameters
    scroll_threshold_y: float = Field(default=0.015, gt=0.0, description="Minimum vertical displacement to trigger scroll")
    scroll_speed: int = Field(default=2, ge=1, description="OS scroll event intensity multiplier")
    scroll_cooldown_seconds: float = Field(default=0.04, gt=0.0, description="Cooldown between scroll pulses")

    # Sprint C: Dwell Click (Accessibility)
    enable_dwell_click: bool = Field(default=False, description="Auto left-click when holding cursor still")
    dwell_duration_seconds: float = Field(default=1.2, ge=0.5, le=3.0, description="Dwell hold duration to trigger click")
    dwell_movement_threshold_px: int = Field(default=20, ge=5, le=60, description="Maximum cursor drift allowed during dwell")


class UISettings(BaseModel):
    """Overlay visualization parameters."""
    show_hud: bool = Field(default=True, description="Display overlay HUD")
    show_fps: bool = Field(default=True, description="Display real-time FPS counter")
    show_landmarks: bool = Field(default=True, description="Render hand landmark skeleton")
    sound_enabled: bool = Field(default=True, description="Audio feedback on clicks")
    window_name: str = Field(default="Gesture Mouse - Computer Vision Control", description="OpenCV window title")


class AppSettings(BaseModel):
    """Root configuration for Gesture Mouse application."""
    camera: CameraSettings = Field(default_factory=CameraSettings)
    zone: InteractionZoneSettings = Field(default_factory=InteractionZoneSettings)
    filter: FilterSettings = Field(default_factory=FilterSettings)
    gestures: GestureSettings = Field(default_factory=GestureSettings)
    ui: UISettings = Field(default_factory=UISettings)

    # Model file path
    model_path: str = Field(
        default_factory=get_default_model_path,
        description="Path to MediaPipe hand_landmarker.task model"
    )
