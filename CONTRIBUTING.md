# Contribuir a Gesture Mouse

Gracias por ayudar a mejorar el proyecto. Antes de enviar cambios, abre un
issue o describe claramente el problema que resuelve la contribución.

## Preparar el entorno

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Validar cambios

```powershell
python -m pytest -q
python -m pip wheel . --no-deps --wheel-dir dist
```

Las pruebas que interactúen con cámara, ratón o Registro de Windows deben usar
dobles de prueba; no deben modificar el equipo durante la suite automatizada.

## Pull requests

- Mantén cada cambio enfocado en un objetivo.
- Añade o actualiza pruebas cuando cambie el comportamiento.
- Actualiza `README.md` si cambia la instalación, los controles o la interfaz.
- No incluyas `.venv`, cachés, `build/`, `dist/` ni configuraciones personales.
