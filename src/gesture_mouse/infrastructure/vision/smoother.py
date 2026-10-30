"""
Signal smoothing implementations: One Euro Filter and Moving Average Smoother.
Implements ISmoother to eliminate jitter while minimizing latency.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Tuple, Optional

from gesture_mouse.domain.interfaces import ISmoother


class LowPassFilter:
    """Standard first-order low-pass filter helper."""

    def __init__(self, alpha: float = 0.5):
        self._alpha = alpha
        self._y: Optional[float] = None
        self._s: Optional[float] = None

    def filter(self, value: float, alpha: Optional[float] = None) -> float:
        if alpha is not None:
            self._alpha = alpha

        if self._s is None:
            self._s = value
        else:
            self._s = self._alpha * value + (1.0 - self._alpha) * self._s
        return self._s

    def last_value(self) -> Optional[float]:
        return self._s

    def reset(self) -> None:
        self._s = None


class OneEuroFilter1D:
    """
    1D One Euro Filter implementation.
    Adaptive low-pass filter: high smoothing at low velocity (eliminates jitter),
    low smoothing at high velocity (eliminates latency/lag).
    """

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff

        self._x_filter = LowPassFilter()
        self._dx_filter = LowPassFilter()
        self._last_time: Optional[float] = None

    def _alpha(self, cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, x: float, timestamp: float) -> float:
        if self._last_time is None:
            self._last_time = timestamp
            return self._x_filter.filter(x)

        dt = timestamp - self._last_time
        self._last_time = timestamp

        # Guard against zero or negative delta time
        if dt <= 0.0:
            last = self._x_filter.last_value()
            return last if last is not None else x

        # Estimate current rate of change (derivative)
        prev_x = self._x_filter.last_value()
        dx = (x - prev_x) / dt if prev_x is not None else 0.0

        # Filter the derivative
        alpha_d = self._alpha(self.d_cutoff, dt)
        edx = self._dx_filter.filter(dx, alpha_d)

        # Adapt cutoff frequency based on velocity
        cutoff = self.min_cutoff + self.beta * abs(edx)

        # Filter signal
        alpha = self._alpha(cutoff, dt)
        return self._x_filter.filter(x, alpha)

    def reset(self) -> None:
        self._x_filter.reset()
        self._dx_filter.reset()
        self._last_time = None


class OneEuroSmoother(ISmoother):
    """
    2D One Euro Filter for screen coordinates / normalized points.
    Applies independent adaptive filtering to X and Y channels.
    """

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007, d_cutoff: float = 1.0):
        self._filter_x = OneEuroFilter1D(min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)
        self._filter_y = OneEuroFilter1D(min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)

    def filter(self, x: float, y: float, timestamp: float) -> Tuple[float, float]:
        smoothed_x = self._filter_x.filter(x, timestamp)
        smoothed_y = self._filter_y.filter(y, timestamp)
        return (smoothed_x, smoothed_y)

    def reset(self) -> None:
        self._filter_x.reset()
        self._filter_y.reset()


class MovingAverageSmoother(ISmoother):
    """
    Simple Moving Average filter over a rolling window.
    Low computational complexity, but introduces symmetrical lag proportional to window size.
    """

    def __init__(self, window_size: int = 5):
        if window_size < 1:
            raise ValueError(f"Window size must be at least 1, got {window_size}")
        self.window_size = window_size
        self._history_x: deque[float] = deque(maxlen=window_size)
        self._history_y: deque[float] = deque(maxlen=window_size)

    def filter(self, x: float, y: float, timestamp: float) -> Tuple[float, float]:
        self._history_x.append(x)
        self._history_y.append(y)
        avg_x = sum(self._history_x) / len(self._history_x)
        avg_y = sum(self._history_y) / len(self._history_y)
        return (avg_x, avg_y)

    def reset(self) -> None:
        self._history_x.clear()
        self._history_y.clear()
