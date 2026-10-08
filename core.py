"""OBD Desk: single-owner ELM327 backend for reads plus an explicit, confirmed mode 04 clear. Python >= 3.10."""
from __future__ import annotations

import csv
import glob
import math
import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from protocols import (PROTOCOL_IDS, normalize_protocol, pid_evidence, valid_payloads,
                       clear_dtc_evidence, ClearVerdict)


@dataclass(frozen=True)
class Sensor:
    command: str
    label: str
    unit: str
    decimals: int = 1


SENSORS = (
    Sensor('RPM', 'R\u00e9gimen del motor', 'rpm', 0),
    Sensor('SPEED', 'Velocidad', 'km/h', 0),
    Sensor('COOLANT_TEMP', 'Temperatura del refrigerante', '\u00b0C'),
    Sensor('INTAKE_TEMP', 'Temperatura del aire de admisi\u00f3n', '\u00b0C'),
    Sensor('ENGINE_LOAD', 'Carga calculada del motor', '%'),
    Sensor('THROTTLE_POS', 'Posici\u00f3n de la mariposa', '%'),
    Sensor('INTAKE_PRESSURE', 'Presi\u00f3n absoluta de admisi\u00f3n', 'kPa'),
    Sensor('ELM_VOLTAGE', 'Tensi\u00f3n le\u00edda por el adaptador', 'V', 2),
)

# Diagnostic reads exposed to the panel. Mode 04 (clear) is a separate, confirmed action.
DTC_COMMANDS = (
    ('GET_DTC', 'Almacenados (modo 03)'),
    ('GET_CURRENT_DTC', 'Pendientes (modo 07)'),
)


@dataclass(frozen=True)
class Reading:
    command: str
    value: float | None
    unit: str
    status: str
    timestamp: float


@dataclass(frozen=True)
class DTCResult:
    category: str
    status: str
    codes: tuple[tuple[str, str], ...]


def serial_ports() -> list[str]:
    """Enumerate ports only; never open or probe an unrelated serial device."""
    found = set(glob.glob('/dev/rfcomm*'))
    try:
        from serial.tools import list_ports
        found.update(p.device for p in list_ports.comports())
    except ImportError:
        pass
    return sorted(found)


class RealBackend:
    """One worker owns this object and the COM port. Reads and one explicit mode 04 clear; no other writes."""
    demo = False
    PID_LENGTHS = {
        'RPM': (0x0C, 4), 'SPEED': (0x0D, 3), 'COOLANT_TEMP': (0x05, 3),
        'INTAKE_TEMP': (0x0F, 3), 'ENGINE_LOAD': (0x04, 3),
        'THROTTLE_POS': (0x11, 3), 'INTAKE_PRESSURE': (0x0B, 3),
    }
    ALLOWED_QUERIES = frozenset({s.command for s in SENSORS} |
                              {name for name, _ in DTC_COMMANDS} |
                              {'PIDS_A', 'ELM_VERSION', 'CLEAR_DTC'})

    def __init__(self, port: str, baudrate: int | None = None,
                 check_voltage: bool = True, obd_module=None,
                 protocol: str | None = None, report_callback: Callable | None = None):
        if not port.strip():
            raise ValueError('Selecciona el puerto del lector; no se exploran puertos automaticamente.')
        self.port, self.baudrate = port.strip(), baudrate
        self.check_voltage = check_voltage
        self.protocol = normalize_protocol(protocol)
        self.obd = obd_module
        self.connection = None
        self.supported: set[str] = set()
        self.report_callback = report_callback
        self.report = {
            'origen': 'VEHICULO', 'puerto': self.port,
            'protocolo_solicitado': self.protocol or 'Auto',
            'serie': 'No verificado', 'adaptador': 'No verificado',
            'ecu': 'No verificada', 'protocolo_id': '', 'protocolo_nombre': '',
            'identificacion_declarada': '', 'verificado_utc': '',
            'respuestas_0100': [], 'pids_01_20_anunciados': [],
        }

    def publish_report(self) -> None:
        if self.report_callback:
            # Lists are replaced, never mutated, after publication.
            self.report_callback(dict(self.report))

    def _query(self, name: str):
        if name not in self.ALLOWED_QUERIES:
            raise ValueError('Comando fuera de la lista de consultas permitidas.')
        if self.connection is None:
            raise ConnectionError('No hay una sesion abierta.')
        command = getattr(self.obd.commands, name)
        # Only the mandatory PID discovery read may bypass supports().
        if name == 'PIDS_A':
            return self.connection.query(command, force=True)
        return self.connection.query(command)

    def connect(self) -> str:
        if self.connection is not None:
            raise RuntimeError('Cierra la sesion anterior antes de conectar.')
        self.supported.clear()
        self.report.pop('error', None)
        self.report.update(serie='No verificado', adaptador='No verificado',
                           ecu='No verificada', verificado_utc='', respuestas_0100=[],
                           pids_01_20_anunciados=[], protocolo_id='', protocolo_nombre='',
                           identificacion_declarada='')
        self.publish_report()
        if self.obd is None:
            try:
                import obd
            except ImportError as exc:
                raise RuntimeError('Faltan dependencias. Ejecuta instalar_windows.bat dentro de la carpeta del proyecto.') from exc
            self.obd = obd
        try:
            # python-OBD performs ELM setup, protocol negotiation and PID discovery.
            # fast=False avoids response-count suffixes and repeat-CR shortcuts.
            self.connection = self.obd.OBD(
                portstr=self.port, baudrate=self.baudrate, protocol=self.protocol,
                fast=False, timeout=2.0, check_voltage=self.check_voltage,
            )
            state = self.connection.status()
            self.report['estado_inicial_biblioteca'] = str(state)
            if state in (self.obd.OBDStatus.ELM_CONNECTED,
                         self.obd.OBDStatus.OBD_CONNECTED,
                         self.obd.OBDStatus.CAR_CONNECTED):
                self.report['serie'] = 'Verificado mediante respuestas AT'
                self.report['adaptador'] = 'Responde a la inicializacion AT'
            self.publish_report()
            if state != self.obd.OBDStatus.CAR_CONNECTED:
                if state == self.obd.OBDStatus.ELM_CONNECTED:
                    reason = 'El ELM responde, pero no se ha verificado la ECU.'
                elif state == self.obd.OBDStatus.OBD_CONNECTED:
                    reason = 'El adaptador informa tension, pero no se ha verificado la ECU.'
                else:
                    reason = 'No se ha verificado la comunicacion serie con el ELM327.'
                raise ConnectionError(reason + ' Revisa contacto, protocolo, puerto saliente y otras apps abiertas; consulta Registro.')
            protocol_id = str(self.connection.protocol_id()).upper()
            if protocol_id not in PROTOCOL_IDS:
                raise ConnectionError('El protocolo obtenido no esta admitido por esta app (solo OBD-II 1 a 9).')
            if self.protocol is not None and protocol_id != self.protocol:
                raise ConnectionError('El protocolo obtenido no coincide con el solicitado.')
            self.report['protocolo_id'] = protocol_id
            self.report['protocolo_nombre'] = self.connection.protocol_name()
            # A fresh query is required even if the library says CAR_CONNECTED.
            response = self._query('PIDS_A')
            payloads, pids = pid_evidence(response)
            self.report['ecu'] = 'Verificada por respuesta OBD 41 00'
            self.report['verificado_utc'] = datetime.now(timezone.utc).isoformat()
            self.report['respuestas_0100'] = list(payloads)
            self.report['pids_01_20_anunciados'] = list(pids)
            for sensor in SENSORS:
                if self.connection.supports(getattr(self.obd.commands, sensor.command)):
                    self.supported.add(sensor.command)
            # No sensor in this particular panel is mandatory. 0100 is evidence
            # even for an ECU exposing none of the dashboard's selected PIDs.
            self.publish_report()
            return (f'ECU verificada | {self.port} | '
                    f'{protocol_id}: {self.connection.protocol_name()} | '
                    f'{len(self.supported - {"ELM_VOLTAGE"})} parametros ECU del panel')
        except Exception as exc:
            self.report['ecu'] = 'No verificada'
            self.report['error'] = str(exc)
            self.publish_report()
            self.close()
            raise

    def heartbeat(self) -> bool:
        """Never use static connection.status() or ELM voltage as live evidence."""
        try:
            pid_evidence(self._query('PIDS_A'))
            return True
        except ConnectionError:
            return False

    def read_sensors(self, stop: threading.Event) -> list[Reading]:
        readings = []
        for sensor in SENSORS:
            if stop.is_set():
                break
            if sensor.command not in self.supported:
                readings.append(Reading(sensor.command, None, sensor.unit, 'No compatible', time.time()))
                continue
            response = self._query(sensor.command)
            value, status = None, 'Sin respuesta'
            if not response.is_null():
                valid = True
                if sensor.command in self.PID_LENGTHS:
                    pid, length = self.PID_LENGTHS[sensor.command]
                    matches = valid_payloads(response, bytes((0x41, pid)), length)
                    first = getattr(response.messages[0], 'data', None) if response.messages else None
                    valid = bool(matches) and first == matches[0]
                if not valid:
                    status = 'Respuesta no valida para este PID'
                else:
                    try:
                        value = float(response.value.magnitude)
                        if not math.isfinite(value):
                            raise ValueError('non-finite sensor value')
                        status = 'OK (adaptador)' if sensor.command == 'ELM_VOLTAGE' else 'OK'
                    except (AttributeError, TypeError, ValueError):
                        value, status = None, 'Dato no interpretable'
            readings.append(Reading(sensor.command, value, sensor.unit, status, time.time()))
        return readings

    def read_dtcs(self, stop: threading.Event) -> list[DTCResult]:
        results = []
        for name, category in DTC_COMMANDS:
            if stop.is_set():
                break
            command = getattr(self.obd.commands, name)
            if not self.connection.supports(command):
                results.append(DTCResult(category, 'No compatible', ()))
                continue
            response = self._query(name)
            prefix = b'\x43' if name == 'GET_DTC' else b'\x47'
            payloads = valid_payloads(response, prefix)
            if response.is_null():
                results.append(DTCResult(category, 'Sin respuesta; no permite descartar fallos', ()))
            elif not payloads or any(len(data) < 2 or len(data) < 2 + 2 * data[1]
                                     for data in payloads):
                results.append(DTCResult(category, 'Sin respuesta OBD valida para esta categoria', ()))
            elif isinstance(response.value, (list, tuple)):
                try:
                    codes = tuple((str(code), str(desc or 'Sin descripcion disponible'))
                                  for code, desc in response.value)
                except (ValueError, TypeError):
                    results.append(DTCResult(category, 'Respuesta no interpretable', ()))
                else:
                    results.append(DTCResult(category, 'OK', codes))
            else:
                results.append(DTCResult(category, 'Respuesta no interpretable', ()))
        return results

    def clear_dtcs(self, stop: threading.Event) -> ClearVerdict:
        """Mode 04. python-OBD always reports CLEAR_DTC as supported, so a fresh
        OBD 44 payload is the only accepted proof; the ELM OK is not."""
        if stop.is_set():
            return ClearVerdict(False, 'Cancelado', 'No se envio la orden de borrado.')
        return clear_dtc_evidence(self._query('CLEAR_DTC'))

    def close(self) -> None:
        if self.connection is not None:
            connection, self.connection = self.connection, None
            connection.close()


class DemoBackend:
    """Synthetic values. Does not import obd, open a port, or contact a vehicle."""
    demo = True

    def __init__(self):
        self.start = time.monotonic()
        self.supported = {s.command for s in SENSORS}
        self.stored_cleared = False
        self.report = {'origen': 'SIMULADO', 'serie': 'NO ABIERTA (demo)',
                       'adaptador': 'NO UTILIZADO (demo)', 'ecu': 'SIMULADA, no verificada'}

    def connect(self) -> str:
        return 'DEMO: datos simulados; no hay conexi\u00f3n con un veh\u00edculo'

    def read_sensors(self, stop: threading.Event) -> list[Reading]:
        t = time.monotonic() - self.start
        values = [840 + 35 * math.sin(t), 0, 87 + math.sin(t / 5),
                  27 + math.sin(t / 7), 18 + 2 * math.sin(t / 2),
                  13 + math.sin(t / 3), 32 + math.sin(t), 14.1 + 0.04 * math.sin(t)]
        return [Reading(s.command, value, s.unit, 'SIMULADO', time.time())
                for s, value in zip(SENSORS, values) if not stop.is_set()]

    def read_dtcs(self, stop: threading.Event) -> list[DTCResult]:
        if stop.is_set():
            return []
        stored = () if self.stored_cleared else (
            ('P0300', 'EJEMPLO SIMULADO: fallos de encendido aleatorios / m\u00faltiples'),)
        return [DTCResult('Almacenados (modo 03)', 'SIMULADO', stored),
                DTCResult('Pendientes (modo 07)', 'SIMULADO', ())]

    def clear_dtcs(self, stop: threading.Event) -> ClearVerdict:
        if stop.is_set():
            return ClearVerdict(False, 'Cancelado', 'SIMULADO: no se envio ninguna orden.')
        self.stored_cleared = True
        return ClearVerdict(True, 'SIMULADO: 44', 'SIMULADO: la ECU ficticia acepto el borrado (modo 04).')

    def close(self) -> None:
        pass


class QueueLogHandler(logging.Handler):
    """Bridge library diagnostics to the GUI queue, never to Tk from a worker."""
    def __init__(self, events):
        super().__init__(logging.DEBUG)
        self.events = events

    def emit(self, record):
        self.events.put(('log', f'{record.levelname} {record.name}: {record.getMessage()}'))


class Worker(threading.Thread):
    """One serial owner; the GUI communicates exclusively through queues."""

    def __init__(self, factory: Callable, events: queue.Queue, interval: float = 1.0):
        super().__init__(daemon=True, name='obd-reader')
        self.factory, self.events, self.interval = factory, events, interval
        self.actions: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        backend = None
        logger = logging.getLogger('obd')
        old_level = logger.level
        handler = QueueLogHandler(self.events)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        try:
            backend = self.factory()
            self.events.put(('log', 'Iniciando enlace y detecci\u00f3n del protocolo...'))
            info = backend.connect()
            if self.stop_event.is_set():
                return
            if hasattr(backend, 'report'):
                self.events.put(('report', dict(backend.report)))
            self.events.put(('connected', (info, backend.demo)))
            next_poll, missed = 0.0, 0
            while not self.stop_event.is_set():
                try:
                    action = self.actions.get_nowait()
                except queue.Empty:
                    action = None
                if action == 'dtcs':
                    result = backend.read_dtcs(self.stop_event)
                    if not self.stop_event.is_set():
                        self.events.put(('dtcs', result))
                if action == 'clear':
                    result = backend.clear_dtcs(self.stop_event)
                    if not self.stop_event.is_set():
                        self.events.put(('dtcs', backend.read_dtcs(self.stop_event)))
                        self.events.put(('cleared', result))
                if self.stop_event.is_set():
                    break
                if time.monotonic() >= next_poll:
                    readings = backend.read_sensors(self.stop_event)
                    if self.stop_event.is_set():
                        break
                    self.events.put(('readings', readings))
                    valid_car_data = any(r.command != 'ELM_VOLTAGE' and r.value is not None for r in readings)
                    if not valid_car_data and hasattr(backend, 'heartbeat'):
                        valid_car_data = backend.heartbeat()
                    missed = 0 if valid_car_data else missed + 1
                    self.events.put(('health', (valid_car_data, missed)))
                    if missed >= 3:
                        raise ConnectionError('Tres ciclos sin datos v\u00e1lidos del veh\u00edculo. Comprueba el contacto y vuelve a conectar.')
                    # Wait after a full batch; actual rate depends on ELM/car latency.
                    next_poll = time.monotonic() + self.interval
                self.stop_event.wait(0.1)
        except Exception as exc:
            if not self.stop_event.is_set():
                self.events.put(('error', str(exc)))
        finally:
            if backend is not None:
                try:
                    backend.close()
                except Exception as exc:
                    self.events.put(('log', f'Error al cerrar el puerto: {exc}'))
            logger.removeHandler(handler)
            logger.setLevel(old_level)
            self.events.put(('done', None))


class CSVRecorder:
    """Long-format CSV with individual timestamps, units, and demo provenance."""
    def __init__(self, path: str | Path, demo: bool):
        self.file = Path(path).open('w', encoding='utf-8-sig', newline='')
        self.writer = csv.writer(self.file, delimiter=';')
        self.source = 'SIMULADO' if demo else 'VEHICULO'
        try:
            self.writer.writerow(['fecha_utc', 'origen', 'sensor', 'valor', 'unidad', 'estado'])
            self.file.flush()
        except Exception:
            self.file.close()
            raise

    def write(self, readings: list[Reading]) -> None:
        for reading in readings:
            stamp = datetime.fromtimestamp(reading.timestamp, timezone.utc).isoformat(timespec='milliseconds')
            value = '' if reading.value is None else format(reading.value, '.8g')
            self.writer.writerow([stamp, self.source, reading.command, value, reading.unit, reading.status])
        self.file.flush()

    def close(self) -> None:
        self.file.close()
