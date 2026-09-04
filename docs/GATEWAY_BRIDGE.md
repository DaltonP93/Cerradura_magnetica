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
**huella (fingerprint)** a la API en un header de confianza. Cada puente tiene su
propio certificado; revocarlo o desactivar el puente corta su acceso.

> **Confianza del header**: el borde **debe** setear/sobrescribir el header y
> **descartar** cualquier valor que envíe el cliente, para que no se pueda
> falsificar la identidad. El nombre del header es `ACP_BRIDGE_CERT_HEADER`
> (default `X-Client-Cert-Fingerprint`).

Ejemplo de Nginx (borde con verificación de cliente):

```nginx
ssl_client_certificate /etc/nginx/certs/bridge-ca.pem;   # CA que emite los certs de puente
ssl_verify_client on;
location /api/v1/gateway/commands/ {
    proxy_set_header X-Client-Cert-Fingerprint $ssl_client_fingerprint;  # el borde lo fija
    proxy_pass http://backend:8000;
}
```

## API del puente (implementada)

Registro (admin, autenticado como usuario de la plataforma):

- `POST /api/v1/gateway/bridges` — alta de un puente `{name, cert_fingerprint}`
  (la huella se normaliza: minúsculas, sin separadores). `GET` para listar.

Consumo (autenticado por la huella mTLS del puente, sin sesión de usuario):

- `POST /api/v1/gateway/commands/claim` — `{worker_token, controller_id?,
  lease_seconds?, limit?}` → arrienda comandos entregables de **la organización
  del puente** y los devuelve.
- `POST /api/v1/gateway/commands/{id}/ack` — `{worker_token, success, result?,
  error?}` → acusa el resultado (idempotente). Un comando de otra organización
  responde 404 (aislamiento multi-tenant).

## Pendiente (próximos tramos)

- **Cableado del outbox** al flujo de comandos (hoy los comandos se ejecutan de
  forma síncrona contra el `ControllerGateway`; en despliegues con puente pasarían
  por el outbox). Se hará detrás de un flag, sin cambiar el modo `simulated` por
  defecto.
- Sincronización desired/observed y confirmación del wire protocol real (Fase 2).
