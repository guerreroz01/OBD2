import csv
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import CSVRecorder, DemoBackend, DTCResult, Reading, RealBackend, SENSORS, Worker


class Response:
    def __init__(self, value, messages=None):
        self.value = value
        self.messages = messages or []
        self.explicit_messages = messages is not None

    def is_null(self):
        return self.value is None


class FakeConnection:
    def __init__(self, state='car'):
        self.state = state
        self.closed = False
        self.queries = []
        self.unsupported = set()
        self.replies = {}
        self.kwargs = None
        self.protocol = '6'
        self.forced = []

    def status(self):
        return self.state

    def supports(self, command):
        return command not in self.unsupported

    def protocol_id(self):
        return self.protocol

    def protocol_name(self):
        return 'SIMULATED PROTOCOL'

    def query(self, command, force=False):
        self.queries.append(command)
        self.forced.append(force)
        response = self.replies.get(command, Response(SimpleNamespace(magnitude=42.0)))
        if not response.explicit_messages:
            if command == 'PIDS_A':
                data = bytes.fromhex('41 00 FF FF FF FF')
            elif command in RealBackend.PID_LENGTHS:
                pid, length = RealBackend.PID_LENGTHS[command]
                data = bytes((0x41, pid)) + bytes(length - 2)
            elif command in ('GET_DTC', 'GET_CURRENT_DTC'):
                data = bytes((0x43 if command == 'GET_DTC' else 0x47, 0))
            elif command == 'CLEAR_DTC':
                data = b'\x44'
            else:
                data = b''
            response.messages = [SimpleNamespace(data=data)]
        return response

    def close(self):
        self.closed = True


def fake_module(connection):
    def factory(**kwargs):
        connection.kwargs = kwargs
        return connection
    names = [s.command for s in SENSORS] + ['GET_DTC', 'GET_CURRENT_DTC', 'PIDS_A', 'ELM_VERSION', 'CLEAR_DTC']
    return SimpleNamespace(
        OBD=factory,
        OBDStatus=SimpleNamespace(CAR_CONNECTED='car', ELM_CONNECTED='elm', OBD_CONNECTED='obd'),
        commands=SimpleNamespace(**{name: name for name in names}),
    )


class BackendTests(unittest.TestCase):
    def test_requires_explicit_port(self):
        with self.assertRaises(ValueError):
            RealBackend('   ')

    def test_compatibility_settings(self):
        connection = FakeConnection()
        backend = RealBackend('COM7', obd_module=fake_module(connection))
        backend.connect()
        self.assertFalse(connection.kwargs['fast'])
        self.assertTrue(connection.kwargs['check_voltage'])
        self.assertEqual(connection.kwargs['portstr'], 'COM7')
        self.assertEqual(len(backend.supported), 8)
        backend.close()
        self.assertTrue(connection.closed)

    def test_partial_connection_is_not_success(self):
        for state in ('elm', 'obd', 'none'):
            connection = FakeConnection(state)
            backend = RealBackend('COM7', obd_module=fake_module(connection))
            with self.assertRaises(ConnectionError):
                backend.connect()
            self.assertTrue(connection.closed)

    def test_ecu_without_dashboard_sensors_is_still_verified(self):
        connection = FakeConnection()
        connection.unsupported.update(s.command for s in SENSORS if s.command != 'ELM_VOLTAGE')
        backend = RealBackend('COM7', obd_module=fake_module(connection))
        self.assertIn('ECU verificada', backend.connect())
        self.assertEqual(backend.supported, {'ELM_VOLTAGE'})
        self.assertTrue(backend.heartbeat())


    def test_zero_rpm_is_valid_and_unsupported_not_queried(self):
        connection = FakeConnection()
        connection.unsupported.add('INTAKE_TEMP')
        connection.replies['RPM'] = Response(SimpleNamespace(magnitude=0))
        backend = RealBackend('COM7', obd_module=fake_module(connection))
        backend.connect()
        readings = {r.command: r for r in backend.read_sensors(threading.Event())}
        self.assertEqual(readings['RPM'].value, 0)
        self.assertEqual(readings['RPM'].status, 'OK')
        self.assertEqual(readings['INTAKE_TEMP'].status, 'No compatible')
        self.assertNotIn('INTAKE_TEMP', connection.queries)

    def test_invalid_and_null_sensor_values_are_not_zero(self):
        connection = FakeConnection()
        connection.replies['RPM'] = Response(None)
        connection.replies['SPEED'] = Response(SimpleNamespace(magnitude=float('nan')))
        backend = RealBackend('COM7', obd_module=fake_module(connection))
        backend.connect()
        readings = {r.command: r for r in backend.read_sensors(threading.Event())}
        self.assertIsNone(readings['RPM'].value)
        self.assertEqual(readings['RPM'].status, 'Sin respuesta')
        self.assertIsNone(readings['SPEED'].value)
        self.assertEqual(readings['SPEED'].status, 'Dato no interpretable')

    def test_empty_dtcs_differ_from_missing_response(self):
        connection = FakeConnection()
        connection.replies['GET_DTC'] = Response([])
        connection.replies['GET_CURRENT_DTC'] = Response(None)
        backend = RealBackend('COM7', obd_module=fake_module(connection))
        backend.connect()
        results = backend.read_dtcs(threading.Event())
        self.assertEqual(results[0].status, 'OK')
        self.assertEqual(results[0].codes, ())
        self.assertIn('Sin respuesta', results[1].status)
        self.assertNotIn('CLEAR_DTC', connection.queries)

    def test_dtc_codes_preserved(self):
        connection = FakeConnection()
        connection.replies['GET_DTC'] = Response([('P0300', 'Random misfire')])
        connection.replies['GET_CURRENT_DTC'] = Response([])
        backend = RealBackend('COM7', obd_module=fake_module(connection))
        backend.connect()
        self.assertEqual(backend.read_dtcs(threading.Event())[0].codes[0][0], 'P0300')

    def test_cancellation_does_not_query(self):
        connection = FakeConnection()
        backend = RealBackend('COM7', obd_module=fake_module(connection))
        backend.connect()
        connection.queries.clear()
        stop = threading.Event()
        stop.set()
        self.assertEqual(backend.read_sensors(stop), [])
        self.assertEqual(backend.read_dtcs(stop), [])
        self.assertEqual(connection.queries, [])

    def test_clear_requires_mode04_evidence(self):
        connection = FakeConnection()
        backend = RealBackend('COM7', obd_module=fake_module(connection))
        backend.connect()
        result = backend.clear_dtcs(threading.Event())
        self.assertTrue(result.confirmed)
        self.assertIn('CLEAR_DTC', connection.queries)

    def test_clear_without_44_is_not_confirmed(self):
        connection = FakeConnection()
        connection.replies['CLEAR_DTC'] = Response(None, [])
        backend = RealBackend('COM7', obd_module=fake_module(connection))
        backend.connect()
        self.assertFalse(backend.clear_dtcs(threading.Event()).confirmed)

    def test_clear_cancelled_does_not_query(self):
        connection = FakeConnection()
        backend = RealBackend('COM7', obd_module=fake_module(connection))
        backend.connect()
        connection.queries.clear()
        stop = threading.Event()
        stop.set()
        self.assertFalse(backend.clear_dtcs(stop).confirmed)
        self.assertEqual(connection.queries, [])

    def test_demo_clear_is_marked_and_clears_codes(self):
        backend = DemoBackend()
        self.assertIn('SIMULADO', backend.clear_dtcs(threading.Event()).status)
        self.assertEqual(backend.read_dtcs(threading.Event())[0].codes, ())

    def test_worker_clear_event(self):
        events = queue.Queue()
        worker = Worker(DemoBackend, events, interval=0.05)
        worker.actions.put('clear')
        worker.start()
        kinds = []
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            kind, _ = events.get(timeout=1)
            kinds.append(kind)
            if 'cleared' in kinds and 'dtcs' in kinds:
                break
        worker.stop()
        worker.join(timeout=2)
        self.assertIn('cleared', kinds)

    def test_demo_values_are_explicitly_marked(self):
        backend = DemoBackend()
        self.assertIn('DEMO', backend.connect())
        readings = backend.read_sensors(threading.Event())
        self.assertEqual(len(readings), 8)
        self.assertTrue(all(r.status == 'SIMULADO' for r in readings))
        self.assertTrue(all(r.status == 'SIMULADO' for r in backend.read_dtcs(threading.Event())))

    def test_csv_provenance_timestamp_missing_value_and_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.csv'
            recorder = CSVRecorder(path, True)
            recorder.write([Reading('RPM', 0, 'rpm', 'SIMULADO', 0),
                            Reading('SPEED', None, 'km/h', 'Sin respuesta', 0)])
            recorder.close()
            with path.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream, delimiter=';'))
            self.assertEqual(rows[0]['origen'], 'SIMULADO')
            self.assertEqual(rows[0]['valor'], '0')
            self.assertEqual(rows[1]['valor'], '')
            self.assertIn('+00:00', rows[0]['fecha_utc'])

    def test_worker_demo_lifecycle_and_dtc_request(self):
        events = queue.Queue()
        worker = Worker(DemoBackend, events, interval=0.05)
        worker.actions.put('dtcs')
        worker.start()
        kinds = set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            kind, payload = events.get(timeout=1)
            kinds.add(kind)
            if {'connected', 'dtcs', 'readings'} <= kinds:
                break
        worker.stop()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertTrue({'connected', 'dtcs', 'readings'} <= kinds)
        self.assertNotIn('error', kinds)
        self.assertIn('done', [item[0] for item in list(events.queue)])

    def test_worker_reports_connect_failure_and_closes(self):
        class Broken(DemoBackend):
            closed = False
            def connect(self):
                raise ConnectionError('Fake failure')
            def close(self):
                self.closed = True
        backend = Broken()
        events = queue.Queue()
        worker = Worker(lambda: backend, events)
        worker.start()
        worker.join(timeout=2)
        self.assertTrue(backend.closed)
        self.assertEqual([item[0] for item in events.queue], ['log', 'error', 'done'])

    def test_worker_detects_silent_loss(self):
        class Silent(DemoBackend):
            def read_sensors(self, stop):
                return [Reading('RPM', None, 'rpm', 'Sin respuesta', time.time()),
                        Reading('ELM_VOLTAGE', 12, 'V', 'OK', time.time())]
        events = queue.Queue()
        worker = Worker(Silent, events, interval=0.01)
        worker.start()
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertIn('error', [item[0] for item in events.queue])


if __name__ == '__main__':
    unittest.main()
