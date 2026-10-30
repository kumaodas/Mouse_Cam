"""
Audio feedback service for Gesture Mouse.
Plays gentle beeps on click events using Windows winsound or no-op fallback.
Executed in background daemon threads to prevent any frame drops or UI latency.
"""

from __future__ import annotations

import sys
import threading
from typing import Optional


class SoundService:
    """Non-blocking sound player for UX feedback."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._is_windows = sys.platform == "win32"

    def _play_async(self, frequency: int, duration_ms: int) -> None:
        if not self.enabled or not self._is_windows:
            return

        def _worker():
            try:
                import winsound
                winsound.Beep(frequency, duration_ms)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def play_left_click(self) -> None:
        """Play soft crisp tone for left click."""
        self._play_async(1050, 40)

    def play_right_click(self) -> None:
        """Play distinct double tone or higher pitch for right click."""
        self._play_async(1500, 60)

    def play_dwell_click(self) -> None:
        """Play short chime for dwell click."""
        self._play_async(850, 50)

    def play_calibration_complete(self) -> None:
        """Play celebration beep on calibration finish."""
        def _worker():
            try:
                import winsound
                winsound.Beep(800, 70)
                winsound.Beep(1200, 100)
            except Exception:
                pass

        if self.enabled and self._is_windows:
            threading.Thread(target=_worker, daemon=True).start()
