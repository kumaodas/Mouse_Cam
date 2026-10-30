# Gesture Mouse: Control del Cursor Mediante Visión Artificial

---

## 1. Fundamentos y Herramientas: El "Qué" y el "Con Qué"

Para un proyecto de estas características, **Python 3.10+** es una elección fantástica: el ecosistema de librerías es maduro y permite prototipar y llevar a producción de forma eficiente.

### Stack Tecnológico Recomendado

| Componente | Herramienta / Librería | Propósito Principal |
| :--- | :--- | :--- |
| **Lenguaje** | Python 3.10+ | Lenguaje base. Prototipado rápido y control de hardware. |
| **Visión por Computadora** | OpenCV (`opencv-python`) | Captura y procesamiento de video en tiempo real (frames). |
| **Detección de Manos** | MediaPipe | Framework de Google para detección de 21 puntos clave (*landmarks*) con alta velocidad y precisión (CPU/GPU). |
| **Control del Ratón** | `pynput` | Emulación de eventos de ratón/teclado. Más robusta y fluida en segundo plano que `pyautogui`. |
| **Suavizado de Señal** | Media Móvil / Filtro $1€$ | Algoritmos para eliminar el *jitter* (temblor) de la detección. |
| **Tipado y Validación** | Pydantic | Modelado de datos estricto y configuración tipada (umbrales, tolerancias). |
| **Gestor de Entorno** | Poetry / `pip-tools` | Control reproducible de dependencias y empaquetado. |

---

## 2. Conceptos Clave a Dominar

### Landmarks de la Mano (MediaPipe)
MediaPipe indexa 21 puntos tridimensionales por mano ($0$ al $20$). Los puntos críticos para este diseño son:
* **Landmark 8 (`INDEX_FINGER_TIP`):** Punta del dedo índice, utilizado como ancla para dirigir las coordenadas del cursor.
* **Landmark 4 (`THUMB_TIP`):** Punta del pulgar, utilizado para calcular distancias relativas de activación (gesto *pinch*).
* **Landmark 12 (`MIDDLE_FINGER_TIP`):** Punta del dedo medio, empleado en combinaciones secundarias.

### Mapeo de Gestos

```
       [Landmark 8: Índice] <--- Distancia Euclidiana ---> [Landmark 4: Pulgar]
                 |                                                 |
         (Cursor (x, y))                                      (Clic/Pinch)
```

* **Mover Cursor:** Coordenadas normalizadas $(x, y)$ del Landmark 8 transformadas linealmente a la resolución de pantalla.
* **Clic Izquierdo (Pinch):** Activado cuando la distancia euclidiana $d(L_4, L_8) < \text{umbral}$ (ej. 35 px) acompañada de una ventana temporal mínima (*debounce*).
* **Clic Derecho:** Activado por proximidad entre pulgar y dedo medio: $d(L_4, L_{12}) < \text{umbral}$.
* **Scroll:** Desplazamiento vertical cuando índice y medio permanecen extendidos en paralelo.

### Jitter vs. Latencia (Delay)
* **Jitter:** Ruido de alta frecuencia inherente a la estimación visual entre fotogramas.
* **Delay:** Retardo inducido por los buffers de suavizado.
* **Meta:** Lograr estabilidad espacial sin comprometer la respuesta táctil percibida.

---

## 3. Arquitectura de Software: Limpia, Escalable y Testeable

Se aplica **Clean Architecture** para desacoplar la lógica matemática y de negocio frente a librerías de hardware/cámara.

### Estructura de Directorios

```text
gesture_mouse/
├── src/
│   └── gesture_mouse/
│       ├── domain/                 # 🧠 Capa de Dominio (Lógica Pura)
│       │   ├── models.py           # Entidades: Punto, Mano, Gesto
│       │   ├── value_objects.py    # Coordenada, Distancia, Velocidad
│       │   └── interfaces.py       # Contratos y Protocolos (Interfaces)
│       │
│       ├── application/            # 🚀 Capa de Aplicación (Casos de Uso)
│       │   ├── use_cases.py        # MoverCursor, DetectarClic, EjecutarScroll
│       │   └── services/
│       │       └── gesture_service.py # Orquestación y estado de gestos
│       │
│       ├── infrastructure/         # 🔧 Capa de Infraestructura (Detalles Técnicos)
│       │   ├── vision/
│       │   │   ├── hand_tracker.py # Adaptador de MediaPipe
│       │   │   └── smoother.py     # Implementaciones: Moving Average, One Euro Filter
│       │   ├── mouse/
│       │   │   └── mouse_controller.py # Adaptador pynput
│       │   └── config/
│       │       └── settings.py     # Configuración vía Pydantic
│       │
│       └── presentation/           # 🖥️ Capa de Presentación (Entrypoint)
│           └── main.py             # Loop principal, contenedor DI y renderizado
├── tests/
│   ├── unit/                       # Pruebas de dominio y aplicación
│   └── integration/                # Pruebas de adaptadores de infraestructura
├── pyproject.toml                  # Configuración Poetry / dependencias
└── README.md
```

> **Regla de Dependencias:** El flujo de llamadas avanza hacia adentro. La capa `presentation` inyecta las implementaciones de `infrastructure` dentro de los casos de uso de `application`, los cuales operan exclusivamente contra abstracciones declaradas en `domain`.

---

## 4. Estrategia contra el Jitter y el Delay: Filtros en Acción

### Comparativa de Algoritmos

```
[Señal Cruda] ---> [Filtro Seleccionado] ---> [Posición en Pantalla]
```

1. **Filtro de Media Móvil (Moving Average):**
   * Computa el promedio de las últimas $N$ observaciones ($N \approx 5$).
   * *Ventaja:* Implementación trivial.
   * *Desventaja:* Añade latencia simétrica constante proporcional al tamaño de la ventana $N$.

2. **Filtro $1€$ (One Euro Filter):**
   * Filtro pasa-bajas adaptativo basado en dos parámetros: frecuencia de corte mínima ($f_c$) y factor de velocidad ($\beta$).
   * **Baja velocidad:** Reduce la frecuencia de corte para amortiguar drásticamente el temblor involuntario al apuntar a un objetivo estático.
   * **Alta velocidad:** Aumenta la frecuencia de corte para eliminar la latencia visual en desplazamientos rápidos.

> **Recomendación técnica:** Implementar directamente el **Filtro $1€$**. La respuesta dinámica mejora de forma sustancial la precisión sin generar sensación de arrastre o retraso.

---

## 5. Plan de Acción Inicial (Roadmap por Sprints)

```
Sprint 0 (Setup) ──> Sprint 1 (Cursor) ──> Sprint 2 (Clics) ──> Sprint 3 (Estabilidad) ──> Sprint 4 (Extras)
```

- [x] **Sprint 0: Setup y Validación de Concepto (Completado)**
  - Inicializar entorno virtual e instalar dependencias con compatibilidad Python 3.13 (`opencv-python`, `mediapipe 1.1+`, `pynput`, `pydantic`, `pytest`).
  - Definir árbol base de paquetes con Clean Architecture (`pyproject.toml`, editable install).
  - Validar inferencia de MediaPipe HandLandmarker con descarga automática del modelo `hand_landmarker.task`.
- [x] **Sprint 1: Movimiento del Cursor (Completado)**
  - Implementar adaptador `MediaPipeHandTracker` (infraestructura) para extracción de landmarks.
  - Diseñar interfaces y módulo `Smoother` con Filtro 1€ (`OneEuroSmoother`) y Media Móvil (`MovingAverageSmoother`).
  - Integrar `PynputMouseController` con detección de resolución nativa y soporte DPI de Windows.
  - Orquestar caso de uso `MoveCursorUseCase` con mapeo proporcional e interpolación de márgenes (`InteractionZone`).
- [x] **Sprint 2: Gestos de Clic (Completado)**
  - Modelar cálculo de distancia euclidiana en `domain/value_objects.py`.
  - Implementar máquina de estados en `DetectClickUseCase` con debounce temporal, detección de clics y arrastre sostenido (drag & drop).
  - Mapear clics izquierdo ($L_4 \leftrightarrow L_8$) y derecho ($L_4 \leftrightarrow L_{12}$).
- [x] **Sprint 3: Refinamiento y Estabilidad (Completado)**
  - Calibrar parámetros del Filtro $1€$ y umbrales con Pydantic (`settings.py`).
  - Cobertura completa de tests unitarios e integración con pytest (16 tests pasando).
  - Manejo robusto de pérdida de tracking (mano fuera de frame con reset de suavizado y liberación segura de botones).
- [x] **Sprint 4: Extras (Completado)**
  - Implementar caso de uso `ScrollGestureUseCase` con detección de dos dedos paralelos (índice y medio).
  - Overlay HUD avanzado en tiempo real con OpenCV: gauge de distancia de pinch, badges de estado por color, indicador de FPS, zona activa visible y selector de filtro en caliente con tecla 'F'.