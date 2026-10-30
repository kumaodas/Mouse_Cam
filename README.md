# Gesture Mouse: control del cursor mediante visión artificial

> Estado: versión inicial (`0.1.0`), orientada a Windows 10/11.

Sistema de control de ratón y gestos mediante visión artificial en tiempo real utilizando **Python 3.10+**, **OpenCV**, **MediaPipe (Google Tasks)** y **Pynput**, estructurado bajo los principios de **Clean Architecture** y optimizado con el **Filtro 1€ (One Euro Filter)** para eliminar el jitter sin latencia perceptible.

---
##  Características Principales

- **Arquitectura Limpia (Clean Architecture):** Desacoplamiento total entre la lógica matemática del dominio, casos de uso de la aplicación y librerías de hardware/visión.
- **Detección Precisa de Manos:** MediaPipe HandLandmarker de alta velocidad con 21 landmarks 3D.
- **Filtro 1€ Adaptativo:** Algoritmo de filtrado pasabajas adaptativo con frecuencia de corte dinámica dependiente de la velocidad ($f_c = f_{c,min} + \beta |\dot{x}|$). Máxima estabilidad cuando la mano está quieta y mínima latencia al desplazarse.
- **Zona Activa de Interacción (`InteractionZone`):** Sub-rectángulo configurable para abarcar el 100% de la pantalla sin tener que forzar la mano a los bordes de la cámara.
- **Máquina de Estados de Clic & Arrastre:**
  - **Clic Izquierdo (Pinch):** Unión rápida entre la punta del pulgar ($L_4$) y el índice ($L_8$).
  - **Arrastre (Drag & Drop):** Mantener el pinch durante más de 0.35s activa el botón sostenido.
  - **Clic Derecho:** Unión entre la punta del pulgar ($L_4$) y el dedo medio ($L_{12}$).
  - **Debounce:** Ventana temporal para evitar rebotes involuntarios.
- **Scroll con Dos Dedos:** Desplazamiento vertical extendiendo simultáneamente índice y medio.
- **HUD Visual en Tiempo Real:** Medidor visual de distancia de pinch, badges con código de color por estado de gesto, indicador de FPS, y recuadro de la zona activa.

---

##  Arquitectura del Proyecto

```text
gesture_mouse/
├── src/
│   └── gesture_mouse/
│       ├── domain/                     #  Lógica Pura y Entidades
│       │   ├── models.py               # Hand, NormalizedPoint, HandLandmarkId, GestureType
│       │   ├── value_objects.py        # ScreenCoordinate, ScreenSize, Distance, InteractionZone
│       │   └── interfaces.py           # Contratos: IHandTracker, ISmoother, IMouseController
│       │
│       ├── application/                #  Casos de Uso
│       │   ├── use_cases.py            # MoveCursorUseCase, DetectClickUseCase, ScrollGestureUseCase
│       │   └── services/
│       │       └── gesture_service.py  # Orquestador del pipeline
│       │
│       ├── infrastructure/             #  Implementaciones Técnicas
│       │   ├── vision/
│       │   │   ├── hand_tracker.py     # Adaptador MediaPipe HandLandmarker
│       │   │   └── smoother.py         # One Euro Filter & Moving Average
│       │   ├── mouse/
│       │   │   └── mouse_controller.py # Adaptador pynput con soporte DPI Windows
│       │   └── config/
│       │       └── settings.py         # Validación y configuración con Pydantic
│       │
│       └── presentation/               #  Entrypoint y UI
│           └── main.py                 # Bucle OpenCV, HUD y contenedor DI
├── tests/
│   ├── unit/                           # Pruebas de dominio, filtros y casos de uso
│   └── integration/                    # Pruebas de integración del pipeline completo
├── pyproject.toml                      # Empaquetado y dependencias
└── README.md
```

---

## Instalación y requisitos

### Requisitos
- Windows 10/11
- Python 3.10, 3.11, 3.12 o 3.13
- Cámara web USB o integrada

### Instalación Rápida

1. **Crear entorno virtual e instalar dependencias:**
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   python -m pip install -e .
   ```

2. **Ejecutar suite de tests:**
   ```bash
   python -m pytest -v
   ```

---

##  Uso y Controles

### Iniciar la aplicación

Tienes varias alternativas para ejecutar el programa:

#### 1. Ejecutable portable (sin Python)

Descarga y descomprime el ZIP publicado en la sección **Releases** del
repositorio. Después ejecuta `GestureMouse.exe`. Los artefactos de `dist/` no
se versionan: se generan para cada lanzamiento.

#### 2. Doble clic con entorno virtual Python
Haz doble clic sobre [run.bat](run.bat) en el Explorador de Archivos de Windows.

#### 3. Mediante script PowerShell
```powershell
.\run.ps1
```

#### 4. Mediante el script raíz `run.py`
```powershell
.\.venv\Scripts\python.exe run.py
```

---

## 🎛️ Bandeja del Sistema (System Tray) & Autostart

Gesture Mouse incluye integración nativa con la barra de tareas de Windows (al lado del reloj):

- **⏸ Pausar / Reanudar Ratón:** Congela el cursor temporalmente para escribir en el teclado físico o descansar el brazo.
- **🔊 Feedback Sonoro:** Alterna el audio táctil (beeps) en clics.
- **👁 Mostrar / Ocultar Cámara:** Permite minimizar la ventana OpenCV para trabajar discretamente y con mínimo consumo de CPU.
- **⚙ Recalibrar Gestos:** Lanza la calibración guiada en cualquier momento.
- **🚀 Iniciar con Windows:** Configura la aplicación para iniciarse automáticamente con el sistema (vía Registro de Windows `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`), sin requerir permisos de administrador.
- **❌ Salir:** Cierra ordenadamente la aplicación y libera la cámara web.

### Controles en Tiempo Real (Atajos de Teclado)
| Tecla | Acción |
| :--- | :--- |
| **`Q`** o **`ESC`** | Salir de la aplicación y liberar la cámara. |
| **`F`** | Alternar en caliente entre **1-Euro Filter** y **Moving Average**. |
| **`D`** | Activar/desactivar **Panel de Telemetría y Debug** con ratios en tiempo real. |
| **`C`** | Iniciar **Calibración Automática Guiada (3 seg)** de tu mano abierta. |
| **`T`** | Abrir/cerrar **Sliders en Vivo (Trackbars)** para calibración milimétrica en caliente. |
| **`S`** | **Guardar Configuración** actual en disco (`~/.gesture_mouse/settings.json`). |
| **`W`** | Alternar **Dwell-Click** (Clic automático por permanencia / Accesibilidad). |
| **`M`** | Activar/silenciar **Feedback de Audio** (beeps táctiles en clics). |
| **`H`** | Mostrar/ocultar la **Guía Rápida de Ayuda** en pantalla completa. |

### Mapeo de Gestos

#### Mano Principal / Derecha (Control del Ratón)
*Dispone de **Bloqueo Anti-Slip (Pre-Click Anchor)**: al iniciar cualquier clic, el cursor se congela automáticamente sobre la posición exacta donde estabas apuntando, eliminando el desplazamiento o resbalón por la flexión del dedo.*

| Gesto Principal (Opción A) | Gesto Alternativo (Micro-Pinza) | Acción en el Ratón | Descripción |
| :--- | :--- | :--- | :--- |
| **Dedos extendidos** | Mano abierta | **Mover Cursor** | Mueve el puntero fluidamente en la zona activa. |
| **Doblar Índice hacia abajo** | **Pinch Pulgar + Índice** | **Clic Izquierdo (Tap)** | **Cursor congelado en el objetivo**; al soltar el dedo dispara el clic. |
| **Índice doblado (>0.35s)** | **Pinch sostenido (>0.35s)** | **Arrastrar (Drag & Drop)** | Inicia arrastre y permite mover la ventana o texto; al estirar se suelta. |
| **Doblar Medio hacia abajo** | **Pinch Pulgar + Medio** | **Clic Derecho** | **Cursor congelado en el objetivo**; dispara clic derecho instantáneo. |
| **2 Dedos (Índice + Medio)** | - | **Scroll Vertical** | Mover ambos dedos arriba o abajo para hacer scroll suave. |
| **Mano al borde de cámara** | - | **Bloqueo de Seguridad** | Congela el cursor inmediatamente y anula cualquier clic involuntario. |

#### Control y Pausa
El sistema está optimizado para **1 sola mano** con mínimo consumo de CPU. Si deseas descansar la mano o usar el teclado físico, puedes pausar el control en cualquier momento con clic derecho en el icono de la bandeja del sistema (*System Tray*) seleccionando **Pausar Ratón**.

---

##  Configuración (`settings.py`)

Todos los parámetros se gestionan mediante **Pydantic**:

```python
from gesture_mouse.infrastructure.config.settings import AppSettings

settings = AppSettings()
# Ajustes de cámara
settings.camera.camera_index = 0
settings.camera.flip_horizontal = True

# Sensibilidad y Mapeo Ergonómico Asimétrico (100% Cobertura de Pantalla)
settings.zone.margin_left = 0.18    # Llega al borde izquierdo sin forzar la mano
settings.zone.margin_right = 0.18   # Llega al borde derecho
settings.zone.margin_top = 0.12     # Llega a la barra superior
settings.zone.margin_bottom = 0.35  # Llega a la barra de tareas inferior sin que la muñeca salga de la cámara

# Calibración del Filtro 1€
settings.filter.one_euro_min_cutoff = 1.0  # Frecuencia mínima (Hz)
settings.filter.one_euro_beta = 0.007      # Sensibilidad a la velocidad

# Umbrales de Flexión de Dedos (Air Mouse)
settings.gestures.finger_bent_ratio = 1.40      # Doblado (clic)
settings.gestures.finger_extended_ratio = 1.60  # Extendido (reposo)
settings.gestures.drag_hold_seconds = 0.35      # Tiempo para arrastrar
```

---

##  Pruebas Automatizadas

El proyecto incluye pruebas unitarias y de integración:
```bash
python -m pytest -v
```
- Cobertura de cálculos de distancia euclidiana 2D/3D y límites de pantalla.
- Verificación del comportamiento del Filtro 1€ ante señales con ruido y altas velocidades.
- Pruebas de la máquina de estados de clic, arrastre y debounce con controladores simulados (`MockMouseController`).
- Prueba de integración end-to-end con el modelo de MediaPipe en memoria.

---

## Empaquetado y distribución

### Paquete Python

Instala las herramientas y genera el wheel y la distribución fuente:

```powershell
python -m pip install -e ".[build]"
python -m build
python -m twine check dist/*
```

El modelo `hand_landmarker.task` se incluye en ambos formatos. Prueba el wheel
en un entorno virtual limpio antes de publicarlo.

### Portable para Windows

```powershell
python -m pip install -e ".[build]"
python -m PyInstaller --clean --noconfirm gesture_mouse.spec
Compress-Archive -Path .\dist\GestureMouse -DestinationPath .\dist\GestureMouse-v0.1.0-windows-x64.zip
```

Publica el ZIP como artefacto de una versión; no subas `build/`, `dist/`, el
entorno virtual ni cachés al repositorio.

## Estructura para mantenimiento

- `src/gesture_mouse/domain`: entidades, valores e interfaces sin dependencias
  de hardware.
- `src/gesture_mouse/application`: casos de uso y coordinación de gestos.
- `src/gesture_mouse/infrastructure`: cámara, MediaPipe, ratón, audio,
  configuración y autoinicio.
- `src/gesture_mouse/presentation`: CLI, ventana OpenCV y bandeja del sistema.
- `tests/unit` y `tests/integration`: validación automatizada.
- `assets`: iconos usados por el portable.
- `.github/workflows/ci.yml`: pruebas y validación del paquete.

Consulta [CONTRIBUTING.md](CONTRIBUTING.md) para preparar cambios y
[CHANGELOG.md](CHANGELOG.md) para el historial de versiones.

## Privacidad y seguridad

Los fotogramas de la cámara se procesan localmente y no se transmiten por la
aplicación. El programa controla el cursor del sistema y, si se habilita el
autoinicio, modifica únicamente la clave de usuario de Windows. Revisa el
código y descarga ejecutables solamente desde una fuente de confianza.

## Licencia

Distribuido bajo la licencia MIT. Consulta [LICENSE](LICENSE).
