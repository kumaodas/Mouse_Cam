"""
Unit tests for SoundService.
"""

from gesture_mouse.infrastructure.audio.sound_service import SoundService


def test_sound_service_disabled():
    sound = SoundService(enabled=False)
    # Shouldn't raise any exceptions
    sound.play_left_click()
    sound.play_right_click()
    sound.play_dwell_click()
    sound.play_calibration_complete()
    assert sound.enabled is False


def test_sound_service_toggle():
    sound = SoundService(enabled=True)
    assert sound.enabled is True
    sound.enabled = False
    assert sound.enabled is False
