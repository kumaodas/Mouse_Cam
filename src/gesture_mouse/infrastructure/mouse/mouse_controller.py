"""
Mouse Controller Adapter using pynput.
Implements IMouseController to command physical OS cursor and mouse events.
"""

from __future__ import annotations

import sys
from typing import Optional
from pynput.mouse import Controller as PynputController, Button as PynputButton

from gesture_mouse.domain.interfaces import IMouseController
from gesture_mouse.domain.value_objects import ScreenCoordinate, ScreenSize, MouseButton


class PynputMouseController(IMouseController):
    """OS Mouse Controller adapter wrapping pynput."""

    def __init__(self, override_screen_size: Optional[ScreenSize] = None):
        self._controller = PynputController()
        self._button_map = {
            MouseButton.LEFT: PynputButton.left,
            MouseButton.RIGHT: PynputButton.right,
            MouseButton.MIDDLE: PynputButton.middle,
        }
        self._screen_size = override_screen_size or self._detect_screen_size()

    def _detect_screen_size(self) -> ScreenSize:
        """Detect primary monitor resolution with Windows DPI awareness."""
        if sys.platform == "win32":
            try:
                import ctypes
                # Attempt to enable DPI awareness for true physical screen pixels
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
                except Exception:
                    try:
                        ctypes.windll.user32.SetProcessDPIAware()
                    except Exception:
                        pass

                user32 = ctypes.windll.user32
                width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
                height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
                if width > 0 and height > 0:
                    return ScreenSize(width=width, height=height)
            except Exception:
                pass

        # Fallback to tkinter or default
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            w = root.winfo_screenwidth()
            h = root.winfo_screenheight()
            root.destroy()
            return ScreenSize(width=w, height=h)
        except Exception:
            return ScreenSize(width=1920, height=1080)

    def get_screen_size(self) -> ScreenSize:
        return self._screen_size

    def move_to(self, coordinate: ScreenCoordinate) -> None:
        # Clamp to screen boundary to prevent OS cursor lockouts
        clamped = coordinate.clamp(
            min_x=0,
            min_y=0,
            max_x=self._screen_size.width - 1,
            max_y=self._screen_size.height - 1
        )
        self._controller.position = (clamped.x, clamped.y)

    def get_position(self) -> ScreenCoordinate:
        pos_x, pos_y = self._controller.position
        return ScreenCoordinate(x=int(pos_x), y=int(pos_y))

    def click(self, button: MouseButton) -> None:
        p_button = self._button_map.get(button, PynputButton.left)
        self._controller.click(p_button, 1)

    def press(self, button: MouseButton) -> None:
        p_button = self._button_map.get(button, PynputButton.left)
        self._controller.press(p_button)

    def release(self, button: MouseButton) -> None:
        p_button = self._button_map.get(button, PynputButton.left)
        self._controller.release(p_button)

    def scroll(self, dx: int, dy: int) -> None:
        self._controller.scroll(dx, dy)
