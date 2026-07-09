# Arquitectura

## Visión general

```
┌────────────────┐     HTTPS/WSS      ┌────────────────────────────┐
│  SPA React     │ ─────────────────▶ │  FastAPI (backend)          │
│  (nginx)       │  /api/v1  /ws      │  ├─ API REST versionada     │
└────────────────┘                    │  ├─ WebSocket de eventos    │
                                      │  ├─ Motor de decisión       │
                                      │  └─ Gateway de hardware ────┼──▶ Placas L04 (UDP 60000)
                                      └────────────┬───────────────┘
                                                   │ SQLAlchemy / Alembic
                                              ┌────▼────┐
                                              │ Postgres│ (SQLite en dev)
                                              └─────────┘
```

## Multi-tenancy

- Cada fila de negocio lleva `organization_id` (mixin `OrgScopedMixin`); todas las consultas filtran por él.
- Los usuarios pertenecen a una organización; `super_admin` puede operar sobre cualquiera pasando `?organization_id=` (validado en `app/core/deps.py::get_org_id`).
- El aislamiento se verifica con tests (`test_tenant_isolation`).

## Modelo de dominio

| Entidad | Rol |
|---|---|
| `Organization` | Tenant del SaaS (plan, estado) |
| `User` | Usuario de la plataforma con rol RBAC |
| `Site` | Ubicación física (zona horaria para horarios) |
| `Controller` | Placa L04: serie, IP, estado online/offline |
| `Door` | 1–4 por placa: modo, tiempos, sensor, anti-passback |
| `Department` / `Cardholder` / `Credential` | Personal y sus tarjetas/PIN |
| `Schedule` + `ScheduleInterval` + `Holiday` | Perfiles horarios semanales y feriados |
| `AccessLevel` + `AccessLevelDoor` | Permisos: puerta + horario, asignados N–N a personas |
| `Event` | Historial/monitoreo en tiempo real |
| `AuditLog` | Auditoría de acciones de usuarios |

## Motor de decisión (`app/services/access_engine.py`)

Orden de evaluación de una lectura de tarjeta (idéntico en espíritu al software de escritorio):

1. La credencial existe y está activa (`unknown_credential`, `credential_inactive`).
2. PIN correcto si la credencial es tarjeta+PIN (`wrong_pin`).
3. Persona activa y dentro de su vigencia (`cardholder_inactive`, `out_of_validity`).
4. Modo de puerta: normalmente abierta → concede; normalmente cerrada → deniega (`door_locked`).
5. Algún nivel de acceso de la persona incluye la puerta (`no_access_level`).
6. La regla es 24/7 (`schedule_id = null`) o el horario permite el momento actual en la zona horaria del sitio, considerando feriados (`out_of_schedule`, `holiday`).

Toda lectura genera un `Event` (concedido o denegado con motivo) que se difunde por WebSocket.

## Tiempo real

`app/services/events.py` mantiene un `ConnectionManager` con las conexiones WebSocket agrupadas por organización. `record_event()` persiste y difunde. El frontend se conecta a `/ws/events?token=<JWT>` y reconecta con backoff.

## Gateway de hardware

Interfaz `ControllerGateway` (`ping`, `open_door`, `sync_time`, `sync_permissions`) con dos implementaciones seleccionadas por `ACP_GATEWAY_MODE`:

- `simulated`: responde siempre; permite demo y tests sin hardware.
- `tcp`: protocolo UDP binario de 64 bytes de las placas L04 (ver [HARDWARE.md](HARDWARE.md)).

## Seguridad

- Contraseñas con bcrypt; JWT HS256 con tokens de acceso (30 min) y refresh (7 días) separados por `type`.
- RBAC por dependencia `require_roles(...)` en cada endpoint.
- Auditoría en cada mutación y login (`app/services/audit.py`).
- CORS configurable; secretos solo por variables de entorno.

## Decisiones

- **SQLite en desarrollo / Postgres en producción**: mismo código, URL por `ACP_DATABASE_URL`.
- **Alembic** para migraciones en producción; `create_all` en dev/tests para agilidad.
- **Eventos en la misma base**: volumen esperado moderado; particionar o mover a una cola es una evolución natural si crece.
