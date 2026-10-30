"""
Unit tests for Smoothing Filters (One Euro Filter and Moving Average).
"""

import pytest
import math
from gesture_mouse.infrastructure.vision.smoother import (
    OneEuroFilter1D,
    OneEuroSmoother,
    MovingAverageSmoother,
)


def test_moving_average_smoother():
    smoother = MovingAverageSmoother(window_size=3)

    # Initial values
    x1, y1 = smoother.filter(10.0, 20.0, 1.0)
    assert x1 == 10.0 and y1 == 20.0

    x2, y2 = smoother.filter(20.0, 40.0, 1.1)
    assert x2 == 15.0 and y2 == 30.0

    x3, y3 = smoother.filter(30.0, 60.0, 1.2)
    assert x3 == 20.0 and y3 == 40.0

    # 4th sample: oldest sample (10.0, 20.0) is popped
    x4, y4 = smoother.filter(40.0, 80.0, 1.3)
    # (20 + 30 + 40)/3 = 30.0
    assert math.isclose(x4, 30.0, rel_tol=1e-5)
    # (40 + 60 + 80)/3 = 60.0
    assert math.isclose(y4, 60.0, rel_tol=1e-5)

    smoother.reset()
    assert len(smoother._history_x) == 0


def test_one_euro_filter_1d_low_velocity_damping():
    """At low velocity, One Euro Filter should heavily damp small jitter."""
    f = OneEuroFilter1D(min_cutoff=0.5, beta=0.001)

    # Base signal around 100 with small jitter
    t = 0.0
    out = f.filter(100.0, t)
    assert out == 100.0

    # Small oscillation
    jittered_values = [102.0, 98.0, 101.5, 98.5, 100.5]
    outputs = []
    for val in jittered_values:
        t += 0.033  # ~30 FPS
        out = f.filter(val, t)
        outputs.append(out)

    # Output should stay closely bounded near 100 without extreme jumps
    for out in outputs:
        assert 98.5 <= out <= 101.5


def test_one_euro_filter_1d_high_velocity_tracking():
    """At high velocity, the filter adapts cutoff and follows signal with minimal lag."""
    f = OneEuroFilter1D(min_cutoff=1.0, beta=0.1)

    # Jump from 0 to 1000 rapidly
    t = 0.0
    f.filter(0.0, t)

    t += 0.033
    fast_out = f.filter(1000.0, t)

    # Due to high beta, fast_out should make a significant jump towards 1000
    assert fast_out > 200.0


def test_one_euro_smoother_2d():
    smoother = OneEuroSmoother(min_cutoff=1.0, beta=0.01)

    sx, sy = smoother.filter(100.0, 200.0, 1.0)
    assert sx == 100.0 and sy == 200.0

    sx2, sy2 = smoother.filter(105.0, 205.0, 1.033)
    assert 100.0 < sx2 < 105.0
    assert 200.0 < sy2 < 205.0

    smoother.reset()
    assert smoother._filter_x._last_time is None
