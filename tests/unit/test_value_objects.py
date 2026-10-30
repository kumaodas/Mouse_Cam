"""
Unit tests for Domain Value Objects.
"""

import pytest
import math
from gesture_mouse.domain.models import NormalizedPoint
from gesture_mouse.domain.value_objects import (
    ScreenCoordinate,
    ScreenSize,
    Distance,
    InteractionZone,
    MouseButton,
)


def test_screen_coordinate_clamp():
    coord = ScreenCoordinate(x=-50, y=2000)
    clamped = coord.clamp(min_x=0, min_y=0, max_x=1919, max_y=1079)
    assert clamped.x == 0
    assert clamped.y == 1079
    assert clamped.to_tuple() == (0, 1079)


def test_screen_size_validation():
    size = ScreenSize(width=1920, height=1080)
    assert size.width == 1920
    assert size.height == 1080

    with pytest.raises(ValueError):
        ScreenSize(width=-10, height=1080)


def test_euclidean_distance():
    p1 = NormalizedPoint(x=0.0, y=0.0, z=0.0)
    p2 = NormalizedPoint(x=3.0, y=4.0, z=0.0)
    dist_2d = Distance.euclidean_2d(p1, p2)
    assert math.isclose(dist_2d, 5.0, rel_tol=1e-5)

    p3 = NormalizedPoint(x=0.0, y=0.0, z=12.0)
    # p1=(0,0,0) to (3,4,12) -> sqrt(9+16+144) = sqrt(169) = 13.0
    p4 = NormalizedPoint(x=3.0, y=4.0, z=12.0)
    dist_3d = Distance.euclidean_3d(p1, p4)
    assert math.isclose(dist_3d, 13.0, rel_tol=1e-5)


def test_interaction_zone_mapping():
    # Zone margins 0.2 (active range x in [0.2, 0.8], y in [0.2, 0.8])
    zone = InteractionZone(margin_x=0.2, margin_y=0.2)
    screen = ScreenSize(width=1000, height=500)

    # Center point (0.5, 0.5) should map to center of screen
    pt_center = NormalizedPoint(x=0.5, y=0.5)
    screen_center = zone.map_to_screen(pt_center, screen)
    # norm = (0.5 - 0.2)/0.6 = 0.5 -> 0.5 * 999 = 499, 0.5 * 499 = 249
    assert abs(screen_center.x - 499) <= 1
    assert abs(screen_center.y - 249) <= 1

    # Point at top-left corner of active zone
    pt_corner = NormalizedPoint(x=0.2, y=0.2)
    screen_corner = zone.map_to_screen(pt_corner, screen)
    assert screen_corner.x == 0
    assert screen_corner.y == 0

    # Point outside active zone (should clamp to 0 or max screen pixel)
    pt_outside = NormalizedPoint(x=0.05, y=0.95)
    screen_outside = zone.map_to_screen(pt_outside, screen)
    assert screen_outside.x == 0
    assert screen_outside.y == 499


def test_interaction_zone_invalid_margin():
    with pytest.raises(ValueError):
        InteractionZone(margin_x=0.6, margin_y=0.1)


def test_interaction_zone_asymmetric_margins():
    zone = InteractionZone(
        margin_left=0.18,
        margin_right=0.18,
        margin_top=0.12,
        margin_bottom=0.35,
    )
    screen = ScreenSize(width=1920, height=1080)

    # Top-left corner of active area -> (0, 0)
    pt_tl = NormalizedPoint(0.18, 0.12)
    res_tl = zone.map_to_screen(pt_tl, screen)
    assert res_tl.x == 0 and res_tl.y == 0

    # Bottom-right corner of active area -> (1919, 1079)
    pt_br = NormalizedPoint(0.82, 0.65)
    res_br = zone.map_to_screen(pt_br, screen)
    assert res_br.x == 1919 and res_br.y == 1079

    # Point beyond bottom edge (e.g. y=0.80) should stay locked at bottom of screen
    pt_low = NormalizedPoint(0.50, 0.85)
    res_low = zone.map_to_screen(pt_low, screen)
    assert res_low.y == 1079
