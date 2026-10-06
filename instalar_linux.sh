#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python3 -c 'import tkinter' || { echo 'Instala Tk para Python. Consulta README.md.'; exit 1; }
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c 'import obd; import serial; print("Dependencias listas.")'
echo 'Ejecuta: sh iniciar_linux.sh'
