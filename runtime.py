"""Entrypoint guard: imports/tests remain usable; applications require a venv."""
from __future__ import annotations
import sys

def require_venv() -> None:
    if sys.prefix == sys.base_prefix:
        raise SystemExit(
            'Ejecuta instalar_windows.bat y despues iniciar_windows.bat.\n'
            'La aplicacion debe ejecutarse dentro de un entorno virtual, '
            'no con el Python global.')
