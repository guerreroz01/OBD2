"""Run GUI checks with a display; on headless Linux: xvfb-run -a python -m unittest discover -s tests."""
import time
import unittest
from unittest.mock import patch
import tkinter as tk

from app import App


class GUITests(unittest.TestCase):
    def setUp(self):
        try:
            self.app = App(demo=True)
        except tk.TclError as exc:
            self.skipTest(f'No graphical display: {exc}')

    def tearDown(self):
        if hasattr(self, 'app'):
            worker = self.app.worker
            if worker:
                worker.stop()
                worker.join(timeout=3)
            try:
                self.app.update()
                self.app.on_close()
                self.app.update()
            except tk.TclError:
                pass

    def until(self, condition, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            if condition():
                return
            time.sleep(0.02)
        self.fail('GUI condition timed out')

    def test_demo_connect_dtcs_disconnect(self):
        self.until(lambda: self.app.active and 'SIMULADO' in self.app.sensors.item('RPM', 'values'))
        self.assertIn('DEMO', self.app.banner.get())
        self.app.request_dtcs()
        self.until(lambda: len(self.app.dtc_table.get_children()) == 2)
        self.assertFalse(self.app.dtc_pending)
        self.app.disconnect()
        self.until(lambda: self.app.worker is None)
        self.assertFalse(self.app.active)
        self.assertEqual(self.app.sensors.item('RPM', 'values')[2], 'Desconectado')
        self.assertIn('HIST', self.app.dtc_status.get())

    def test_protocol_selector_and_demo_report(self):
        self.until(lambda: self.app.active and bool(self.app.last_report))
        self.assertEqual(len(self.app.protocol_box['values']), 10)
        self.assertEqual(self.app.last_report['origen'], 'SIMULADO')
        self.assertNotIn('Verificada', self.app.last_report['ecu'])
        self.assertEqual(str(self.app.protocol_box['state']), 'disabled')

    def test_no_live_verification_after_disconnect(self):
        self.until(lambda: self.app.active)
        self.app.disconnect()
        self.until(lambda: self.app.worker is None)
        self.assertIn('HISTORICO', self.app.last_report['estado_sesion'])
        self.assertEqual(str(self.app.protocol_box['state']), 'readonly')


if __name__ == '__main__':
    unittest.main()
