# Validacion de OBD Desk 0.2

Fecha: 2026-10-06. Entorno de revision: Linux x86_64, Python 3.13.5,
Tk 8.6 y pantalla virtual Xvfb. Python usado dentro de un venv de pruebas.

## Resultados observados

- 46 pruebas descubiertas: **43 superadas, 3 omitidas**, sin fallos.
- Las tres omitidas corresponden a contratos con el parser real de python-OBD
  (CAN 11 bits, CAN 29 bits y respuesta NO DATA).
- Se intento instalar `obd==0.7.3` y `pyserial==3.5` en el entorno de pruebas,
  pero fallo la descarga por resolucion de red. NO se han validado aqui esas
  dependencias en ejecucion, su instalacion completa ni `pip check` con ellas.
- Las pruebas de backend usan dobles de prueba. No se ha simulado ni afirmado
  que esos dobles constituyan comunicacion Bluetooth o acceso a una ECU real.
- Compilacion de los modulos y pruebas: correcta.
- GUI demo: arranque, lecturas, DTC simulados, selector, informe y desconexion
  comprobados. Vistas de datos e informe revisadas visualmente en Linux.
- CLI sin --port: devuelve informacion del entorno sin abrir puertos y senala
  explicitamente la ausencia de las dependencias de comunicacion.
- Intento real de arrancar con `/usr/bin/python3` fuera de venv: rechazado con
  codigo de salida 1 e indicacion de usar los scripts del proyecto.
- Scripts .bat revisados estaticamente; NO ejecutados en Windows.
- Hardware: NINGUNO. No se dispone del IM77R ni del coche del usuario.

Comando de pruebas ejecutado desde la raiz, en el entorno de revision:

```bash
xvfb-run -a /mnt/data/obd_v02/.testvenv/bin/python -m unittest discover -s tests -v
```

Salida completa conservada en `docs/TEST_RESULTS.txt`. Imagenes de la DEMO
bajo Linux: `docs/demo_linux.png` y `docs/verificacion_demo_linux.png`.
No son capturas de Windows ni datos reales de un coche.

## Pendiente antes de declarar compatibilidad

Instalar desde cero en Windows; importar dependencias; ejecutar `pip check`
y toda la suite sin omisiones; comprobar scripts y emparejamiento/COM;
verificar respuestas reales 0100 y sensores en la unidad del usuario.
Probar protocolos diferentes requiere vehiculos/simuladores apropiados:
una prueba con CAN no certifica J1850 ni K-line.

No se certifica lectura de ABS/airbag, funciones de marca ni todas las ECUs.
