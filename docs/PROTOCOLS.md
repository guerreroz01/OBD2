# Comunicacion con el ELM327 y la ECU

## Tres capas, tres pruebas distintas

1. Windows / SPP-RFCOMM / COM: transporte serie sobre Bluetooth clasico.
2. Aplicacion / comandos AT / ELM327: configuracion e identificacion del lector.
3. ELM327 / protocolo del bus / ECU: solicitudes y respuestas OBD del vehiculo.

El puerto COM y `OK` no demuestran el paso 3. La tension tampoco. El dato
importante es la respuesta a una consulta OBD dirigida al vehiculo.

## Catalogo seleccionable

| ID | Protocolo del vehiculo | Seleccion realizada por la dependencia |
|---|---|---|
| Auto | Busqueda automatica | `ATSP0`, consulta `0100` y `ATDPN`; posibles reintentos internos |
| 1 | SAE J1850 PWM, 41.6 kbit/s | `ATTP1` |
| 2 | SAE J1850 VPW, 10.4 kbit/s | `ATTP2` |
| 3 | ISO 9141-2, inicializacion a 5 baudios | `ATTP3` |
| 4 | ISO 14230-4 KWP2000, inicializacion a 5 baudios | `ATTP4` |
| 5 | ISO 14230-4 KWP2000, inicializacion rapida | `ATTP5` |
| 6 | ISO 15765-4 CAN, 11 bits, 500 kbit/s | `ATTP6` |
| 7 | ISO 15765-4 CAN, 29 bits, 500 kbit/s | `ATTP7` |
| 8 | ISO 15765-4 CAN, 11 bits, 250 kbit/s | `ATTP8` |
| 9 | ISO 15765-4 CAN, 29 bits, 250 kbit/s | `ATTP9` |

`ATSPn` es el comando Set Protocol del ELM. La seleccion manual de
python-OBD 0.7.3 utiliza `ATTPn` (Try Protocol), no una implementacion fisica
del bus en Python. El modo Auto de la dependencia tiene su propio fallback;
la app no acepta como resultado J1939 ni IDs fuera de 1-9.

La lista expresa capacidad del SOFTWARE para seleccionar esos protocolos,
no certificacion de que esta unidad fisica los implemente todos. El firmware
y la circuiteria del adaptador, el coche, su ECU y su estado de contacto deben
ser compatibles. Ningun archivo en un venv corrige la ausencia de hardware.

## Flujo de esta version

```text
Usuario selecciona COM y Auto/ID
  -> python-OBD / pyserial abre el puerto concreto
  -> inicializacion del ELM (ATZ, ATE0, ATH1, ATL0; tension opcional)
  -> seleccion/negociacion del protocolo y descubrimiento de PIDs
  -> estado inicial de la biblioteca (NO es el criterio final)
  -> OBD Desk envia otra consulta PIDS_A / 0100
  -> exige payload normalizado 41 00 + 4 bytes
  -> publica ECU verificada con evidencia y fecha
  -> lee solo sensores anunciados y valida servicio/PID
  -> si faltan datos: latido nuevo 0100; tres fallos de ciclo cierran la sesion
```

Las cabeceras y, para CAN, la reconstruccion de mensajes se delegan a
python-OBD/ELM. `valid_payloads()` recibe `Message.data`, no una trama de cable.
Por ejemplo `7E8 06 41 00 BE 3E B8 13 00` es una representacion CAN con
cabecera/longitud/relleno. La evidencia normalizada es `41 00 BE 3E B8 13`.
Ese ejemplo es una muestra tecnica, no una lectura del coche del usuario.

El bit mas significativo del primer byte indica PID 01, y el menos
significativo del cuarto indica PID 20 hexadecimal. La lista del informe es
la union de las respuestas conservadas por la biblioteca, no un inventario
completo de todas las centralitas del vehiculo. Los bloques superiores se
consultan por la dependencia segun sus mapas, pero el informe muestra 01-20.

No hay selector de ECU por direccion en esta version. El filtrado y la
identificacion de motor usados por python-OBD limitan que modulos aparecen.
No confundir protocolo KWP2000 de OBD generico con funciones de fabricante,
ni CAN OBD con disponer de todos los servicios UDS.

## Borrado de fallos: modo 04 (unica escritura)

El modo 04 (`CLEAR_DTC`) es la unica operacion de escritura de la app. Requiere
confirmacion explicita del usuario y nunca se ejecuta sola. Elimina los DTC
almacenados y pendientes, la foto de datos (freeze frame) y reinicia los monitores
de disposicion, que quedaran "no listos" hasta completar de nuevo los ciclos de
conduccion. Por eso no se usa para ocultar averias ni antes de una inspeccion.

`python-OBD==0.7.3` decodifica `CLEAR_DTC` con un decodificador `drop`: su
`OBDResponse.value` es siempre `None` e `is_null()` siempre `True`. No se puede usar
`valid_payloads()` como evidencia de borrado. La evidencia se lee directamente de
`response.messages[*].data`:

- `44`: la ECU acepta el borrado (positivo). Es la unica confirmacion valida.
- `7F 04 <NRC>`: la ECU rechaza el borrado (negativo).
- Cualquier otro caso (sin mensajes, sin `44`): no confirmado. El `OK` del ELM327
  no prueba nada.

El modo 04 no es una lectura: hay trafico de escritura en el bus. Sigue sin haber
consola AT/UDS/raw ni otros servicios de escritura (modo 08, codificacion,
actuadores, acceso de seguridad).

## Errores que no son "ECU conectada"

`NO DATA`, `UNABLE TO CONNECT`, `CAN ERROR`, errores de inicializacion,
respuestas negativas, eco del comando y datos truncados se tratan como falta
de evidencia valida. No se atribuyen automaticamente a una causa unica:
pueden influir contacto, protocolo, adaptador, puerto, ECU o alimentacion.
Consulta la traza tecnica y no diagnostiques un componente por el mensaje solo.

Para el formato, comandos y asignacion de protocolos: ver docs/SOURCES.md.
