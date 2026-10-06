# Fuentes primarias consultadas

Consulta de referencia: 2026-10-06. La implementacion depende de `obd==0.7.3`
y `pyserial==3.5`; las paginas "latest" pueden cambiar despues.

- Elm Electronics, ELM327 Datasheet (ELM327DSJ). Paginas 31 (Talking to the
  Vehicle), 36 (Selecting Protocols) y apartados de comandos AT y formatos:
  https://www.elmelectronics.com/wp-content/uploads/2016/07/ELM327DS.pdf
- python-OBD, Connections: protocolo, supports(), consultas y advertencia de
  que status() es estado inicial, no una comprobacion periodica:
  https://python-obd.readthedocs.io/en/latest/Connections/
- Codigo de la version fijada: ELM initialization, ATSP0, ATTPn, ATDPN:
  https://github.com/brendan-w/python-OBD/blob/v0.7.3/obd/elm327.py
- Codigo de consultas y descubrimiento de PIDs:
  https://github.com/brendan-w/python-OBD/blob/v0.7.3/obd/obd.py
- Modelo Message.data y decodificacion de PIDs:
  https://github.com/brendan-w/python-OBD/blob/v0.7.3/obd/protocols/protocol.py
  https://github.com/brendan-w/python-OBD/blob/v0.7.3/obd/decoders.py
- Python, venv: aislamiento, invocacion directa y no portabilidad:
  https://docs.python.org/3.13/library/venv.html
- Microsoft, pila Bluetooth: RFCOMM y puertos COM virtuales:
  https://learn.microsoft.com/en-us/windows-hardware/drivers/bluetooth/bluetooth-driver-stack
- Version de la dependencia:
  https://pypi.org/project/obd/0.7.3/

La ficha del producto y la afirmacion Bluetooth 2.1 identifican el equipo
aportado por el usuario; no se han usado como prueba de comunicacion fisica
ni como certificacion de los protocolos de una unidad concreta.
