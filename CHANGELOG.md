# Cambios

## 0.2

- AGENTS.md completo en la raiz, con entorno, arquitectura y criterios de prueba.
- Foco Windows; instalacion local .venv y guardia de entorno en GUI/CLI.
- Selector Auto y protocolos 1-9, separados de baudios COM.
- Consulta 0100 adicional y validacion de payload 41 00 antes de declarar ECU.
- Se permite una ECU que responde 0100 aunque no anuncie sensores del panel.
- Verificacion de servicio/PID en sensores y de servicio en DTC.
- Latido OBD real ante ausencia de datos; tension nunca sustituye respuesta ECU.
- Informe por capas exportable a JSON y captura del registro tecnico de python-OBD.
- CLI diagnostico sin acceso a puertos salvo --port explicito.
- Pruebas de errores de protocolo, evidencia, entorno y contratos con la dependencia.
- Cierre cooperativo de ventana y marcado historico de informes al desconectar.

## 0.1

Base Python/Tkinter con seleccion de puerto, datos en vivo, lectura de fallos,
CSV, demo y comprobacion inicial CAR_CONNECTED. Ya creaba entorno virtual,
pero no incluia selector manual ni AGENTS.md ni verificacion adicional 0100.
