#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
  echo 'Ejecuta primero: sh instalar_linux.sh'
  exit 1
fi
exec .venv/bin/python app.py "$@"
