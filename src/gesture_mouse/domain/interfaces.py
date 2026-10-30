"""
Domain Interfaces (Contracts / Ports).
Pure abstract base classes defining expectations for infrastructure adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Any

from gesture_mouse.domain.models import Hand
from gesture_mouse.domain.value_objects import ScreenCoordinate, ScreenSize, MouseButton


class IHandTracker(ABC):
    """Port for computer vision hand tracking."""

    @abstractmethod
    def track(self, frame: Any, timestamp_ms: int) -> Optional[Hand]:
        """Process a video frame and extract hand landmarks."""
        pass

    def track_all(self, frame: Any, timestamp_ms: int) -> list[Hand]:
        """Process a video frame and extract all detected hands (up to 2)."""
        hand = self.track(frame, timestamp_ms)
        return [hand] if hand is not None else []

    @abstractmethod
    def close(self) -> None:
        """Release tracker resources."""
        pass


class ISmoother(ABC):
    """Port for signal smoothing algorithms (One Euro, Moving Average)."""

    @abstractmethod
    def filter(self, x: float, y: float, timestamp: float) -> Tuple[float, float]:
        """Apply smoothing to 2D coordinate stream."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset internal filter states and histories."""
        pass


class IMouseController(ABC):
    """Port for low-level OS mouse control."""

    @abstractmethod
    def move_to(self, coordinate: ScreenCoordinate) -> None:
        """Move OS cursor to specified coordinate."""
        pass

    @abstractmethod
    def get_position(self) -> ScreenCoordinate:
        """Get current OS cursor position."""
        pass

    @abstractmethod
    def click(self, button: MouseButton) -> None:
        """Single click mouse button."""
        pass

    @abstractmethod
    def press(self, button: MouseButton) -> None:
        """Press down mouse button (start drag)."""
        pass

    @abstractmethod
    def release(self, button: MouseButton) -> None:
        """Release mouse button (end drag)."""
        pass

    @abstractmethod
    def scroll(self, dx: int, dy: int) -> None:
        """Emit scroll wheel events."""
        pass

    @abstractmethod
    def get_screen_size(self) -> ScreenSize:
        """Get primary monitor dimensions in pixels."""
        pass
