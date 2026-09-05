# Integración con el hardware (controladoras N3000 / L04)

## El sistema legacy

El software original que esta plataforma reemplaza es el **"Professional Door Control Management" (N3000)**, distribuido como `AccessControl.en software` y su versión actualizada `WGACCESS_NUEVO_ACTUALIZADO`:

- Controladoras TCP/IP de hasta 4 puertas, identificadas por **número de serie (S/N) de 9 dígitos** grabado en la placa.
- Configuración de red por software: IP, máscara, gateway y **puerto 60000**.
- Lectoras Wiegand por puerta; lector USB de escritorio **WG1028** para el alta rápida de tarjetas.
- Base de datos legacy `iCCard3000.mdb` (Access) o SQL Server (`AccessData`).
- Comunicación física implementada en las DLLs del fabricante: `n3k_comm.dll`, `n3k_jm.dll`, `n3k_extern.dll`.
- Consola operativa: Check, Adjust Time, Upload, Monitor, Download y Download And Monitor.
- Privilegios por usuario y puerta: Allow / Allow and Upload / Prohibit / Prohibit and Upload.

## Principio de diseño: no inventar el protocolo

El manual del sistema es una **guía operativa, no una especificación de protocolo**. Siguiendo esa premisa (documentada en los prompts de diseño del proyecto), la plataforma **no asume tramas TCP/seriales propias del N3000**: toda la comunicación física está aislada detrás de la interfaz `ControllerGateway` (`backend/app/services/gateway/base.py`) con implementaciones intercambiables:

| Modo (`ACP_GATEWAY_MODE`) | Implementación | Estado |
|---|---|---|
| `simulated` (por defecto) | `simulated.py` — responde siempre, ideal para demo, desarrollo y tests | ✅ Estable |
| `tcp` | `l04_udp.py` — protocolo UDP binario de 64 bytes (puerto 60000) usado por controladoras de 4 puertas UHPPOTE-compatibles | ⚠️ **Experimental** |

> **Importante**: el modo `tcp` implementa un protocolo público de placas de 4 puertas que usan el mismo puerto 60000, pero **no está verificado contra las placas N3000 de este proyecto**. Antes de usarlo en producción hay que confirmar el protocolo real con el SDK del fabricante o capturando tráfico del software legacy.

### Codec del protocolo (Fase 2)

El **formato de la trama de 64 bytes** está aislado en el paquete puro `backend/app/services/protocol/` (sin I/O):

- `frames.py`: modelo `Frame` y `encode_frame`/`decode_frame` con validación (largo 64, marcador `0x17`, serial LE, `xID`/secuencia en offset 40).
- `codec.py`: builders/parsers por función (`FUNC_*`: status, open door, set time, put card, discover), helpers BCD/fecha y el registro de tarjeta (`CardRecord`).

`l04_udp.py` es **solo transporte** (UDP async) y delega toda la codificación en este codec, que es la **única fuente de verdad** del formato y está cubierto por tests puros (`tests/test_protocol_codec.py`) con vectores hex sintéticos. Sigue siendo **experimental**: un test verde del codec **no** equivale a validación contra hardware. Las funciones cuyo layout real se desconoce para el N3000 (p. ej. perfiles horarios semanales por tarjeta) se dejan **sin implementar** en lugar de inventarse. Ajustar los códigos `FUNC_*` en `codec.py` cuando se confirme el protocolo real; el resto de la plataforma no cambia.

## Camino recomendado hacia el hardware real

1. **Hoy**: operar con `simulated` — toda la lógica de negocio (personal, permisos, horarios, monitoreo) funciona completa; el panel "Probar lectura" ejercita el motor de decisión real.
2. **Confirmar el protocolo**: dos vías posibles:
   - Envolver las DLLs legacy (`n3k_comm.dll`) en un pequeño daemon puente en Windows que hable HTTP con esta API (las DLLs son de 32 bits para Windows; no se pueden usar directamente desde el backend Linux).
   - Capturar el tráfico UDP/TCP del software legacy hacia una placa real (Wireshark) y documentar las tramas.
3. **Implementar el adaptador real** detrás de `ControllerGateway` — el resto de la plataforma no cambia.
4. Los eventos de las placas se reportan a la API vía `POST /api/v1/events/swipe` (el daemon puente los reenvía), y quedan registrados y difundidos en vivo igual que los simulados.

## Decisión online vs offline

Las controladoras deciden de forma autónoma con las tarjetas cargadas en su memoria (el "Upload" del software original → botón **Sincronizar permisos**), y la plataforma decide en línea con su motor (`/api/v1/events/swipe`). Flujo recomendado:

1. Gestionar personal, niveles y horarios en la plataforma.
2. Sincronizar permisos hacia la placa (equivalente a "Allow and Upload").
3. La placa reporta los eventos; el puente los reenvía a la API para monitoreo e historial (equivalente a "Download And Monitor").

## Lectoras y formatos Wiegand / PIN (datasheets de lectora)

> Fuente: datasheets de las lectoras RFID y con teclado provistas por el dueño.
> Describen la interfaz **lectora → controladora** (Wiegand), no el protocolo de
> red plataforma↔controladora (ese sigue pendiente; ver "Codec del protocolo").

- **Tipos de tarjeta**: EM (125 KHz) y/o Mifare (13.56 MHz); Mifare incluye
  PLUS, DESFire, Pro, Ultralight, Classic, NFC213-216, S50, S70. IP67, 10-24 V DC.
- **Formato Wiegand**: default de fábrica **34 bits**; configurable por el usuario.
  EM: 26–44 bits. Mifare: 26–44, 47, 56, 58, **64**, 66 bits. (El soporte de
  **tarjeta de 64 bits** de Fase 2 corresponde a este formato Wiegand de 64 bits.)
- **PIN por teclado** (lectora con keypad), tres modos de salida Wiegand:
  - **4-bit por tecla**: cada dígito envía su nibble (1=0001 … 9=1001, 0=0000,
    *=1010, #=1011).
  - **8-bit por tecla**: cada dígito envía un byte (mapa dedicado por tecla).
  - **Virtual card number (10 dígitos)**: un PIN de 4-6 dígitos se emite como un
    número de tarjeta decimal de 10 dígitos (p. ej. `999999` → `0000999999`).
    Implicancia para la plataforma: un PIN de teclado puede presentarse como un
    "número de tarjeta" — a tener en cuenta al mapear credenciales PIN vs tarjeta.
- **Configuración**: en lectoras con teclado, los formatos Wiegand se setean por
  el teclado (modo programa `* <código> #`); las lectoras sin teclado requieren
  una lectora con teclado externa para configurarse.
- **Cableado de lectora** (colores): Red DC+, Black GND, Green D0, White D1,
  Brown LED (verde), Yellow BZ (buzzer), Grey BELL1, Blue BELL2.

## Cableado (resumen del manual original)

- Cerradura magnética al relé NO/COM de cada puerta con fuente de 12 V dedicada.
- Lectora Wiegand: D0/D1/GND/12V a la bornera de la puerta correspondiente.
- Sensor magnético de puerta y botón de salida a las entradas correspondientes.
- Diodo volante en cerraduras inductivas para proteger el relé.
- Lector USB WG1028 en el puesto de administración para el alta rápida de tarjetas (drivers FTDI incluidos en el material legacy).
