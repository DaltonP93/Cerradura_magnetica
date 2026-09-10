# Despliegue seguro — Control de Acceso

> Guía operativa de endurecimiento. No autoriza acciones sobre hardware ni
> producción real; documenta cómo desplegar la plataforma web de forma segura.

## Checklist de producción (antes de exponer la app)

- [ ] `ACP_ENVIRONMENT=production` (la app se niega a arrancar con defaults
      inseguros: secret/superuser por defecto, `ACP_DEBUG=true`, o
      `ACP_COOKIE_SECURE=false`).
- [ ] `ACP_SECRET_KEY` único y largo (`openssl rand -hex 32`).
- [ ] `ACP_FIRST_SUPERUSER_PASSWORD` cambiado del default.
- [ ] `ACP_COOKIE_SECURE=true` **y** un borde HTTPS real (ver TLS).
- [ ] `ACP_CORS_ORIGINS` con el/los orígenes reales del frontend (sin comodines).
- [ ] `POSTGRES_PASSWORD` fuerte y fuera del control de versiones.
- [ ] Backups de la base programados y verificados (ver Backups).
- [ ] Un solo worker de uvicorn, **o** un bus compartido (Redis) para
      rate-limit y revocación de WebSocket entre procesos (ver Multi-worker).

## TLS y cookies seguras

La app emite las cookies de sesión con el flag `Secure`, por lo que el
navegador solo las envía sobre **HTTPS**. En producción el navegador debe
llegar a la app por HTTPS, terminando TLS en uno de dos lugares:

1. **En un balanceador/ingress upstream** que reenvíe `X-Forwarded-Proto=https`.
   El `nginx.conf` por defecto (HTTP :80) sirve detrás de ese borde.
2. **En el propio Nginx**: usar `frontend/nginx.tls.conf` (redirige 80→443 y
   termina TLS). Montar el certificado y la clave y reemplazar el config por
   defecto (ver el encabezado del archivo para el ejemplo de compose).

> Si `ACP_COOKIE_SECURE=true` y el navegador llega por HTTP plano, el login
> "funciona" pero la cookie no se guarda y la siguiente petición es 401. Ese es
> el síntoma de que falta el borde HTTPS.

## Cabeceras y proxy

- Nginx agrega cabeceras de seguridad a toda respuesta: `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Strict-Transport-Security`
  (HSTS) y una `Content-Security-Policy` restrictiva (`default-src 'self'`).
- El backend corre con `uvicorn --proxy-headers --forwarded-allow-ips '*'`, de
  modo que la IP del cliente detrás de Nginx se respeta para el rate limiting
  (sin esto, todas las peticiones parecían venir del proxy y el límite por IP
  era evadible/global).

## Contenedores

- El contenedor del backend corre como usuario **no-root** (`appuser`, uid 10001).
- Todos los servicios de compose usan `restart: unless-stopped`.
- Healthchecks: `/health` es **liveness** (no toca la base). `/health/ready` es
  **readiness** (verifica la base con `SELECT 1`, responde 503 si no está lista);
  úsalo como readiness probe en Kubernetes/orquestadores.

## Backups

Los dumps contienen datos personales, metadatos de credenciales y auditoría:
guardarlos en almacenamiento separado y con acceso restringido.

```sh
# Diario a las 02:00 (cron del host); usa el servicio db de compose.
0 2 * * *  BACKUP_DIR=/srv/acp-backups RETENTION_DAYS=14 /path/scripts/backup_db.sh
```

Verificar periódicamente una **restauración** en un entorno aislado; un backup
no probado no es un backup.

## Observabilidad

- Cada request recibe un **id de correlación**: el borde puede mandarlo en
  `X-Request-ID` (se respeta) o el backend lo genera; siempre se devuelve en la
  respuesta y aparece en el log de acceso, para trazar una petición punta a punta.
- `ACP_JSON_LOGS=true` emite los logs como **JSON** (nivel, logger, mensaje,
  request_id, y para el acceso: method/path/status/duration_ms) para ingestión en
  un pipeline de logs; en desarrollo queda en texto plano.
- El request_id también se **persiste en la auditoría** (`audit_logs.request_id`),
  para correlacionar una acción auditada con su línea de acceso.
- **Métricas Prometheus** en `GET /metrics` (contadores de requests por
  método/estado y suma/conteo de latencia). Protegido por `ACP_METRICS_TOKEN`
  (Bearer o `X-Metrics-Token`) cuando está seteado; si no, restringirlo en el
  borde. En multi-worker cada worker lleva sus propios contadores (mismo caveat
  que el rate limiter en memoria).

## Multi-worker (caveat)

El rate limiter de auth es en memoria y la señal inmediata de revocación de
WebSocket es intra-proceso. Con varios workers/procesos, cada uno tiene su
ventana y sus sockets:

- El **lockout por cuenta** está en la base (compartido) y sigue vigente.
- La **revalidación periódica** de la sesión en el WebSocket acota la latencia
  de revocación entre procesos.
- Para un límite duro cross-proceso y fan-out inmediato de revocación, frontear
  con **Redis** (Pub/Sub). Mientras no esté, fijar **un solo worker** de uvicorn.

## Migraciones

`alembic upgrade head` se ejecuta al arrancar el backend en compose. Con varias
réplicas, ejecutar las migraciones como un paso **previo** y único del
despliegue (job dedicado), no en el arranque de cada réplica, para evitar
carreras. La cadena Alembic es lineal (un solo head).
