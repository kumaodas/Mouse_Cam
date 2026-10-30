"""
Settings persistence repository for Gesture Mouse.
Saves and loads user preferences from JSON using Pydantic serialization.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from gesture_mouse.infrastructure.config.settings import AppSettings


class SettingsRepository:
    """Manages loading and saving AppSettings to disk."""

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is not None:
            self._path = Path(config_path)
        else:
            self._path = Path.home() / ".gesture_mouse" / "settings.json"

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> AppSettings:
        """
        Load settings from file. If file does not exist or is invalid,
        returns fresh default AppSettings.
        """
        if not self._path.exists():
            return AppSettings()

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AppSettings.model_validate(data)
        except Exception as e:
            print(f"[SettingsRepository] Warning: Could not load {self._path} ({e}). Using defaults.")
            return AppSettings()

    def save(self, settings: AppSettings) -> bool:
        """Save settings to disk. Returns True on success, False on error."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(settings.model_dump_json(indent=2))
            return True
        except Exception as e:
            print(f"[SettingsRepository] Error: Could not save to {self._path} ({e}).")
            return False
