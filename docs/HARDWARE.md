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

> **Importante**: el modo `tcp` implementa un protocolo público de placas de 4 puertas que usan el mismo puerto 60000, pero **no está verificado contra las placas N3000 de este proyecto**. Antes de usarlo en producción hay que confirmar el protocolo real con el SDK del fabricante o capturando tráfico del software legacy. Los códigos de función están centralizados como constantes `FUNC_*` en `l04_udp.py` para ajustarlos sin tocar el resto de la plataforma.

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

## Cableado (resumen del manual original)

- Cerradura magnética al relé NO/COM de cada puerta con fuente de 12 V dedicada.
- Lectora Wiegand: D0/D1/GND/12V a la bornera de la puerta correspondiente.
- Sensor magnético de puerta y botón de salida a las entradas correspondientes.
- Diodo volante en cerraduras inductivas para proteger el relé.
- Lector USB WG1028 en el puesto de administración para el alta rápida de tarjetas (drivers FTDI incluidos en el material legacy).
