"""Replay against installed python-OBD, never serial hardware.

Skipped explicitly if obd cannot be installed in the test environment.
"""
import unittest
from protocols import pid_evidence
try:
    import obd
except ModuleNotFoundError as exc:
    if exc.name != 'obd':
        raise
    obd = None
else:
    from obd.protocols import ISO_15765_4_11bit_500k, ISO_15765_4_29bit_500k


@unittest.skipIf(obd is None, 'obd no instalado: no se ha ejecutado el parser real de la dependencia')
class LibraryContractTests(unittest.TestCase):
    def test_can11_pid_discovery(self):
        lines = ['7E8 06 41 00 BE 3E B8 13 00']
        parser = ISO_15765_4_11bit_500k(lines)
        response = obd.commands.PIDS_A(parser(lines))
        payloads, pids = pid_evidence(response)
        self.assertEqual(payloads, ('41 00 BE 3E B8 13',))
        self.assertIn('0C', pids)

    def test_can29_pid_discovery(self):
        lines = ['18DAF110 06 41 00 BE 3E B8 13 00']
        parser = ISO_15765_4_29bit_500k(lines)
        response = obd.commands.PIDS_A(parser(lines))
        payloads, _ = pid_evidence(response)
        self.assertEqual(payloads, ('41 00 BE 3E B8 13',))

    def test_no_data_not_ecu_evidence(self):
        parser = ISO_15765_4_11bit_500k(['7E8 06 41 00 BE 3E B8 13 00'])
        response = obd.commands.PIDS_A(parser(['NO DATA']))
        with self.assertRaises(ConnectionError):
            pid_evidence(response)
