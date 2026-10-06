"""OBD Desk -- local, read-only desktop GUI for Bluetooth SPP ELM327 adapters."""
from __future__ import annotations

import argparse
import json
import queue
import tkinter as tk
from collections import deque
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, ttk

from core import CSVRecorder, DemoBackend, RealBackend, SENSORS, Worker, serial_ports
from protocols import PROTOCOLS
from runtime import require_venv


class App(tk.Tk):
    def __init__(self, demo: bool = False):
        super().__init__()
        self.title('OBD Desk 0.2 | Windows | ELM327')
        self.geometry('1100x800')
        self.minsize(960, 740)
        self.events: queue.Queue = queue.Queue()
        self.worker: Worker | None = None
        self.recorder: CSVRecorder | None = None
        self.active = False
        self.session_demo = False
        self.dtc_pending = False
        self.log_lines = deque(maxlen=1000)
        self.port = tk.StringVar()
        self.baud = tk.StringVar(value='Auto')
        self.protocol_choice = tk.StringVar(value=PROTOCOLS[0].label)
        self.last_report = {}
        self.connection_info = ''
        self.closing = False
        self.demo = tk.BooleanVar(value=demo)
        self.skip_voltage = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Sin conexi\u00f3n')
        self.banner = tk.StringVar(value='SOLO LECTURA  |  No borra fallos ni modifica la centralita')
        self.dtc_status = tk.StringVar(value='Todav\u00eda no se han consultado los fallos.')
        self._styles()
        self._build()
        self.refresh_ports()
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self._pump_id = self.after(100, self.pump)
        if demo:
            self._demo_after_id = self.after(200, self.connect)

    def _styles(self):
        self.configure(background='#eef2f6')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10))
        style.configure('TFrame', background='#eef2f6')
        style.configure('TLabel', background='#eef2f6', foreground='#17263c')
        style.configure('Title.TLabel', font=('Segoe UI', 24, 'bold'))
        style.configure('Sub.TLabel', foreground='#52627a')
        style.configure('Banner.TLabel', background='#fff0d2', foreground='#6c4700', padding=10)
        style.configure('TButton', padding=(12, 7))
        style.configure('TCheckbutton', background='#eef2f6')
        style.configure('Treeview', rowheight=30, font=('Segoe UI', 10), background='#ffffff', fieldbackground='#ffffff')
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'), padding=8)
        style.configure('TNotebook.Tab', padding=(18, 10))

    def _build(self):
        body = ttk.Frame(self, padding=22)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='OBD Desk', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='ELM327 / IM77R  \u00b7  Bluetooth cl\u00e1sico  \u00b7  Diagn\u00f3stico local', style='Sub.TLabel').pack(anchor='w', pady=(0, 16))
        ttk.Label(body, textvariable=self.banner, style='Banner.TLabel').pack(fill='x', pady=(0, 12))

        row = ttk.Frame(body)
        row.pack(fill='x')
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text='Puerto:').grid(row=0, column=0, padx=(0, 7))
        self.port_box = ttk.Combobox(row, textvariable=self.port, width=20)
        self.port_box.grid(row=0, column=1, sticky='ew')
        self.refresh_button = ttk.Button(row, text='Actualizar', command=self.refresh_ports)
        self.refresh_button.grid(row=0, column=2, padx=8)
        ttk.Label(row, text='Baudios:').grid(row=0, column=3, padx=(8, 7))
        self.baud_box = ttk.Combobox(row, textvariable=self.baud, state='readonly', width=9,
                                    values=['Auto', '38400', '9600', '115200', '57600', '19200'])
        self.baud_box.grid(row=0, column=4)
        self.connect_button = ttk.Button(row, text='Conectar', command=self.connect)
        self.connect_button.grid(row=0, column=5, padx=(12, 8))
        self.disconnect_button = ttk.Button(row, text='Desconectar', command=self.disconnect, state='disabled')
        self.disconnect_button.grid(row=0, column=6)

        protocol_row = ttk.Frame(body)
        protocol_row.pack(fill='x', pady=(10, 0))
        ttk.Label(protocol_row, text='Protocolo del vehiculo:').pack(side='left', padx=(0, 8))
        self.protocol_box = ttk.Combobox(protocol_row, textvariable=self.protocol_choice,
                                        values=[p.label for p in PROTOCOLS], state='readonly', width=57)
        self.protocol_box.pack(side='left', fill='x', expand=True)
        ttk.Label(protocol_row, text='No es la velocidad del COM', style='Sub.TLabel').pack(side='left', padx=10)

        options = ttk.Frame(body)
        options.pack(fill='x', pady=(8, 6))
        self.demo_check = ttk.Checkbutton(options, text='Demostraci\u00f3n sin coche', variable=self.demo)
        self.demo_check.pack(side='left')
        self.voltage_check = ttk.Checkbutton(options, text='Omitir comprobaci\u00f3n de tensi\u00f3n (solo si falla)', variable=self.skip_voltage)
        self.voltage_check.pack(side='left', padx=20)
        ttk.Label(body, textvariable=self.status, wraplength=970, style='Sub.TLabel').pack(fill='x', pady=(2, 10))

        self.tabs = ttk.Notebook(body)
        self.tabs.pack(fill='both', expand=True)
        live = ttk.Frame(self.tabs, padding=12)
        dtcs = ttk.Frame(self.tabs, padding=12)
        logs = ttk.Frame(self.tabs, padding=12)
        verification = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(live, text='Datos en directo')
        self.tabs.add(dtcs, text='C\u00f3digos de fallo')
        self.tabs.add(verification, text='Verificacion ECU')
        self.tabs.add(logs, text='Registro')
        ttk.Label(verification, text='COM / Bluetooth != ELM327 != ECU. La prueba es una respuesta OBD valida.',
                  wraplength=920, style='Sub.TLabel').pack(anchor='w', pady=(0, 10))
        self.report_text = tk.Text(verification, wrap='word', state='disabled', height=10,
                                   font=('Consolas', 10), padx=12, pady=12)
        self.report_text.pack(fill='both', expand=True)
        ttk.Button(verification, text='Guardar informe de verificacion (JSON)',
                   command=self.save_report).pack(anchor='w', pady=(10, 0))

        live.rowconfigure(0, weight=1)
        live.columnconfigure(0, weight=1)
        self.sensors = ttk.Treeview(live, columns=('sensor', 'value', 'state', 'time'), show='headings', height=6)
        for name, title, width in [('sensor', 'PAR\u00c1METRO', 330), ('value', 'VALOR', 135), ('state', 'ESTADO', 180), ('time', 'LECTURA LOCAL', 130)]:
            self.sensors.heading(name, text=title)
            self.sensors.column(name, width=width, minwidth=80, anchor='w' if name == 'sensor' else 'center')
        self.sensors.grid(row=0, column=0, sticky='nsew')
        live_scroll = ttk.Scrollbar(live, orient='vertical', command=self.sensors.yview)
        live_scroll.grid(row=0, column=1, sticky='ns')
        self.sensors.configure(yscrollcommand=live_scroll.set)
        for sensor in SENSORS:
            self.sensors.insert('', 'end', iid=sensor.command, values=(sensor.label, '\u2014', 'Sin conexi\u00f3n', '\u2014'))
        controls = ttk.Frame(live)
        controls.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(10, 0))
        self.csv_button = ttk.Button(controls, text='Iniciar registro CSV', command=self.toggle_csv, state='disabled')
        self.csv_button.pack(side='left')
        ttk.Label(controls, text='Lecturas secuenciales; frecuencia seg\u00fan el coche y el lector.', style='Sub.TLabel').pack(side='left', padx=15)

        dtcs.rowconfigure(2, weight=1)
        dtcs.columnconfigure(0, weight=1)
        self.dtc_button = ttk.Button(dtcs, text='Leer fallos almacenados y pendientes', command=self.request_dtcs, state='disabled')
        self.dtc_button.grid(row=0, column=0, sticky='w')
        ttk.Label(dtcs, textvariable=self.dtc_status, wraplength=860).grid(row=1, column=0, columnspan=2, sticky='w', pady=10)
        self.dtc_table = ttk.Treeview(dtcs, columns=('type', 'code', 'description'), show='headings', height=6)
        for name, title, width in [('type', 'TIPO', 215), ('code', 'C\u00d3DIGO', 90), ('description', 'RESULTADO / DESCRIPCI\u00d3N', 560)]:
            self.dtc_table.heading(name, text=title)
            self.dtc_table.column(name, width=width, minwidth=70, anchor='w')
        hscroll = ttk.Scrollbar(dtcs, orient='horizontal', command=self.dtc_table.xview)
        self.dtc_table.configure(xscrollcommand=hscroll.set)
        self.dtc_table.grid(row=2, column=0, sticky='nsew')
        dscroll = ttk.Scrollbar(dtcs, orient='vertical', command=self.dtc_table.yview)
        dscroll.grid(row=2, column=1, sticky='ns')
        self.dtc_table.configure(yscrollcommand=dscroll.set)
        hscroll.grid(row=3, column=0, sticky='ew')
        ttk.Label(dtcs, text='OBD-II gen\u00e9rico de motor / emisiones. No es un escaneo completo de ABS, airbag u otros m\u00f3dulos.\nLas descripciones de la biblioteca pueden estar en ingl\u00e9s. Un c\u00f3digo no identifica por s\u00ed solo la pieza averiada.',
                  wraplength=840, style='Sub.TLabel').grid(row=4, column=0, columnspan=2, sticky='w', pady=(10, 0))

        self.log_text = tk.Text(logs, wrap='word', height=12, state='disabled', font=('Consolas', 10), borderwidth=0, padx=12, pady=12)
        self.log_text.pack(fill='both', expand=True)
        ttk.Button(logs, text='Guardar registro de conexi\u00f3n', command=self.save_log).pack(anchor='w', pady=(10, 0))
        ttk.Label(body, text='Usa el ordenador con el veh\u00edculo estacionado. Motor encendido: solo en un lugar bien ventilado.', style='Sub.TLabel').pack(side='bottom', anchor='w', pady=(12, 0), before=self.tabs)

    def log(self, text):
        line = f'{datetime.now():%H:%M:%S}  {text}'
        self.log_lines.append(line)
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.insert('end', '\n'.join(self.log_lines) + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def refresh_ports(self):
        try:
            ports = serial_ports()
            self.port_box.configure(values=ports)
            self.log('Puertos: ' + (', '.join(ports) if ports else 'ninguno; empareja el lector y crea su puerto serie.'))
        except Exception as exc:
            self.log(f'No se pudieron enumerar los puertos: {exc}')

    def set_busy(self, busy):
        self.connect_button.configure(state='disabled' if busy else 'normal')
        self.disconnect_button.configure(state='normal' if busy else 'disabled')
        self.port_box.configure(state='disabled' if busy else 'normal')
        self.baud_box.configure(state='disabled' if busy else 'readonly')
        self.protocol_box.configure(state='disabled' if busy else 'readonly')
        for widget in (self.refresh_button, self.demo_check, self.voltage_check):
            widget.configure(state='disabled' if busy else 'normal')

    def connect(self):
        if self.worker is not None:
            return
        demo = self.demo.get()
        port = self.port.get().strip()
        if not demo and not port:
            messagebox.showinfo('Selecciona el lector', 'Selecciona o escribe el puerto saliente, por ejemplo COM7 o /dev/rfcomm0.\nPara probar la interfaz sin hardware, activa Demostraci\u00f3n.')
            return
        try:
            baud = None if self.baud.get() == 'Auto' else int(self.baud.get())
        except ValueError:
            messagebox.showerror('Baudios', 'Selecciona una velocidad de la lista.')
            return
        check_voltage = not self.skip_voltage.get()
        self.session_demo = demo
        self.banner.set('DEMO  |  Todos los valores y fallos son SIMULADOS' if demo else 'SOLO LECTURA  |  No borra fallos ni modifica la centralita')
        protocol_id = next(p.id for p in PROTOCOLS if p.label == self.protocol_choice.get())
        self.last_report = {}
        self.show_report()
        callback = lambda report: self.events.put(('report', report))
        factory = DemoBackend if demo else lambda: RealBackend(
            port, baud, check_voltage, protocol=protocol_id, report_callback=callback)
        self.dtc_table.delete(*self.dtc_table.get_children())
        self.dtc_status.set('Todav\u00eda no se han consultado los fallos de esta sesi\u00f3n.')
        self.set_busy(True)
        self.status.set('Conectando; la detecci\u00f3n del protocolo puede tardar...')
        self.worker = Worker(factory, self.events)
        self.worker.start()

    def disconnect(self):
        if self.worker is not None:
            self.worker.stop()
            self.active = False
            self.stop_recording()
            self.disconnect_button.configure(state='disabled')
            self.dtc_button.configure(state='disabled')
            self.csv_button.configure(state='disabled')
            self.status.set('Cerrando al terminar la operaci\u00f3n en curso...')

    def request_dtcs(self):
        if self.active and self.worker is not None and not self.dtc_pending:
            self.dtc_pending = True
            self.dtc_button.configure(state='disabled')
            self.dtc_status.set('Consultando; los datos en directo se pausan durante esta lectura.')
            self.worker.actions.put('dtcs')

    def toggle_csv(self):
        if self.recorder is not None:
            self.stop_recording()
            return
        if not self.active:
            return
        prefix = 'DEMO' if self.session_demo else 'OBD'
        path = filedialog.asksaveasfilename(defaultextension='.csv', initialfile=f'{prefix}_{datetime.now():%Y%m%d_%H%M%S}.csv', filetypes=[('CSV', '*.csv')])
        if path:
            try:
                self.recorder = CSVRecorder(path, self.session_demo)
                self.csv_button.configure(text='Detener registro CSV')
                self.log(f'Grabando CSV en {path}')
            except OSError as exc:
                messagebox.showerror('No se pudo iniciar el registro', str(exc))

    def stop_recording(self):
        recorder, self.recorder = self.recorder, None
        if recorder is not None:
            try:
                recorder.close()
                self.log('Registro CSV cerrado.')
            except OSError as exc:
                self.log(f'Error al cerrar CSV: {exc}')
        self.csv_button.configure(text='Iniciar registro CSV')

    def save_log(self):
        path = filedialog.asksaveasfilename(defaultextension='.txt', initialfile='obd_conexion.txt', filetypes=[('Texto', '*.txt')])
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write('\n'.join(self.log_lines) + '\n')
            except OSError as exc:
                messagebox.showerror('No se pudo guardar', str(exc))

    def show_report(self):
        text = json.dumps(self.last_report, ensure_ascii=False, indent=2)
        self.report_text.configure(state='normal')
        self.report_text.delete('1.0', 'end')
        self.report_text.insert('end', text if self.last_report else 'Sin verificacion en esta sesion.')
        self.report_text.configure(state='disabled')

    def save_report(self):
        if not self.last_report:
            messagebox.showinfo('Sin informe', 'Inicia primero una conexion o una demostracion.')
            return
        prefix = 'DEMO' if self.last_report.get('origen') == 'SIMULADO' else 'OBD'
        path = filedialog.asksaveasfilename(defaultextension='.json',
            initialfile=f'{prefix}_verificacion.json', filetypes=[('JSON', '*.json')])
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as stream:
                    json.dump(self.last_report, stream, indent=2, ensure_ascii=False)
                    stream.write('\n')
            except OSError as exc:
                messagebox.showerror('No se pudo guardar el informe', str(exc))

    def pump(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self.handle_event(kind, payload)
        except queue.Empty:
            pass
        self._pump_id = self.after(100, self.pump)

    def handle_event(self, kind, payload):
        if kind == 'report':
            self.last_report = dict(payload)
            self.show_report()
        elif kind == 'health' and self.active:
            valid, missed = payload
            if self.session_demo:
                self.last_report['estado_sesion'] = 'SIMULADO: sin conexion con un coche'
            elif valid:
                self.last_report['estado_sesion'] = 'Respuesta ECU recibida en el ultimo ciclo'
                self.last_report['ultima_respuesta_utc'] = datetime.now(timezone.utc).isoformat()
                self.status.set(self.connection_info)
            else:
                self.last_report['estado_sesion'] = f'ECU sin respuesta valida: {missed}/3 ciclos'
                self.status.set(self.last_report['estado_sesion'])
            self.show_report()
        elif kind == 'connected':
            if self.worker is None or self.worker.stop_event.is_set():
                return
            info, demo = payload
            self.active = True
            self.connection_info = info
            self.status.set(info)
            self.log(info)
            self.dtc_button.configure(state='normal')
            self.csv_button.configure(state='normal')
        elif kind == 'readings' and self.active:
            for reading in payload:
                sensor = next(s for s in SENSORS if s.command == reading.command)
                value = '\u2014' if reading.value is None else f'{reading.value:.{sensor.decimals}f} {sensor.unit}'
                self.sensors.item(reading.command, values=(sensor.label, value, reading.status, datetime.fromtimestamp(reading.timestamp).strftime('%H:%M:%S')))
            if self.recorder is not None:
                try:
                    self.recorder.write(payload)
                except OSError as exc:
                    self.log(f'Error de escritura del CSV: {exc}')
                    self.stop_recording()
                    messagebox.showerror('Registro CSV detenido', str(exc))
        elif kind == 'dtcs' and self.active:
            self.dtc_pending = False
            self.dtc_button.configure(state='normal')
            self.dtc_table.delete(*self.dtc_table.get_children())
            for result in payload:
                if result.status not in ('OK', 'SIMULADO'):
                    self.dtc_table.insert('', 'end', values=(result.category, '\u2014', result.status))
                elif result.codes:
                    for code, desc in result.codes:
                        self.dtc_table.insert('', 'end', values=(result.category, code, desc))
                else:
                    text = 'SIMULADO: sin c\u00f3digos' if self.session_demo else 'Respuesta recibida sin c\u00f3digos en esta categor\u00eda'
                    self.dtc_table.insert('', 'end', values=(result.category, '\u2014', text))
            label = 'SIMULACI\u00d3N' if self.session_demo else 'Lectura realizada'
            self.dtc_status.set(f'{label}: {datetime.now():%H:%M:%S}. Consulta el resultado de cada categor\u00eda.')
            self.log('Consulta de fallos finalizada' + (' (SIMULADOS).' if self.session_demo else '.'))
        elif kind == 'error':
            self.log('ERROR: ' + payload)
            self.status.set(payload)
            messagebox.showerror('Conexi\u00f3n OBD', payload)
        elif kind == 'log':
            self.log(payload)
        elif kind == 'done':
            if self.last_report:
                self.last_report['estado_sesion'] = 'HISTORICO: sesion cerrada, no verifica conexion actual'
                self.show_report()
            self.active = False
            self.dtc_pending = False
            self.stop_recording()
            self.worker = None
            self.set_busy(False)
            self.dtc_button.configure(state='disabled')
            self.csv_button.configure(state='disabled')
            self.status.set('Desconectado. Consulta Registro si se produjo un error.')
            for sensor in SENSORS:
                self.sensors.item(sensor.command, values=(sensor.label, '\u2014', 'Desconectado', '\u2014'))
            if self.dtc_table.get_children():
                self.dtc_status.set('HIST\u00d3RICO de la sesi\u00f3n anterior; sin conexi\u00f3n actual.' + (' Datos SIMULADOS.' if self.session_demo else ''))
            self.log('Sesi\u00f3n cerrada.')

    def on_close(self):
        if self.closing:
            return
        self.closing = True
        if self.worker is not None:
            self.disconnect()
        self.stop_recording()
        self.wait_for_close()

    def wait_for_close(self):
        if self.worker is not None and self.worker.is_alive():
            self.after(100, self.wait_for_close)
        else:
            for name in ('_pump_id', '_demo_after_id'):
                task = getattr(self, name, None)
                if task:
                    try:
                        self.after_cancel(task)
                    except tk.TclError:
                        pass
            self.destroy()


def main():
    parser = argparse.ArgumentParser(description='Aplicaci\u00f3n local de lectura OBD-II por puerto serie Bluetooth.')
    parser.add_argument('--demo', action='store_true', help='Abrir con datos simulados, sin lector ni dependencias OBD.')
    args = parser.parse_args()
    require_venv()
    App(demo=args.demo).mainloop()


if __name__ == '__main__':
    main()
