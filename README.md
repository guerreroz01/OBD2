# OBD Desk 0.2 - Windows, ELM327 y verificacion de ECU

Proyecto Python/Tkinter de escritorio para el lector IM77R anunciado como
ELM327 Bluetooth 2.1. Incluye codigo, instaladores locales y AGENTS.md para
continuar el desarrollo con un agente. Es un ZIP de codigo, no un .exe.

**No se ha comprobado aun con el adaptador ni el coche del usuario.**
Consulta VALIDACION.md para saber exactamente que se ha probado.

## Instalacion en Windows

Extrae todo el ZIP a una carpeta propia, por ejemplo `C:\Proyectos\obd_desk`.
Necesitas Python con Tcl/Tk. Para esta base se propone Python 3.12 o 3.13.

1. Ejecuta `instalar_windows.bat`: crea `.venv`, instala las dependencias alli
   y verifica importaciones. Necesita Internet para descargar los paquetes.
2. Abre `demo_windows.bat` para probar sin coche, o `iniciar_windows.bat` para
   conectar al lector. Ambos utilizan exclusivamente el Python de `.venv`.
3. `probar_windows.bat` ejecuta las pruebas sin acceder a un vehiculo.

No uses `pip install` global. No hace falta activar el entorno ni cambiar la
politica de PowerShell: se llama directamente a `.venv\Scripts\python.exe`.
El entorno no se incluye en el ZIP porque debe crearse para cada instalacion.
`requirements.txt` fija las dependencias directas, no todas las transitivas.

Alternativa desde PowerShell en la raiz:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip --require-virtualenv install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe app.py --demo
```

Si no tienes la version 3.13, usa `py -3.12` en el primer comando. El runtime
rechaza arrancar GUI/CLI con el Python global. Un venv aisla paquetes Python;
no es una maquina virtual y no instala el controlador Bluetooth del sistema.

## Preparar la conexion

Con el coche estacionado, conecta el lector a su toma OBD y pon el contacto
segun las indicaciones del vehiculo. Para la prueba inicial normalmente no es
necesario arrancar el motor. Empareja el lector desde Windows usando el PIN
que indique su documentacion; la app no intenta adivinarlo.

Comprueba el servicio serie Bluetooth/SPP y localiza su puerto COM saliente.
La app utiliza ese puerto, no un servicio BLE/GATT. "Actualizar" solo enumera
puertos: no los abre ni envia consultas para descubrir cual es el lector.
Selecciona expresamente el COM del IM77R y cierra otras apps que puedan usarlo.
Que Windows muestre emparejamiento no confirma comunicacion con la ECU.

Empieza con **Protocolo Auto** y **Baudios Auto**. Los baudios del COM no son
la velocidad del bus del coche. La seleccion manual solo debe hacerse con
informacion sobre el vehiculo. Consulta docs/PROTOCOLS.md.

## Que verifica la app

La dependencia inicializa el ELM, intenta el protocolo y descubre los PIDs.
Adicionalmente, OBD Desk exige una consulta **nueva `0100`** con payload
normalizado **`41 00 AA BB CC DD`** antes de declarar la ECU verificada.
Los cuatro bytes son el mapa de los PIDs 01-20 hexadecimales.

La pestana **Verificacion ECU** separa enlace serie, respuestas AT y evidencia
ECU. Incluye protocolo, hora UTC y payloads de `0100`, exportables en JSON.
El informe es una instantanea, no una garantia de que la conexion siga abierta;
al desconectar se marca HISTORICO. La demo se marca SIMULADO.

Cada lectura del motor exige servicio/PID coherentes. Si no hay datos validos
se usa otro `0100` como latido. Tres ciclos sin datos ECU ni latido provocan
cierre con error, aunque el adaptador siga respondiendo a tension.
La comprobacion de tension puede omitirse para adaptadores que la reporten mal,
pero eso no desactiva la verificacion de la ECU.

## Funciones incluidas

- Seleccion Auto o protocolos ELM 1-9: J1850 PWM/VPW, ISO 9141-2,
  ISO 14230-4 KWP2000 (5 baudios/rapido), ISO 15765-4 CAN 11/29 bits y 250/500 kbit/s.
- RPM, velocidad, temperaturas, carga, mariposa, presion de admision, si la ECU
  anuncia esos sensores. La tension se identifica como lectura del adaptador.
- Consulta de DTC almacenados (03) y pendientes (07), sin borrado.
- Registro CSV y registro tecnico de la biblioteca, con comandos/respuestas.
- Demo sin importar la biblioteca OBD ni abrir un puerto.
- Diagnostico CLI sin GUI y guia AGENTS.md para desarrollo asistido.

El registro visual conserva las ultimas 1000 entradas; guarda pronto una
traza de conexion fallida. Las lecturas son secuenciales. La cancelacion se
atiende entre operaciones; no se promete un limite total de dos segundos.
Una negociacion sin respuesta puede tardar por los timeouts de la dependencia.

## Diagnostico por consola

Solo comprueba entorno y enumera puertos, sin abrirlos:

```powershell
.\.venv\Scripts\python.exe diagnostico.py
```

Con autorizacion para ese lector y vehiculo, verifica un COM concreto:

```powershell
.\.venv\Scripts\python.exe diagnostico.py --port COM7 --protocol Auto --verbose
```

`COM7` es un ejemplo; sustituye por el puerto real. Para un protocolo conocido:

```powershell
.\.venv\Scripts\python.exe diagnostico.py --port COM7 --protocol 6 --baud 38400
```

No ejecutes GUI y CLI a la vez sobre el mismo puerto. El resultado se guarda
en `diagnostico_obd.json` y puede elegirse otra ruta con `--output`.
Sin dependencias se informa de su ausencia; no es una verificacion del coche.

## Limites importantes

El codigo selecciona protocolos y procesa respuestas; no puede incorporar
transceptores ni funciones de firmware ausentes en el IM77R. Que un anuncio
diga ELM327 no certifica todas sus capacidades. Falta comprobar la unidad real.
Tampoco basta que el conector fisico sea OBD para que cualquier ECU sea accesible.

Esta version implementa diagnostico OBD-II generico de motor/emisiones.
No promete diagnostico ABS/airbag, funciones de marca, UDS completo, CAN FD,
DoIP, J1939, codificacion ni reprogramacion. Una respuesta sin codigos en una
categoria no demuestra que todo el coche carezca de averias.

"Solo lectura" significa que no se borra ni modifica la ECU; si se envian
solicitudes diagnosticas al bus y comandos de configuracion al ELM.
No se usa mientras se conduce. Motor encendido: solo con ventilacion adecuada.

## Desarrollo con un agente

Abre la carpeta `obd_desk` como raiz del proyecto y pide al agente que lea
**AGENTS.md** antes de modificar archivos. Alli estan arquitectura, comandos,
invariantes de verificacion, seguridad, pruebas y criterios de entrega.
No hacen falta cuentas ni servicios externos para ejecutar la aplicacion.

Los scripts Linux se conservan solo como ayuda de desarrollo heredada; el
objetivo del usuario es Windows. No hay que instalar WSL.

## Licencia y fuentes

Se conserva `COPYING` (GPL v2) de la entrega original; python-OBD tiene su propia
licencia GPL. No se incluyen los paquetes de terceros dentro del proyecto.
Las fuentes tecnicas primarias y secciones consultadas estan en docs/SOURCES.md.
