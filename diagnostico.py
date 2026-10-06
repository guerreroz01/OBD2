"""Windows-friendly diagnostic CLI. No ECU access unless --port is supplied."""
from __future__ import annotations
import argparse
import json
import logging
import platform
import sys
import threading
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from core import RealBackend, serial_ports
from protocols import PROTOCOLS
from runtime import require_venv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='Puerto explicitamente autorizado, por ejemplo COM7')
    parser.add_argument('--protocol', default='Auto', choices=['Auto'] + [p.id for p in PROTOCOLS if p.id])
    parser.add_argument('--baud', type=int, choices=[9600, 19200, 38400, 57600, 115200])
    parser.add_argument('--skip-voltage', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('diagnostico_obd.json'))
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()
    require_venv()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger('obd').setLevel(logging.DEBUG)
    report = {'python': sys.version, 'ejecutable': sys.executable,
              'sistema': platform.platform(), 'en_venv': sys.prefix != sys.base_prefix,
              'puertos_enumerados_sin_abrir': serial_ports(), 'dependencias': {}}
    for package in ('obd', 'pyserial'):
        try:
            report['dependencias'][package] = version(package)
        except PackageNotFoundError:
            report['dependencias'][package] = 'NO INSTALADO'
    exit_code = 0
    if args.port:
        backend = None
        try:
            backend = RealBackend(args.port, args.baud, not args.skip_voltage,
                                  protocol=args.protocol)
            backend.connect()
            report['conexion'] = dict(backend.report)
            report['lecturas'] = [asdict(r) for r in backend.read_sensors(threading.Event())]
        except Exception as exc:
            report['error'] = str(exc)
            if backend is not None:
                report['conexion'] = dict(backend.report)
            exit_code = 1
        finally:
            if backend is not None:
                try:
                    backend.close()
                except Exception as exc:
                    report['error_cierre'] = str(exc)
                    exit_code = 1
            if 'conexion' in report:
                report['conexion']['estado_sesion'] = 'HISTORICO: prueba terminada y puerto cerrado'
    else:
        report['nota'] = 'Solo entorno y enumeracion: no se ha abierto ningun puerto ni verificado una ECU.'
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    try:
        args.output.write_text(text + '\n', encoding='utf-8')
    except OSError as exc:
        print(f'No se pudo guardar {args.output}: {exc}', file=sys.stderr)
        return 2
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
