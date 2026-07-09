# Integración con las placas L04

## La placa

La L04 es una controladora de acceso TCP/IP de 4 puertas:

- 4 lectoras Wiegand 26/34 (entrada) + 4 relés de cerradura (salida).
- Sensores de puerta y botones de salida por puerta.
- Comunicación por red Ethernet, protocolo binario UDP en el puerto **60000**.
- Identificación por **número de serie** grabado en la placa (como en el software de escritorio original, la placa se da de alta por su número de serie).

## Protocolo (`backend/app/services/gateway/l04_udp.py`)

Paquetes fijos de **64 bytes**:

| Offset | Contenido |
|---|---|
| 0 | `0x17` (tipo de paquete) |
| 1 | Código de función |
| 4–7 | Número de serie de la placa (uint32 little-endian) |
| 8– | Payload de la función |

Funciones implementadas:

| Código | Función | Uso en la plataforma |
|---|---|---|
| `0x20` | Estado | `ping` → online/offline |
| `0x30` | Poner hora (BCD) | Botón "Sincronizar hora" |
| `0x40` | Abrir puerta (nº 1–4) | Apertura remota |
| `0x50` | Cargar tarjeta (nº, vigencia, puertas) | "Sincronizar permisos" |
| `0x94` | Descubrimiento | reservado |

> **Nota**: algunas revisiones de placa usan códigos de función distintos. Están centralizados como constantes `FUNC_*` al inicio de `l04_udp.py`; ajustarlos según el SDK del fabricante no afecta al resto de la plataforma.

## Modos de operación

- `ACP_GATEWAY_MODE=simulated` (por defecto): sin hardware; todos los comandos responden éxito y el panel de "Probar lectura" ejercita el motor de decisión completo.
- `ACP_GATEWAY_MODE=tcp`: envía los comandos UDP reales a la IP/puerto configurados en cada controladora. El backend necesita visibilidad de red hacia las placas (misma LAN o VPN).

## Decisión online vs offline

La placa puede decidir de forma autónoma con las tarjetas cargadas en su memoria (`sync_permissions`), y la plataforma decide en línea con el motor (`/api/v1/events/swipe`). El flujo recomendado en producción:

1. Gestionar personal, niveles y horarios en la plataforma.
2. Pulsar "Sincronizar permisos" (o automatizarlo) para bajar las tarjetas a la placa.
3. La placa reporta los eventos, que se registran vía `swipe` (un daemon puente en la LAN puede reenviar los eventos de la placa a la API).

## Cableado (resumen del manual original)

- Cerradura magnética al relé NO/COM de cada puerta con fuente de 12 V dedicada.
- Lectora Wiegand: D0/D1/GND/12V a la bornera de la puerta correspondiente.
- Sensor magnético de puerta y botón de salida a las entradas correspondientes.
- Diodo volante en cerraduras inductivas para proteger el relé.
