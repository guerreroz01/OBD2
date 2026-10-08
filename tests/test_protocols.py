import queue
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core import RealBackend, Worker
from protocols import PROTOCOLS, normalize_protocol, pid_evidence, valid_payloads, clear_dtc_evidence
from runtime import require_venv
from test_core import FakeConnection, Response, fake_module


def reply(hex_data, value=True):
    return Response(value, [SimpleNamespace(data=bytes.fromhex(hex_data))])


class ProtocolTests(unittest.TestCase):
    def test_catalogue_complete_and_unique(self):
        self.assertEqual([p.id for p in PROTOCOLS], [None] + list('123456789'))

    def test_automatic_normalization(self):
        for value in (None, '', '0', 'auto', ' AUTO '):
            self.assertIsNone(normalize_protocol(value))

    def test_invalid_protocols_rejected_before_connection(self):
        for value in ('A', 'B', 'C', '6;04', 'ATSP6', 'CAN', '10', '6\r04'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RealBackend('COM7', protocol=value)

    def test_manual_ids_passed_to_library(self):
        for value in '123456789':
            connection = FakeConnection()
            connection.protocol = value
            backend = RealBackend('COM7', protocol=value, obd_module=fake_module(connection))
            backend.connect()
            self.assertEqual(connection.kwargs['protocol'], value)
            self.assertEqual(backend.report['protocolo_id'], value)
            backend.close()

    def test_auto_passes_none_not_zero(self):
        c = FakeConnection()
        RealBackend('COM7', protocol='0', obd_module=fake_module(c)).connect()
        self.assertIsNone(c.kwargs['protocol'])

    def test_requested_and_effective_mismatch_rejected(self):
        c = FakeConnection()
        with self.assertRaises(ConnectionError):
            RealBackend('COM7', protocol='3', obd_module=fake_module(c)).connect()
        self.assertTrue(c.closed)

    def test_unimplemented_effective_protocol_rejected(self):
        c = FakeConnection()
        c.protocol = 'A'
        with self.assertRaises(ConnectionError):
            RealBackend('COM7', obd_module=fake_module(c)).connect()

    def test_bit_order_and_bitmap_union(self):
        r = Response(True, [SimpleNamespace(data=bytes.fromhex(x)) for x in
                           ('41 00 80 00 00 01', '41 00 00 10 00 00')])
        payloads, pids = pid_evidence(r)
        self.assertEqual(pids, ('01', '0C', '20'))
        self.assertEqual(len(payloads), 2)

    def test_zero_bitmap_is_still_a_response(self):
        _, pids = pid_evidence(reply('41 00 00 00 00 00'))
        self.assertEqual(pids, ())

    def test_echo_wrong_mode_pid_and_lengths_rejected(self):
        for data in ('01 00', '42 00 FF FF FF FF', '41 20 FF FF FF FF',
                     '41 00 FF FF FF', '41 00 FF FF FF FF 00', '7F 01 11'):
            with self.subTest(data=data), self.assertRaises(ConnectionError):
                pid_evidence(reply(data))

    def test_at_text_and_no_messages_are_not_evidence(self):
        for raw in ('OK', 'NO DATA', 'UNABLE TO CONNECT', 'CAN ERROR', '12.6V', 'ELM327 v2.1'):
            r = Response(True, [SimpleNamespace(data=b'', raw=raw)])
            with self.subTest(raw=raw), self.assertRaises(ConnectionError):
                pid_evidence(r)
        with self.assertRaises(ConnectionError):
            pid_evidence(Response(True, []))

    def test_decoded_value_without_bytes_rejected(self):
        with self.assertRaises(ConnectionError):
            pid_evidence(Response(SimpleNamespace(magnitude=1), []))

    def test_null_response_rejected_even_with_valid_bytes(self):
        with self.assertRaises(ConnectionError):
            pid_evidence(reply('41 00 FF FF FF FF', None))

    def test_malformed_payload_type_is_rejected(self):
        for data in (6, '4100FFFFFFFF', None, [-1, 0, 0, 0, 0, 0], [999]):
            self.assertEqual(valid_payloads(Response(True, [SimpleNamespace(data=data)]), b'\x41'), ())

    def test_static_car_connected_is_insufficient(self):
        c = FakeConnection()
        c.replies['PIDS_A'] = Response(None)
        reports = []
        backend = RealBackend('COM7', obd_module=fake_module(c), report_callback=reports.append)
        with self.assertRaises(ConnectionError):
            backend.connect()
        self.assertTrue(c.closed)
        self.assertIn('AT', reports[-1]['serie'])
        self.assertEqual(reports[-1]['ecu'], 'No verificada')
        self.assertEqual(reports[-1]['verificado_utc'], '')

    def test_forced_query_only_for_pid_discovery(self):
        c = FakeConnection()
        b = RealBackend('COM7', obd_module=fake_module(c))
        b.connect()
        b.read_sensors(threading.Event())
        self.assertEqual([name for name, force in zip(c.queries, c.forced) if force], ['PIDS_A'])

    def test_only_mode04_write_allowed(self):
        c = FakeConnection()
        b = RealBackend('COM7', obd_module=fake_module(c))
        b.connect()
        self.assertIn('CLEAR_DTC', RealBackend.ALLOWED_QUERIES)
        for command in ('08', 'ATSH7E0', 'CUSTOM', '04'):
            with self.assertRaises(ValueError):
                b._query(command)
        self.assertEqual(c.queries, ['PIDS_A'])

    def test_clear_evidence_requires_44(self):
        self.assertTrue(clear_dtc_evidence(Response(True, [SimpleNamespace(data=b'\x44')])).confirmed)
        self.assertFalse(clear_dtc_evidence(Response(None, [])).confirmed)
        verdict = clear_dtc_evidence(Response(True, [SimpleNamespace(data=bytes.fromhex('7F 04 11'))]))
        self.assertFalse(verdict.confirmed)
        self.assertIn('7F', verdict.status)

    def test_clear_evidence_drop_decoder_is_null_yet_confirms(self):
        r = Response(None, [SimpleNamespace(data=b'\x44')])
        self.assertTrue(r.is_null())  # drop decoder => value None
        self.assertTrue(clear_dtc_evidence(r).confirmed)

    def test_wrong_sensor_response_not_displayed(self):
        c = FakeConnection()
        c.replies['RPM'] = reply('41 0D 10 00', SimpleNamespace(magnitude=1000))
        b = RealBackend('COM7', obd_module=fake_module(c))
        b.connect()
        rpm = next(r for r in b.read_sensors(threading.Event()) if r.command == 'RPM')
        self.assertIsNone(rpm.value)

    def test_wrong_dtc_service_not_a_clean_bill(self):
        c = FakeConnection()
        c.replies['GET_DTC'] = reply('47 00', [])
        b = RealBackend('COM7', obd_module=fake_module(c))
        b.connect()
        self.assertNotEqual(b.read_dtcs(threading.Event())[0].status, 'OK')

    def test_truncated_dtc_reply_not_reported_as_zero_codes(self):
        for data in ('43', '43 01', '43 01 03'):
            c = FakeConnection()
            c.replies['GET_DTC'] = reply(data, [])
            b = RealBackend('COM7', obd_module=fake_module(c))
            b.connect()
            self.assertNotEqual(b.read_dtcs(threading.Event())[0].status, 'OK')

    def test_sensor_value_must_match_first_message(self):
        c = FakeConnection()
        c.replies['RPM'] = Response(SimpleNamespace(magnitude=1000), [
            SimpleNamespace(data=bytes.fromhex('41 0D 10 00')),
            SimpleNamespace(data=bytes.fromhex('41 0C 00 00'))])
        b = RealBackend('COM7', obd_module=fake_module(c))
        b.connect()
        rpm = next(r for r in b.read_sensors(threading.Event()) if r.command == 'RPM')
        self.assertIsNone(rpm.value)

    def test_voltage_bypass_does_not_bypass_ecu_validation(self):
        c = FakeConnection()
        c.replies['PIDS_A'] = Response(None)
        b = RealBackend('COM7', check_voltage=False, obd_module=fake_module(c))
        with self.assertRaises(ConnectionError):
            b.connect()
        self.assertFalse(c.kwargs['check_voltage'])

    def test_heartbeat_uses_fresh_data_not_static_status(self):
        c = FakeConnection()
        b = RealBackend('COM7', obd_module=fake_module(c))
        b.connect()
        c.replies['PIDS_A'] = Response(None)
        self.assertEqual(c.status(), 'car')
        self.assertFalse(b.heartbeat())

    def test_runtime_rejects_global_python(self):
        with patch('runtime.sys.prefix', '/global'), patch('runtime.sys.base_prefix', '/global'):
            with self.assertRaises(SystemExit):
                require_venv()

    def test_runtime_accepts_actual_venv(self):
        with patch('runtime.sys.prefix', '/local/.venv'), patch('runtime.sys.base_prefix', '/global'):
            require_venv()

    def test_bad_ecu_never_emits_connected(self):
        c = FakeConnection()
        c.replies['PIDS_A'] = Response(None)
        events = queue.Queue()
        w = Worker(lambda: RealBackend('COM7', obd_module=fake_module(c)), events)
        w.start()
        w.join(2)
        self.assertNotIn('connected', [k for k, _ in events.queue])
        self.assertIn('error', [k for k, _ in events.queue])


if __name__ == '__main__':
    unittest.main()
