from unittest.mock import MagicMock, patch
import pytest

from gesture_mouse.infrastructure.system.autostart import (
    is_autostart_enabled,
    set_autostart,
    get_default_command,
)


def test_get_default_command():
    cmd = get_default_command()
    assert isinstance(cmd, str)
    assert len(cmd) > 0


@patch("sys.platform", "win32")
def test_is_autostart_enabled_true():
    mock_winreg = MagicMock()
    mock_key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key
    mock_winreg.QueryValueEx.return_value = ("path/to/exe", 1)

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        assert is_autostart_enabled() is True


@patch("sys.platform", "win32")
def test_is_autostart_enabled_false_on_not_found():
    mock_winreg = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.side_effect = FileNotFoundError()

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        assert is_autostart_enabled() is False


@patch("sys.platform", "win32")
def test_set_autostart_enable():
    mock_winreg = MagicMock()
    mock_key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        success = set_autostart(True, command="C:\\path\\app.exe")
        assert success is True
        mock_winreg.SetValueEx.assert_called_once()


@patch("sys.platform", "win32")
def test_set_autostart_disable():
    mock_winreg = MagicMock()
    mock_key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        success = set_autostart(False)
        assert success is True
        mock_winreg.DeleteValue.assert_called_once()
