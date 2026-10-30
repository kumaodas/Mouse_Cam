from unittest.mock import MagicMock
from PIL import Image
import pytest

from gesture_mouse.presentation.tray import (
    TraySharedState,
    TrayIconService,
    create_tray_icon_image,
)


def test_create_tray_icon_image():
    img = create_tray_icon_image(size=64)
    assert isinstance(img, Image.Image)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


def test_tray_shared_state_defaults():
    state = TraySharedState()
    assert state.is_paused is False
    assert state.sound_enabled is True
    assert state.show_camera is True
    assert state.trigger_calibration is False
    assert state.request_exit is False


def test_tray_service_toggles():
    state = TraySharedState()
    calib_mock = MagicMock()
    exit_mock = MagicMock()
    service = TrayIconService(
        state=state,
        on_calibration_request=calib_mock,
        on_exit_request=exit_mock,
    )
    mock_icon = MagicMock()

    # Toggle pause
    service._on_toggle_pause(mock_icon, None)
    assert state.is_paused is True
    assert "Pausado" in mock_icon.title

    service._on_toggle_pause(mock_icon, None)
    assert state.is_paused is False
    assert "Activo" in mock_icon.title

    # Toggle sound
    service._on_toggle_sound(mock_icon, None)
    assert state.sound_enabled is False
    service._on_toggle_sound(mock_icon, None)
    assert state.sound_enabled is True

    # Toggle camera
    service._on_toggle_camera(mock_icon, None)
    assert state.show_camera is False
    service._on_toggle_camera(mock_icon, None)
    assert state.show_camera is True

    # Recalibrate
    service._on_recalibrate(mock_icon, None)
    assert state.trigger_calibration is True
    calib_mock.assert_called_once()

    # Exit
    service._on_exit(mock_icon, None)
    assert state.request_exit is True
    exit_mock.assert_called_once()
    mock_icon.stop.assert_called_once()


def test_build_menu():
    service = TrayIconService()
    menu = service._build_menu()
    assert menu is not None
