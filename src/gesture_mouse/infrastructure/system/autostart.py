"""
Windows Autostart integration using the Windows Registry.
Configures Gesture Mouse to optionally launch on Windows login under HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_APP_NAME = "GestureMouse"


def is_windows() -> bool:
    return sys.platform == "win32"


def get_default_command() -> str:
    """Return the default command to execute for autostart."""
    if getattr(sys, "frozen", False):
        # Running as compiled PyInstaller executable
        return f'"{sys.executable}"'
    else:
        # Running from source with python interpreter
        run_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "run.py"))
        return f'"{sys.executable}" "{run_py}"'


def is_autostart_enabled(app_name: str = REG_APP_NAME) -> bool:
    """Check if the application is set to start with Windows in HKCU."""
    if not is_windows():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, app_name)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_autostart(enabled: bool, command: Optional[str] = None, app_name: str = REG_APP_NAME) -> bool:
    """
    Enable or disable autostart in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
    Returns True on success, False on error.
    """
    if not is_windows():
        return False

    cmd = command or get_default_command()

    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass  # Value didn't exist, which is fine
        return True
    except Exception as e:
        print(f"[Autostart] Registry operation failed: {e}")
        return False
