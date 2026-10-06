# Pruebas y validacion

## Sin hardware

Desde PowerShell en Windows, con dependencias instaladas en `.venv`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe app.py --demo
.\.venv\Scripts\python.exe diagnostico.py --output entorno_prueba.json
```

Las pruebas unitarias y de GUI utilizan datos simulados. Las de contrato
procesan tramas de ejemplo con el parser de python-OBD, sin abrir puertos.
Si falta `obd`, los tres contratos se omiten con un motivo explicito: no los
cuentes como aprobados. Si no hay pantalla, la GUI tambien puede omitirse.

En un entorno de desarrollo Linux con pantalla virtual:

```bash
python3 -m venv .venv
.venv/bin/python -m pip --require-virtualenv install -r requirements.txt
xvfb-run -a .venv/bin/python -m unittest discover -s tests -v
```

Comprueba tambien: una carpeta con espacios, un .venv nuevo, arranque desde
otra carpeta, mensajes de error de instalacion, red no disponible, importacion
Tkinter, intento de arrancar fuera de un entorno virtual y cierre de ventana.
La revision estatica de un .bat bajo Linux no es una prueba de Windows.

## Con hardware (solo autorizado y estacionado)

Anota marca/modelo/ano/motor y region del coche, Windows, puerto COM y protocolo.
No hace falta recoger VIN ni matricula. Cierra otras apps y verifica contacto.

Empieza con Auto; guarda JSON y registro. Acepta la conexion solo con payload
`41 00` valido, y comprueba algun sensor anunciado. Si esta disponible, cero
RPM con motor parado debe presentarse como cero, no como falta de respuesta.

Comprueba perdida de comunicacion en una sesion segura: ninguna lectura vieja
ni la tension del ELM debe seguir marcando la ECU como conectada. No hagas
pruebas sobre un vehiculo en circulacion ni borres fallos para "probar".

Repite despues con el protocolo manual que se haya identificado. No inventes
que todos los protocolos han sido probados fisicamente por ensayar solo uno.
Distingue validacion de transporte Bluetooth, de ELM, de bus y de servicios OBD.

Registra resultado exacto y limites en VALIDACION.md. Una demo, un mock o un
parser de ejemplo no certifica compatibilidad del IM77R ni de un coche real.
