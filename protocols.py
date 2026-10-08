"""ELM protocol catalogue and strict ECU evidence validation (no I/O).

Wire protocol implementation belongs to the ELM hardware/firmware and
python-OBD. These definitions select it; they cannot add missing hardware.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Protocol:
    id: str | None
    label: str

PROTOCOLS = (
    Protocol(None, 'Auto - detectar con el ELM327'),
    Protocol('1', '1 - SAE J1850 PWM (41.6 kbit/s)'),
    Protocol('2', '2 - SAE J1850 VPW (10.4 kbit/s)'),
    Protocol('3', '3 - ISO 9141-2 (inicio a 5 baudios)'),
    Protocol('4', '4 - ISO 14230-4 KWP2000 (inicio a 5 baudios)'),
    Protocol('5', '5 - ISO 14230-4 KWP2000 (inicio rapido)'),
    Protocol('6', '6 - ISO 15765-4 CAN (11 bits, 500 kbit/s)'),
    Protocol('7', '7 - ISO 15765-4 CAN (29 bits, 500 kbit/s)'),
    Protocol('8', '8 - ISO 15765-4 CAN (11 bits, 250 kbit/s)'),
    Protocol('9', '9 - ISO 15765-4 CAN (29 bits, 250 kbit/s)'),
)
PROTOCOL_IDS = frozenset(p.id for p in PROTOCOLS if p.id is not None)


def normalize_protocol(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in ('', '0', 'AUTO'):
        return None
    if text not in PROTOCOL_IDS:
        raise ValueError('Protocolo no admitido: usa Auto o los identificadores 1 a 9.')
    return text


def valid_payloads(response, prefix: bytes, length: int | None = None) -> tuple[bytes, ...]:
    """Do not mistake decoded values, AT replies, or echoes for ECU evidence.

    Inputs are python-OBD Message.data payloads (already stripped of transport
    headers, PCI bytes and checksums). We do not parse raw CAN frames here.
    """
    if response is None or response.is_null():
        return ()
    valid = []
    for message in getattr(response, 'messages', ()):
        data = getattr(message, 'data', None)
        if not isinstance(data, (bytes, bytearray, list, tuple)):
            continue
        try:
            payload = bytes(data)
        except (ValueError, TypeError, OverflowError):
            continue
        if payload.startswith(prefix) and (length is None or len(payload) == length):
            valid.append(payload)
    return tuple(valid)


def pid_evidence(response) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Fresh Mode 01 PID 00 must contain 41 00 and four bitmap bytes."""
    payloads = valid_payloads(response, b'\x41\x00', 6)
    if not payloads:
        raise ConnectionError(
            'ECU no verificada: falta una respuesta valida 41 00 con cuatro bytes '
            'de PIDs. Bluetooth, OK, ATI, AT RV y CAR_CONNECTED no bastan.')
    advertised = set()
    for data in payloads:
        mask = int.from_bytes(data[2:], 'big')
        advertised.update(f'{pid:02X}' for pid in range(1, 33)
                          if mask & (1 << (32 - pid)))
    return tuple(data.hex(' ').upper() for data in payloads), tuple(sorted(advertised))


@dataclass(frozen=True)
class ClearVerdict:
    confirmed: bool
    status: str
    detail: str


def clear_dtc_evidence(response) -> ClearVerdict:
    """Mode 04 evidence. The ELM 'OK' is not proof of a clear.

    python-OBD decodes CLEAR_DTC with a drop decoder, so OBDResponse.value is
    always None and OBDResponse.is_null() is always True for this command.
    Evidence must be read straight from raw message payloads: positive is 44;
    negative is 7F 04 <NRC>.
    """
    if response is None:
        return ClearVerdict(False, 'Sin respuesta',
                            'No hubo respuesta del adaptador; no se puede confirmar el borrado.')
    positives, negatives = [], []
    for message in getattr(response, 'messages', None) or ():
        data = getattr(message, 'data', None)
        if not isinstance(data, (bytes, bytearray, list, tuple)):
            continue
        try:
            payload = bytes(data)
        except (ValueError, TypeError, OverflowError):
            continue
        if payload.startswith(b'\x44'):
            positives.append(payload)
        elif payload.startswith(b'\x7f'):
            negatives.append(payload)
    if negatives:
        for data in negatives:
            if len(data) >= 3 and data[1] == 0x04:
                return ClearVerdict(False, 'Rechazado por la ECU (7F 04)',
                                    f'La ECU respondio negativo: NRC 0x{data[2]:02X}. No se borro nada.')
        return ClearVerdict(False, 'Respuesta negativa (7F)',
                            'La ECU devolvio una respuesta negativa; no se confirma el borrado.')
    if positives:
        return ClearVerdict(True, 'Confirmado por la ECU (44)',
                            f'La ECU acepto el borrado (modo 04). Respuestas validas 44: {len(positives)}.')
    return ClearVerdict(False, 'No confirmado (sin 44)',
                        'No hubo payload OBD 44. El OK del ELM327 no prueba el borrado.')
