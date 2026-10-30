"""
Unit tests for SettingsRepository.
"""

from pathlib import Path
from gesture_mouse.infrastructure.config.settings import AppSettings
from gesture_mouse.infrastructure.config.repository import SettingsRepository


def test_settings_repository_load_default_when_file_missing(tmp_path: Path):
    missing_file = tmp_path / "non_existent_settings.json"
    repo = SettingsRepository(missing_file)
    settings = repo.load()
    assert isinstance(settings, AppSettings)
    assert settings.gestures.click_confirm_frames == 4


def test_settings_repository_save_and_reload(tmp_path: Path):
    save_file = tmp_path / "custom_settings.json"
    repo = SettingsRepository(save_file)

    custom_settings = AppSettings()
    custom_settings.gestures.finger_bent_ratio = 1.35
    custom_settings.gestures.click_confirm_frames = 6
    custom_settings.camera.camera_index = 1

    success = repo.save(custom_settings)
    assert success is True
    assert save_file.exists()

    reloaded = repo.load()
    assert reloaded.gestures.finger_bent_ratio == 1.35
    assert reloaded.gestures.click_confirm_frames == 6
    assert reloaded.camera.camera_index == 1
