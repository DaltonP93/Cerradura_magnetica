# Puente de gateway local (Fase 3) — diseño y andamiaje

> Estado: **andamiaje lado-plataforma**. No hay comunicación con hardware en el
> repositorio; el puente real es un componente externo. Nada aquí abre puertas
> ni contacta controladoras.

## Por qué un puente

Las DLLs del fabricante (`n3k_comm.dll`, …) son de 32 bits para Windows y no se
usan desde el backend Linux (ver `docs/HARDWARE.md`). Un **daemon puente** corre
cerca de las placas (Windows), habla con ellas (por las DLLs o el protocolo UDP
del codec de Fase 2) y se comunica con esta API por HTTP sobre **mTLS**.

## Flujo outbox / inbox

- **Outbox (plataforma → placa):** la plataforma encola comandos
  (`open_door`, `sync_time`, `sync_permissions`, `ping`). El puente los **arrienda**
  (lease), los ejecuta y **acusa** el resultado.
- **Inbox (placa → plataforma):** los eventos de las placas se reportan vía
  `POST /api/v1/events/swipe` (ya existente), quedando registrados y difundidos
  igual que los simulados.

## Modelo de outbox (implementado)

Tabla `gateway_commands` (`app/models/gateway.py`) + servicio
`app/services/gateway_outbox.py`:

- **`enqueue`** — idempotente por `(organization_id, idempotency_key)`: reencolar
  la misma clave devuelve la fila existente (nunca duplica un comando).
- **`claim`** — un worker arrienda hasta *N* comandos entregables (PENDING, o
  LEASED con lease vencido) mediante **compare-and-set** por fila: un comando se
  entrega a lo sumo a un worker a la vez; el `attempts` se incrementa por entrega.
- **`acknowledge`** — el worker dueño del lease reporta éxito/fallo. **Idempotente**
  (un segundo ack sobre un comando terminal no hace nada). El fallo reencola hasta
  agotar `max_attempts`, luego marca `FAILED`.

Estados: `PENDING → LEASED → SUCCEEDED | FAILED` (o `LEASED → PENDING` al reintentar).
El **lease con expiración** permite recuperar comandos de un worker caído sin
riesgo de doble entrega concurrente.

## Idempotencia (dos niveles)

1. **Encolado:** la clave de idempotencia evita encolar el mismo comando dos veces.
2. **Entrega:** el puente debe tratar cada comando como idempotente en la placa
   (p. ej. "set time" y "put card" son naturalmente idempotentes; "open door" es
   una pulsación puntual). El `acknowledge` idempotente cubre reintentos de red.

## Cola SQLite del puente

El puente mantiene **su propia cola SQLite local** (persistente) para sobrevivir
reinicios y cortes de red: guarda los comandos arrendados hasta acusarlos y los
eventos por subir hasta confirmarlos. Es un componente externo; este repositorio
sólo define el contrato de la plataforma.

## mTLS

La autenticación puente↔plataforma es **TLS mutuo**: el borde (Nginx/ingress,
ver `docs/DEPLOYMENT.md`) valida el certificado de cliente del puente y pasa su
identidad a la API. Cada puente tiene su propio certificado; revocarlo corta su
acceso.

## Pendiente (próximos tramos)

- **API orientada al puente**: `claim` / `acknowledge` sobre HTTP con la identidad
  mTLS del puente (aún no expuesta como endpoints).
- **Cableado del outbox** al flujo de comandos (hoy los comandos se ejecutan de
  forma síncrona contra el `ControllerGateway`; en despliegues con puente pasarían
  por el outbox). Se hará detrás de un flag, sin cambiar el modo `simulated` por
  defecto.
- Sincronización desired/observed y confirmación del wire protocol real (Fase 2).
