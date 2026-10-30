"""
System Tray Icon Service using pystray and Pillow.
Provides a background taskbar icon with context menu for:
- Pause / Resume mouse control
- Sound Mute / Unmute toggle
- Show / Hide camera preview window
- Quick recalibration trigger
- Start with Windows (Autostart) toggle
- Clean Exit
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional, Callable
from PIL import Image, ImageDraw

import pystray
from gesture_mouse.infrastructure.system.autostart import is_autostart_enabled, set_autostart


@dataclass
class TraySharedState:
    """Thread-safe state shared between System Tray and OpenCV main loop."""
    is_paused: bool = False
    sound_enabled: bool = True
    show_camera: bool = True
    trigger_calibration: bool = False
    request_exit: bool = False


def create_tray_icon_image(size: int = 64) -> Image.Image:
    """Generate a crisp, stylized hand/pointer icon in-memory with Pillow."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Outer circle background
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(24, 28, 36, 255),
        outline=(0, 220, 180, 255),
        width=3,
    )

    # Stylized mouse pointer / pointing hand triangle
    # Points scaled to size
    p1 = (int(size * 0.32), int(size * 0.24))
    p2 = (int(size * 0.32), int(size * 0.76))
    p3 = (int(size * 0.50), int(size * 0.60))
    p4 = (int(size * 0.72), int(size * 0.76))
    p5 = (int(size * 0.78), int(size * 0.68))
    p6 = (int(size * 0.56), int(size * 0.52))
    p7 = (int(size * 0.72), int(size * 0.52))

    draw.polygon([p1, p2, p3, p4, p5, p6, p7], fill=(0, 230, 190, 255))
    return image


class TrayIconService:
    """Manages the Windows taskbar notification area (System Tray) icon."""

    def __init__(
        self,
        state: Optional[TraySharedState] = None,
        on_calibration_request: Optional[Callable[[], None]] = None,
        on_exit_request: Optional[Callable[[], None]] = None,
    ):
        self.state = state or TraySharedState()
        self.on_calibration_request = on_calibration_request
        self.on_exit_request = on_exit_request
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def _on_toggle_pause(self, icon, item):
        self.state.is_paused = not self.state.is_paused
        icon.title = "Gesture Mouse (Pausado)" if self.state.is_paused else "Gesture Mouse (Activo)"

    def _on_toggle_sound(self, icon, item):
        self.state.sound_enabled = not self.state.sound_enabled

    def _on_toggle_camera(self, icon, item):
        self.state.show_camera = not self.state.show_camera

    def _on_recalibrate(self, icon, item):
        self.state.trigger_calibration = True
        if self.on_calibration_request:
            self.on_calibration_request()

    def _on_toggle_autostart(self, icon, item):
        current = is_autostart_enabled()
        set_autostart(not current)

    def _on_exit(self, icon, item):
        self.state.request_exit = True
        if self.on_exit_request:
            self.on_exit_request()
        icon.stop()

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                "Pausar Ratón",
                self._on_toggle_pause,
                checked=lambda item: self.state.is_paused,
            ),
            pystray.MenuItem(
                "Feedback Sonoro",
                self._on_toggle_sound,
                checked=lambda item: self.state.sound_enabled,
            ),
            pystray.MenuItem(
                "Mostrar Cámara",
                self._on_toggle_camera,
                checked=lambda item: self.state.show_camera,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Recalibrar Gestos [C]",
                self._on_recalibrate,
            ),
            pystray.MenuItem(
                "Iniciar con Windows",
                self._on_toggle_autostart,
                checked=lambda item: is_autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self._on_exit),
        )

    def start(self) -> None:
        """Launch the tray icon inside a background daemon thread."""
        image = create_tray_icon_image()
        self._icon = pystray.Icon(
            name="gesture_mouse",
            icon=image,
            title="Gesture Mouse",
            menu=self._build_menu(),
        )

        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="TrayIconThread")
        self._thread.start()

    def stop(self) -> None:
        """Stop and remove the tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
