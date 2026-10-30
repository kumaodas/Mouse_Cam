"""
Presentation Layer / Entrypoint.
Initializes Dependency Injection, runs the camera loop, and renders a modern visual HUD.
"""

from __future__ import annotations

import sys
import os
import time
import argparse

# Suppress internal TensorFlow / MediaPipe C++ verbosity
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "3"

import cv2
import numpy as np

from gesture_mouse.domain.value_objects import InteractionZone, ScreenCoordinate
from gesture_mouse.infrastructure.config.settings import AppSettings
from gesture_mouse.infrastructure.config.repository import SettingsRepository
from gesture_mouse.infrastructure.audio.sound_service import SoundService
from gesture_mouse.infrastructure.vision.smoother import OneEuroSmoother, MovingAverageSmoother
from gesture_mouse.infrastructure.vision.hand_tracker import MediaPipeHandTracker
from gesture_mouse.infrastructure.mouse.mouse_controller import PynputMouseController
from gesture_mouse.application.use_cases import (
    MoveCursorUseCase,
    DetectClickUseCase,
    ScrollGestureUseCase,
    CalibrationUseCase,
    DwellClickUseCase,
)
from gesture_mouse.application.services.gesture_service import GestureService, ProcessResult
from gesture_mouse.domain.models import GestureType, HandLandmarkId
from gesture_mouse.presentation.tray import TrayIconService, TraySharedState


class HUDOverlay:
    """Renders user feedback, gesture badges, and diagnostics on OpenCV frames."""

    # Color palette (BGR)
    COLOR_BG_CARD = (30, 30, 30)
    COLOR_ACCENT = (0, 200, 255)
    COLOR_TEXT = (240, 240, 240)
    COLOR_MUTED = (140, 140, 140)

    GESTURE_COLORS = {
        GestureType.IDLE: (100, 100, 100),
        GestureType.MOVE: (60, 220, 60),
        GestureType.LEFT_CLICK: (255, 200, 0),
        GestureType.RIGHT_CLICK: (255, 50, 200),
        GestureType.DRAGGING: (0, 140, 255),
        GestureType.SCROLLING: (0, 220, 255),
        GestureType.STABILIZING: (0, 165, 255),
        GestureType.OUT_OF_BOUNDS: (0, 0, 230),
    }

    @staticmethod
    def draw(
        frame: np.ndarray,
        result: ProcessResult,
        fps: float,
        zone: InteractionZone,
        settings: AppSettings,
        current_smoother_name: str,
        show_debug: bool = False,
        calib_active: bool = False,
        calib_remaining: float = 0.0,
        toast_msg: str = "",
        dwell_progress: float = 0.0,
        drag_start_point: Optional[tuple[int, int]] = None,
        show_help: bool = False,
        is_paused: bool = False,
    ) -> np.ndarray:
        h, w, _ = frame.shape

        # 1. Draw Safety Sensor Margin (Camera edge threshold)
        sm = settings.zone.safety_edge_margin
        sx1, sy1 = int(sm * w), int(sm * h)
        sx2, sy2 = int((1.0 - sm) * w), int((1.0 - sm) * h)
        cv2.rectangle(frame, (sx1, sy1), (sx2, sy2), (50, 50, 50), 1, cv2.LINE_AA)

        # 2. Draw Active Interaction Zone
        x1, y1 = int(zone.x_min * w), int(zone.y_min * h)
        x2, y2 = int(zone.x_max * w), int(zone.y_max * h)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(
            frame,
            "Active Zone",
            (x1 + 8, y1 + 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (200, 200, 200),
            1,
            cv2.LINE_AA
        )

        # 3. If Hand is Out of Bounds / At Border: Draw Alert Frame
        if result.is_out_of_bounds:
            cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 230), 4)
            cv2.putText(
                frame,
                "SAFETY LOCK: HAND AT CAMERA BORDER - ACTIONS FROZEN",
                (w // 2 - 250, h // 2),
                cv2.FONT_HERSHEY_DUPLEX,
                0.6,
                (0, 0, 255),
                1,
                cv2.LINE_AA
            )

        # 4. Draw Top HUD Panel
        panel_h = 75
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, panel_h), HUDOverlay.COLOR_BG_CARD, -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

        # Title & FPS
        cv2.putText(frame, "GESTURE MOUSE", (20, 30), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 230, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"FPS: {fps:.1f}", (20, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, HUDOverlay.COLOR_TEXT, 1, cv2.LINE_AA)

        # Smoother Filter Mode
        cv2.putText(frame, f"Filter: {current_smoother_name}", (150, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.5, HUDOverlay.COLOR_MUTED, 1, cv2.LINE_AA)

        # Audio Status Pill [M] (Option to enable/disable sound)
        audio_active = settings.ui.sound_enabled
        aud_w, aud_h = 135, 26
        ax = 320
        ay = 40
        aud_bg = (20, 110, 20) if audio_active else (35, 35, 80)
        aud_border = (0, 230, 0) if audio_active else (50, 50, 220)
        aud_txt = "[M] AUDIO: ON" if audio_active else "[M] AUDIO: OFF"
        cv2.rectangle(frame, (ax, ay), (ax + aud_w, ay + aud_h), aud_bg, -1)
        cv2.rectangle(frame, (ax, ay), (ax + aud_w, ay + aud_h), aud_border, 1)
        cv2.putText(frame, aud_txt, (ax + 10, ay + 18), cv2.FONT_HERSHEY_DUPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

        # Gesture Status Badge
        if is_paused:
            gesture_name = "PAUSADO (BANDEJA)"
            badge_color = (0, 140, 255)
        else:
            gesture_name = result.gesture.value if result.hand else "SEARCHING HAND"
            badge_color = HUDOverlay.GESTURE_COLORS.get(result.gesture, (100, 100, 100)) if result.hand else (80, 80, 80)
        
        badge_w, badge_h = 240, 44
        bx = w - badge_w - 20
        by = 15
        cv2.rectangle(frame, (bx, by), (bx + badge_w, by + badge_h), badge_color, -1, cv2.LINE_AA)
        cv2.rectangle(frame, (bx, by), (bx + badge_w, by + badge_h), (255, 255, 255), 1, cv2.LINE_AA)
        
        text_size = cv2.getTextSize(gesture_name, cv2.FONT_HERSHEY_DUPLEX, 0.60, 1)[0]
        tx = bx + (badge_w - text_size[0]) // 2
        ty = by + (badge_h + text_size[1]) // 2
        cv2.putText(frame, gesture_name, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, 0.60, (0, 0, 0), 1, cv2.LINE_AA)

        # Centered Pause Banner if active
        if is_paused:
            banner_w, banner_h = 380, 54
            px = (w - banner_w) // 2
            py = h // 2 - 27
            pause_overlay = frame.copy()
            cv2.rectangle(pause_overlay, (px, py), (px + banner_w, py + banner_h), (20, 20, 20), -1)
            cv2.addWeighted(pause_overlay, 0.85, frame, 0.15, 0, frame)
            cv2.rectangle(frame, (px, py), (px + banner_w, py + banner_h), (0, 165, 255), 2)
            cv2.putText(frame, "PAUSADO DESDE LA BANDEJA", (px + 20, py + 34), cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 165, 255), 1, cv2.LINE_AA)

        # 5. Virtual Mouse Buttons Feedback (Option A: Finger Flexion + Confidence Progress)
        if result.hand and not result.is_out_of_bounds:
            # Highlight bent fingers on the hand skeleton
            if result.is_index_bent:
                px = int(result.hand.index_pip.x * w)
                py = int(result.hand.index_pip.y * h)
                cv2.circle(frame, (px, py), 16, (0, 220, 255), 2, cv2.LINE_AA)
                cv2.circle(frame, (px, py), 8, (0, 220, 255), -1, cv2.LINE_AA)

            if result.is_middle_bent:
                px = int(result.hand.middle_pip.x * w)
                py = int(result.hand.middle_pip.y * h)
                cv2.circle(frame, (px, py), 16, (255, 50, 200), 2, cv2.LINE_AA)
                cv2.circle(frame, (px, py), 8, (255, 50, 200), -1, cv2.LINE_AA)

            # --- Virtual Left Mouse Button ---
            btn_w, btn_h = 175, 48
            x_lbtn, y_lbtn = 20, h - 90
            color_lbtn = (0, 200, 255) if result.is_index_bent else (40, 40, 40)
            text_color_lbtn = (0, 0, 0) if result.is_index_bent else (220, 220, 220)
            cv2.rectangle(frame, (x_lbtn, y_lbtn), (x_lbtn + btn_w, y_lbtn + btn_h), color_lbtn, -1)
            cv2.rectangle(frame, (x_lbtn, y_lbtn), (x_lbtn + btn_w, y_lbtn + btn_h), (255, 255, 255), 1)

            # Left button flexion progress (0.0 = extended, 1.0 = bent)
            b_ratio = settings.gestures.finger_bent_ratio
            e_ratio = settings.gestures.finger_extended_ratio
            l_prog = np.clip((e_ratio - result.index_ratio) / max(0.01, (e_ratio - b_ratio)), 0.0, 1.0)
            
            # Left progress bar
            l_bar_w = int((btn_w - 6) * l_prog)
            l_bar_color = (0, 220, 0) if l_prog < 0.6 else ((0, 200, 255) if l_prog < 0.95 else (0, 50, 255))
            if l_bar_w > 0:
                cv2.rectangle(frame, (x_lbtn + 3, y_lbtn + btn_h - 6), (x_lbtn + 3 + l_bar_w, y_lbtn + btn_h - 2), l_bar_color, -1)

            frames_str = f"[{result.left_bent_frames}/{result.click_confirm_frames}]" if result.left_bent_frames > 0 else ""
            neutral_str = " (NEUTRO)" if result.left_in_neutral else ""
            lbtn_status = f"IND: {result.index_ratio:.2f} {frames_str}{neutral_str}"
            cv2.putText(frame, "BOTON IZQUIERDO", (x_lbtn + 10, y_lbtn + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.38, text_color_lbtn, 1, cv2.LINE_AA)
            cv2.putText(frame, lbtn_status, (x_lbtn + 10, y_lbtn + 34), cv2.FONT_HERSHEY_DUPLEX, 0.40, text_color_lbtn, 1, cv2.LINE_AA)

            # --- Virtual Right Mouse Button ---
            x_rbtn = x_lbtn + btn_w + 10
            color_rbtn = (255, 50, 200) if result.is_middle_bent else (40, 40, 40)
            text_color_rbtn = (0, 0, 0) if result.is_middle_bent else (220, 220, 220)
            cv2.rectangle(frame, (x_rbtn, y_lbtn), (x_rbtn + btn_w, y_lbtn + btn_h), color_rbtn, -1)
            cv2.rectangle(frame, (x_rbtn, y_lbtn), (x_rbtn + btn_w, y_lbtn + btn_h), (255, 255, 255), 1)

            # Right button flexion progress
            r_prog = np.clip((e_ratio - result.middle_ratio) / max(0.01, (e_ratio - b_ratio)), 0.0, 1.0)
            r_bar_w = int((btn_w - 6) * r_prog)
            r_bar_color = (0, 220, 0) if r_prog < 0.6 else ((0, 200, 255) if r_prog < 0.95 else (255, 50, 200))
            if r_bar_w > 0:
                cv2.rectangle(frame, (x_rbtn + 3, y_lbtn + btn_h - 6), (x_rbtn + 3 + r_bar_w, y_lbtn + btn_h - 2), r_bar_color, -1)

            rframes_str = f"[{result.right_bent_frames}/{result.click_confirm_frames}]" if result.right_bent_frames > 0 else ""
            rneutral_str = " (NEUTRO)" if result.right_in_neutral else ""
            rbtn_status = f"MED: {result.middle_ratio:.2f} {rframes_str}{rneutral_str}"
            cv2.putText(frame, "BOTON DERECHO", (x_rbtn + 10, y_lbtn + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.38, text_color_rbtn, 1, cv2.LINE_AA)
            cv2.putText(frame, rbtn_status, (x_rbtn + 10, y_lbtn + 34), cv2.FONT_HERSHEY_DUPLEX, 0.40, text_color_rbtn, 1, cv2.LINE_AA)

            # Target Locked indicator if currently clicking
            if result.gesture in (GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK):
                x_lock = x_rbtn + btn_w + 10
                cv2.rectangle(frame, (x_lock, y_lbtn), (x_lock + 120, y_lbtn + btn_h), (0, 200, 0), -1)
                cv2.rectangle(frame, (x_lock, y_lbtn), (x_lock + 120, y_lbtn + btn_h), (255, 255, 255), 1)
                cv2.putText(frame, "ANTI-SLIP", (x_lock + 12, y_lbtn + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 1, cv2.LINE_AA)
                cv2.putText(frame, "BLOQUEADO", (x_lock + 12, y_lbtn + 38), cv2.FONT_HERSHEY_DUPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

        # 6. Debug Telemetry Floating Panel (Toggle with Hotkey 'D')
        if show_debug and result.hand:
            dbg_w, dbg_h = 320, 180
            dx = w - dbg_w - 20
            dy = 90
            dbg_overlay = frame.copy()
            cv2.rectangle(dbg_overlay, (dx, dy), (dx + dbg_w, dy + dbg_h), (20, 20, 20), -1)
            cv2.addWeighted(dbg_overlay, 0.85, frame, 0.15, 0, frame)
            cv2.rectangle(frame, (dx, dy), (dx + dbg_w, dy + dbg_h), (0, 200, 255), 1)

            guard_ok = result.index_ratio >= settings.gestures.right_click_index_min_ratio
            guard_txt = "PASS" if guard_ok else "BLOQUEADO"
            guard_color = (0, 255, 0) if guard_ok else (0, 50, 255)

            lines = [
                ("--- TELEMETRIA DEBUG [D] ---", (0, 230, 255)),
                (f"Indice Ratio: {result.index_ratio:.2f} (Bent<{settings.gestures.finger_bent_ratio:.2f})", (220, 220, 220)),
                (f"Indice Frames: {result.left_bent_frames}/{result.click_confirm_frames} | Neutro: {result.left_in_neutral}", (200, 200, 200)),
                (f"Medio Ratio : {result.middle_ratio:.2f} (Bent<{settings.gestures.finger_bent_ratio:.2f})", (220, 220, 220)),
                (f"Guardia Der (Indice > {settings.gestures.right_click_index_min_ratio:.2f}): {guard_txt}", guard_color),
                (f"Pinza Izq dist: {result.left_pinch_dist:.3f} (< {settings.gestures.click_pinch_threshold:.3f})", (200, 200, 200)),
                (f"Pinza Der dist: {result.right_pinch_dist:.3f} (< {settings.gestures.right_click_pinch_threshold:.3f})", (200, 200, 200)),
            ]
            for i, (txt, col) in enumerate(lines):
                cv2.putText(frame, txt, (dx + 10, dy + 22 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.40, col, 1, cv2.LINE_AA)

        # 7. Drag Visual Feedback (C3: Trail & pulsing badge)
        if result.gesture == GestureType.DRAGGING and result.hand:
            curr_x = int(result.hand.index_pip.x * w)
            curr_y = int(result.hand.index_pip.y * h)
            if drag_start_point is not None:
                cv2.line(frame, drag_start_point, (curr_x, curr_y), (0, 140, 255), 2, cv2.LINE_AA)
                cv2.circle(frame, drag_start_point, 6, (0, 100, 255), -1, cv2.LINE_AA)

            # Pulsing indicator badge near drag point
            blink = (int(time.time() * 4) % 2) == 0
            badge_bg = (0, 140, 255) if blink else (0, 80, 180)
            cv2.rectangle(frame, (curr_x + 12, curr_y - 25), (curr_x + 130, curr_y - 5), badge_bg, -1)
            cv2.rectangle(frame, (curr_x + 12, curr_y - 25), (curr_x + 130, curr_y - 5), (255, 255, 255), 1)
            cv2.putText(frame, "ARRASTRANDO", (curr_x + 18, curr_y - 10), cv2.FONT_HERSHEY_DUPLEX, 0.40, (0, 0, 0), 1, cv2.LINE_AA)

        # 8. Dwell-Click Ring Indicator (C2)
        if dwell_progress > 0.0 and result.hand:
            tx = int(result.hand.index_tip.x * w)
            ty = int(result.hand.index_tip.y * h)
            radius = 24
            # Background guide ring
            cv2.circle(frame, (tx, ty), radius, (60, 60, 60), 2, cv2.LINE_AA)
            # Progress arc
            end_angle = int(360 * dwell_progress)
            cv2.ellipse(frame, (tx, ty), (radius, radius), -90, 0, end_angle, (0, 240, 255), 3, cv2.LINE_AA)

        # 9. Calibration Banner (Center overlay during calibration)
        if calib_active:
            box_w, box_h = 560, 100
            bx = (w - box_w) // 2
            by = (h - box_h) // 2
            cal_overlay = frame.copy()
            cv2.rectangle(cal_overlay, (bx, by), (bx + box_w, by + box_h), (20, 20, 40), -1)
            cv2.addWeighted(cal_overlay, 0.85, frame, 0.15, 0, frame)
            cv2.rectangle(frame, (bx, by), (bx + box_w, by + box_h), (0, 220, 255), 2)

            cv2.putText(frame, "CALIBRANDO: MANTEN TU MANO ABIERTA Y RELAJADA", (bx + 25, by + 35), cv2.FONT_HERSHEY_DUPLEX, 0.55, (0, 230, 255), 1, cv2.LINE_AA)
            cv2.putText(frame, f"Tiempo restante: {calib_remaining:.1f}s", (bx + 25, by + 65), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (220, 220, 220), 1, cv2.LINE_AA)

            # Progress bar
            prog = max(0.0, min(1.0, (3.0 - calib_remaining) / 3.0))
            cv2.rectangle(frame, (bx + 25, by + 78), (bx + box_w - 25, by + 86), (60, 60, 60), -1)
            cv2.rectangle(frame, (bx + 25, by + 78), (bx + 25 + int((box_w - 50) * prog), by + 86), (0, 220, 255), -1)

        # 10. Toast notification banner
        if toast_msg:
            t_box_w = min(w - 40, len(toast_msg) * 12 + 40)
            tx = (w - t_box_w) // 2
            ty = panel_h + 12
            toast_overlay = frame.copy()
            cv2.rectangle(toast_overlay, (tx, ty), (tx + t_box_w, ty + 38), (10, 60, 20), -1)
            cv2.addWeighted(toast_overlay, 0.90, frame, 0.10, 0, frame)
            cv2.rectangle(frame, (tx, ty), (tx + t_box_w, ty + 38), (0, 230, 0), 1)
            cv2.putText(frame, toast_msg, (tx + 15, ty + 24), cv2.FONT_HERSHEY_DUPLEX, 0.48, (240, 255, 240), 1, cv2.LINE_AA)

        # 11. Help Modal Overlay (C4: Toggle with [H])
        if show_help:
            hw_w, hw_h = min(w - 60, 680), min(h - 60, 420)
            hx = (w - hw_w) // 2
            hy = (h - hw_h) // 2
            h_overlay = frame.copy()
            cv2.rectangle(h_overlay, (hx, hy), (hx + hw_w, hy + hw_h), (18, 18, 22), -1)
            cv2.addWeighted(h_overlay, 0.92, frame, 0.08, 0, frame)
            cv2.rectangle(frame, (hx, hy), (hx + hw_w, hy + hw_h), (0, 200, 255), 2)

            cv2.putText(frame, "GUIA RAPIDA DE GESTOS Y ATAJOS [H]", (hx + 24, hy + 38), cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 230, 255), 1, cv2.LINE_AA)
            cv2.line(frame, (hx + 20, hy + 48), (hx + hw_w - 20, hy + 48), (60, 60, 60), 1)

            help_lines = [
                ("GESTOS DE CONTROL:", (255, 200, 0)),
                ("  - Mover Cursor    : Mueve el dedo indice dentro de la Zona Activa", (220, 220, 220)),
                ("  - Clic Izquierdo  : Dobla el indice hacia abajo o haz pinza pulgar-indice", (220, 220, 220)),
                ("  - Clic Derecho    : Dobla el dedo medio (con indice extendido) o pinza pulgar-medio", (220, 220, 220)),
                ("  - Arrastrar/Soltar: Manten el indice doblado > 0.35s y desplaza la mano", (220, 220, 220)),
                ("  - Scroll Vertical : Junta indice y medio extendidos y mueve arriba/abajo", (220, 220, 220)),
                ("ATAJOS DE TECLADO:", (255, 200, 0)),
                ("  [Q/ESC] Salir         | [F] Alternar Filtro    | [D] Telemetria Debug", (200, 200, 200)),
                ("  [C]     Calibrar (3s) | [T] Sliders en Vivo    | [S] Guardar en Disco", (200, 200, 200)),
                ("  [W]     Dwell Clic    | [M] Sonido On/Off      | [H] Cerrar esta Ayuda", (200, 200, 200)),
            ]
            for i, (txt, col) in enumerate(help_lines):
                cv2.putText(frame, txt, (hx + 24, hy + 76 + i * 26), cv2.FONT_HERSHEY_SIMPLEX, 0.44, col, 1, cv2.LINE_AA)

        # 12. Instructions footer
        cv2.putText(
            frame,
            "[Q] Salir | [F] Filtro | [D] Debug | [C] Calibrar | [T] Sliders | [S] Guardar | [W] Dwell | [M] Audio | [H] Ayuda",
            (20, h - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (200, 200, 200),
            1,
            cv2.LINE_AA
        )

        return frame


def create_gesture_service(settings: AppSettings, smoother_type: str = "one_euro") -> tuple[GestureService, MediaPipeHandTracker, Any, PynputMouseController]:
    """Dependency Injection factory assembling Clean Architecture layers."""
    # 1. Vision Adapter
    hand_tracker = MediaPipeHandTracker(
        model_path=settings.model_path,
        num_hands=1
    )

    # 2. Smoother Filter Adapter
    if smoother_type == "moving_average":
        smoother = MovingAverageSmoother(window_size=settings.filter.moving_average_window)
    else:
        smoother = OneEuroSmoother(
            min_cutoff=settings.filter.one_euro_min_cutoff,
            beta=settings.filter.one_euro_beta,
            d_cutoff=settings.filter.one_euro_d_cutoff,
        )

    # 3. Mouse Controller Adapter
    mouse_controller = PynputMouseController()

    # 4. Domain Value Object
    zone = InteractionZone(
        margin_left=settings.zone.margin_left,
        margin_right=settings.zone.margin_right,
        margin_top=settings.zone.margin_top,
        margin_bottom=settings.zone.margin_bottom,
    )

    # 5. Application Use Cases
    move_cursor_uc = MoveCursorUseCase(
        mouse_controller=mouse_controller,
        smoother=smoother,
        zone=zone,
        lookback_seconds=settings.gestures.pre_click_lookback_seconds,
    )
    detect_click_uc = DetectClickUseCase(mouse_controller, settings.gestures)
    scroll_gesture_uc = ScrollGestureUseCase(mouse_controller, settings.gestures)

    # 6. Service Orchestrator
    service = GestureService(
        hand_tracker=hand_tracker,
        move_cursor_uc=move_cursor_uc,
        detect_click_uc=detect_click_uc,
        scroll_gesture_uc=scroll_gesture_uc,
        safety_edge_margin=settings.zone.safety_edge_margin,
        reentry_stabilization_seconds=settings.gestures.reentry_stabilization_seconds,
    )

    return service, hand_tracker, zone, mouse_controller


def main() -> None:
    parser = argparse.ArgumentParser(description="Gesture Mouse: Vision-based computer cursor control.")
    parser.add_argument("--camera", type=int, default=None, help="Webcam device index")
    parser.add_argument("--filter", type=str, choices=["one_euro", "moving_average"], default=None, help="Smoothing filter")
    parser.add_argument("--sound", action="store_true", default=None, help="Activar feedback sonoro")
    parser.add_argument("--no-sound", "--mute", dest="sound", action="store_false", help="Desactivar feedback sonoro (Mute)")
    parser.add_argument("--no-tray", dest="tray", action="store_false", default=True, help="Desactivar icono en la bandeja del sistema")
    parser.add_argument("--hidden", action="store_true", default=False, help="Iniciar minimizado en la bandeja del sistema")
    args = parser.parse_args()

    repo = SettingsRepository()
    settings = repo.load()

    if args.camera is not None:
        settings.camera.camera_index = args.camera
    if args.sound is not None:
        settings.ui.sound_enabled = args.sound
    current_filter_mode = args.filter if args.filter is not None else settings.filter.smoother_type

    print("=" * 60)
    print(" GESTURE MOUSE - Clean Architecture & Computer Vision")
    print("=" * 60)
    print(f" Config file  : {repo.path}")
    print(f" Camera index : {settings.camera.camera_index}")
    print(f" Smoother     : {current_filter_mode}")
    print(f" Audio Sonido : {'ACTIVADO' if settings.ui.sound_enabled else 'DESACTIVADO (Mute)'}")
    print(f" Target Res   : {settings.camera.width}x{settings.camera.height}")
    print(f" Flexion Thresh: {settings.gestures.finger_bent_ratio:.2f}")
    print(f" Extension Thr : {settings.gestures.finger_extended_ratio:.2f}")
    print("-" * 60)

    # Initialize DI container
    service, tracker, zone, mouse_controller = create_gesture_service(settings, current_filter_mode)

    # Initialize UX helpers (Sprint C)
    sound = SoundService(enabled=settings.ui.sound_enabled)
    dwell_uc = DwellClickUseCase(
        mouse_controller=mouse_controller,
        dwell_duration=settings.gestures.dwell_duration_seconds,
        movement_threshold_px=settings.gestures.dwell_movement_threshold_px,
    )

    # Open Camera
    cap = cv2.VideoCapture(settings.camera.camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.camera.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.camera.height)

    if not cap.isOpened():
        print(f"[Error] Could not open camera {settings.camera.camera_index}.")
        print("Please verify your webcam connection or select another camera with --camera <id>.")
        sys.exit(1)

    print("[Ready] Running loop. Hotkeys:")
    print("  [Q/ESC] Salir")
    print("  [F]     Alternar Filtro (1-Euro / Moving Avg)")
    print("  [D]     Panel de Telemetria Debug")
    print("  [C]     Calibracion Automatica Guiada (3 seg)")
    print("  [T]     Sliders en Vivo (Trackbars)")
    print("  [S]     Guardar Configuracion en Disco")
    print("  [W]     Alternar Dwell-Click (Accesibilidad)")
    print("  [M]     Alternar Sonido (Feedback Audio)")
    print("  [H]     Guia Rapida en Pantalla")

    fps = 0.0
    prev_time = time.time()
    frame_count = 0
    show_debug = False
    show_trackbars = False
    show_help = False
    enable_dwell = settings.gestures.enable_dwell_click
    trackbar_win_name = "Ajustes de Calibracion [T]"

    calibration_uc = CalibrationUseCase(duration_seconds=3.0)
    calib_remaining = 0.0
    toast_msg = ""
    toast_until = 0.0

    last_gesture = GestureType.IDLE
    drag_start_point: Optional[tuple[int, int]] = None

    # System Tray Service (Sprint E)
    tray_state = TraySharedState(
        is_paused=False,
        sound_enabled=settings.ui.sound_enabled,
        show_camera=not args.hidden,
    )
    tray_service = None
    if args.tray:
        try:
            tray_service = TrayIconService(state=tray_state)
            tray_service.start()
            print("[Tray] Icono de bandeja del sistema (System Tray) activado.")
        except Exception as e:
            print(f"[Tray] Aviso: No se pudo iniciar el icono de bandeja: {e}")

    def nothing(x: int) -> None:
        pass

    try:
        while True:
            # Check exit request from system tray
            if tray_state.request_exit:
                print("[Tray] Salida solicitada desde la bandeja del sistema.")
                break

            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            current_time = time.time()
            frame_count += 1
            if current_time - prev_time >= 1.0:
                fps = frame_count / (current_time - prev_time)
                frame_count = 0
                prev_time = current_time

            # Flip horizontally for natural mirror behavior
            if settings.camera.flip_horizontal:
                frame = cv2.flip(frame, 1)

            # Check calibration trigger from tray
            if tray_state.trigger_calibration:
                tray_state.trigger_calibration = False
                if not calibration_uc.is_active:
                    calibration_uc.start(current_time)
                    toast_msg = "CALIBRANDO: Manten tu mano abierta y relajada (3s)..."
                    toast_until = current_time + 3.0
                    print("[Tray] Calibracion activada desde la bandeja.")

            # Sync audio state with tray
            sound.enabled = tray_state.sound_enabled
            settings.ui.sound_enabled = sound.enabled

            # Process frame through domain pipeline (or bypass when paused)
            if not tray_state.is_paused:
                result = service.process_frame(frame, current_time)
            else:
                hands = tracker.track_all(frame, int(current_time * 1000))
                hand = hands[0] if hands else None
                result = ProcessResult(
                    hand=hand,
                    cursor_position=ScreenCoordinate(0, 0),
                    gesture=GestureType.IDLE,
                    is_safe=True,
                    is_out_of_bounds=False,
                )

            # Sound feedback on gesture transitions (C1)
            if result.gesture == GestureType.LEFT_CLICK and last_gesture != GestureType.LEFT_CLICK:
                sound.play_left_click()
            elif result.gesture == GestureType.RIGHT_CLICK and last_gesture != GestureType.RIGHT_CLICK:
                sound.play_right_click()

            # Drag start point tracking (C3)
            if result.gesture == GestureType.DRAGGING:
                if drag_start_point is None and result.hand:
                    drag_start_point = (
                        int(result.hand.index_pip.x * frame.shape[1]),
                        int(result.hand.index_pip.y * frame.shape[0]),
                    )
            else:
                drag_start_point = None

            # Dwell-Click Evaluation (C2)
            dwell_prog = 0.0
            if enable_dwell:
                is_manual_click = result.gesture in (GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK, GestureType.DRAGGING)
                dw_trig, dwell_prog = dwell_uc.execute(result.cursor_position, current_time, is_gesture_clicking=is_manual_click)
                if dw_trig:
                    sound.play_dwell_click()
                    toast_msg = "DWELL-CLICK DISPARADO!"
                    toast_until = current_time + 1.2

            last_gesture = result.gesture

            # Handle Calibration sampling (B1)
            if calibration_uc.is_active:
                if result.hand:
                    done, remaining, cal_res = calibration_uc.sample(result.hand, current_time)
                    calib_remaining = remaining
                    if done and cal_res:
                        settings.gestures.finger_bent_ratio = cal_res["finger_bent_ratio"]
                        settings.gestures.finger_extended_ratio = cal_res["finger_extended_ratio"]
                        settings.gestures.right_click_index_min_ratio = cal_res["right_click_index_min_ratio"]
                        repo.save(settings)
                        sound.play_calibration_complete()
                        toast_msg = f"CALIBRACION GUARDADA! Bent<{cal_res['finger_bent_ratio']:.2f} Ext>{cal_res['finger_extended_ratio']:.2f}"
                        toast_until = current_time + 4.0
                        print(f"[Calibracion] {toast_msg}")
                else:
                    calib_remaining = 3.0

            # Active toast check
            active_toast = toast_msg if current_time < toast_until else ""

            # Update settings from trackbars if open (B3)
            if show_trackbars:
                try:
                    b_val = max(100, cv2.getTrackbarPos("Flexion x100", trackbar_win_name)) / 100.0
                    e_val = max(130, cv2.getTrackbarPos("Extension x100", trackbar_win_name)) / 100.0
                    cf_val = max(1, cv2.getTrackbarPos("Confirm Frames", trackbar_win_name))
                    lb_val = max(40, cv2.getTrackbarPos("Lookback ms", trackbar_win_name)) / 1000.0
                    s_val = cv2.getTrackbarPos("Sonido (0/1)", trackbar_win_name)
                    settings.gestures.finger_bent_ratio = b_val
                    settings.gestures.finger_extended_ratio = e_val
                    settings.gestures.click_confirm_frames = cf_val
                    settings.gestures.pre_click_lookback_seconds = lb_val
                    sound.enabled = (s_val == 1)
                    settings.ui.sound_enabled = sound.enabled
                except Exception:
                    pass

            # Draw visual landmarks if hand detected
            if settings.ui.show_landmarks and result.hand:
                tracker.draw_landmarks(frame, result.hand)

            # Render HUD diagnostics
            if settings.ui.show_hud:
                HUDOverlay.draw(
                    frame=frame,
                    result=result,
                    fps=fps,
                    zone=zone,
                    settings=settings,
                    current_smoother_name="1-Euro Filter" if current_filter_mode == "one_euro" else "Moving Avg",
                    show_debug=show_debug,
                    calib_active=calibration_uc.is_active,
                    calib_remaining=calib_remaining,
                    toast_msg=active_toast,
                    dwell_progress=dwell_prog,
                    drag_start_point=drag_start_point,
                    show_help=show_help,
                    is_paused=tray_state.is_paused,
                )

            if tray_state.show_camera:
                cv2.imshow(settings.ui.window_name, frame)
                key = cv2.waitKey(1) & 0xFF
            else:
                try:
                    cv2.destroyWindow(settings.ui.window_name)
                except Exception:
                    pass
                time.sleep(0.01)
                key = -1
            if key in (ord('q'), ord('Q'), 27):  # 'q' or ESC
                break
            elif key in (ord('f'), ord('F')):
                # Toggle filter mode dynamically
                current_filter_mode = "moving_average" if current_filter_mode == "one_euro" else "one_euro"
                service.shutdown()
                service, tracker, zone, mouse_controller = create_gesture_service(settings, current_filter_mode)
                dwell_uc = DwellClickUseCase(
                    mouse_controller=mouse_controller,
                    dwell_duration=settings.gestures.dwell_duration_seconds,
                    movement_threshold_px=settings.gestures.dwell_movement_threshold_px,
                )
                print(f"[HUD] Toggled filter to: {current_filter_mode}")
            elif key in (ord('d'), ord('D')):
                show_debug = not show_debug
                print(f"[HUD] Debug panel: {'ACTIVADO' if show_debug else 'DESACTIVADO'}")
            elif key in (ord('c'), ord('C')):
                if not calibration_uc.is_active:
                    calibration_uc.start(current_time)
                    toast_msg = "CALIBRANDO: Manten tu mano abierta y relajada (3s)..."
                    toast_until = current_time + 3.0
                    print("[HUD] Calibracion iniciada (3 segundos)...")
                else:
                    calibration_uc.cancel()
                    toast_msg = "CALIBRACION CANCELADA"
                    toast_until = current_time + 2.0
            elif key in (ord('t'), ord('T')):
                show_trackbars = not show_trackbars
                if show_trackbars:
                    cv2.namedWindow(trackbar_win_name, cv2.WINDOW_NORMAL)
                    cv2.resizeWindow(trackbar_win_name, 440, 260)
                    cv2.createTrackbar("Flexion x100", trackbar_win_name, int(settings.gestures.finger_bent_ratio * 100), 180, nothing)
                    cv2.createTrackbar("Extension x100", trackbar_win_name, int(settings.gestures.finger_extended_ratio * 100), 240, nothing)
                    cv2.createTrackbar("Confirm Frames", trackbar_win_name, settings.gestures.click_confirm_frames, 10, nothing)
                    cv2.createTrackbar("Lookback ms", trackbar_win_name, int(settings.gestures.pre_click_lookback_seconds * 1000), 250, nothing)
                    cv2.createTrackbar("Sonido (0/1)", trackbar_win_name, 1 if sound.enabled else 0, 1, nothing)
                    print("[HUD] Sliders de calibracion abiertos en ventana separada.")
                else:
                    try:
                        cv2.destroyWindow(trackbar_win_name)
                    except Exception:
                        pass
                    print("[HUD] Sliders de calibracion cerrados.")
            elif key in (ord('s'), ord('S')):
                saved = repo.save(settings)
                if saved:
                    toast_msg = f"CONFIGURACION GUARDADA EN {repo.path.name}"
                    toast_until = current_time + 3.0
                    print(f"[Settings] Guardado exitosamente en: {repo.path}")
            elif key in (ord('w'), ord('W')):
                enable_dwell = not enable_dwell
                settings.gestures.enable_dwell_click = enable_dwell
                dwell_uc.reset()
                toast_msg = f"DWELL-CLICK: {'ACTIVADO' if enable_dwell else 'DESACTIVADO'}"
                toast_until = current_time + 2.5
                print(f"[HUD] {toast_msg}")
            elif key in (ord('m'), ord('M')):
                sound.enabled = not sound.enabled
                settings.ui.sound_enabled = sound.enabled
                tray_state.sound_enabled = sound.enabled
                toast_msg = f"FEEDBACK AUDIO: {'ACTIVADO' if sound.enabled else 'MUTED'}"
                toast_until = current_time + 2.0
                print(f"[HUD] {toast_msg}")
            elif key in (ord('h'), ord('H')):
                show_help = not show_help
                print(f"[HUD] Guia de ayuda: {'MOSTRANDO' if show_help else 'OCULTA'}")

    except KeyboardInterrupt:
        print("\n[Gesture Mouse] Interrupted by user.")
    finally:
        print("[Gesture Mouse] Cleaning up resources...")
        if tray_service:
            tray_service.stop()
        service.shutdown()
        cap.release()
        cv2.destroyAllWindows()
        print("[Gesture Mouse] Terminated gracefully.")


if __name__ == "__main__":
    main()
