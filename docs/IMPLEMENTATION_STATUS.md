# Estado de implementación — Control de Acceso / Cerradura Magnética

> **Fuente de verdad del "qué está hecho".** Este documento reemplaza cualquier
> afirmación de estado en `DEVELOPMENT_LOG.md` (histórico). Actualizado a partir
> de la auditoría multiagente del 2026-09-06.
>
> - **Rama de trabajo:** `claude/develop` — para el commit exacto, `git log -1`
>   (no fijamos un hash aquí para que no envejezca).
> - **Base:** `main` (`beec044`) **no** contiene este trabajo. Todo vive en la
>   rama de integración = **PR #7**. Nada está fusionado a `main`.
> - **Evidencia de tests:** `pytest tests -q` → **177 passed** (verificado en la
>   auditoría). Ver `TEST_EVIDENCE.md`.

## Taxonomía de estados

| Estado | Significado |
|---|---|
| `OPEN_PR_VERIFIED` | Existe en la rama y se verificó leyendo el código y/o con un test verde. **No está en `main`.** |
| `OPEN_PR_UNVERIFIED` | Existe pero no se confirmó su efecto real. |
| `PARTIAL` | Implementado a medias (falta enforcement, UI, o cobertura). |
| `SIMULATED_ONLY` | Funciona solo contra el gateway `simulated`. |
| `BLOCKED_HARDWARE` | Requiere una placa N3000/L04 real para validarse. |
| `BLOCKED_SPEC` | Requiere el wire protocol real, hoy no disponible. |
| `PLANNED` | En hoja de ruta, sin implementar. |

> **Regla del proyecto:** un test verde **no** equivale a validación contra
> hardware físico. Nada que toque la placa está verificado en hardware real.

## Estado por fase (vertiente plataforma)

| Fase | Alcance | Estado plataforma | Verificado en hardware | Evidencia |
|---|---|---|---|---|
| **1 — Seguridad web** | Sesiones server-side, refresh rotativo, cookies/CSRF, PIN cifrado, hardening prod, rate-limit/lockout, MFA, doble aprobación | `OPEN_PR_VERIFIED` | n/a | `SECURITY.md`; tests `test_sessions` (22), `test_cookie_auth` (8), `test_pin_encryption` (5), `test_production_safety` (8), `test_login_protection` (5), `test_mfa` (5), `test_dual_approval` (10) |
| **2 — Codec de protocolo** | Frame de 64 bytes aislado, builders/parsers `FUNC_*`, BCD/fecha, `CardRecord`, tarjeta 64-bit, virtual card number de teclado | `OPEN_PR_VERIFIED` (codec puro) / `BLOCKED_SPEC` (placa real) | ❌ | `app/services/protocol/`; `test_protocol_codec` (13), `test_wiegand` (2); `HARDWARE_STATUS.md` |
| **3 — Puente local (outbox)** | Cola `gateway_commands`, claim con lease/CAS, ack idempotente, API del puente con auth por fingerprint mTLS, dispatch tras flag | `OPEN_PR_VERIFIED` (contrato plataforma) / `BLOCKED_HARDWARE` (daemon puente real) | ❌ | `app/services/gateway_outbox.py`, `gateway_effects.py`, `app/api/v1/gateway_bridge.py`; `test_gateway_outbox` (7), `test_gateway_bridge` (14), `test_command_dispatch` (4); `GATEWAY_BRIDGE.md` |
| **4 — Flags avanzados de puerta** | anti-passback / interlock / multicard / first-card-open | `PARTIAL` (solo persistencia + UI, **sin enforcement**) | ❌ | `app/models/infrastructure.py`, `app/schemas/infrastructure.py`; **cero referencias en `access_engine.py`** |
| **5 — Inbox de eventos de placa** | `POST /gateway/events` idempotente (dedup por `event_uid`), enmascarado, difusión | `OPEN_PR_VERIFIED` (endpoint) / `BLOCKED_HARDWARE` (productor real) | ❌ | `app/services/gateway_inbox.py`; `test_gateway_bridge`; `GATEWAY_BRIDGE.md` |
| **6 — Importación por etapas** | CSV + MDB con plan/dry-run, validación fila por fila, sin sobrescritura silenciosa | `OPEN_PR_VERIFIED` (backend) / `PARTIAL` (frontend sin dry-run) | n/a | `app/services/importer.py`, `legacy_mdb.py`; `test_import` (7), `test_mdb_import` (4) |
| **7 — Observabilidad** | request-id (ContextVar, `X-Request-ID`), logs JSON, métricas Prometheus `/metrics`, correlación en auditoría | `OPEN_PR_VERIFIED` | n/a | `app/core/observability.py`, `metrics.py`; `test_observability` (6); migración `e0f1a2b3c4d5` |

## Dominio funcional (resumen; detalle en `REQUIREMENTS_TRACEABILITY.md`)

**Verificado y correcto (no requiere acción):**

- Aislamiento multi-tenant por `organization_id` (`deps.py:69-90`).
- Suspensión de empresa corta sesiones y WebSockets vivos (`organizations.py:69-85`, `deps.py:43-44`).
- RBAC 4 roles; super_admin platform-level no secuestrable.
- PIN obligatorio en credenciales PIN-only y card+PIN (`access_engine.py:148-153`); comparación en tiempo constante.
- PIN cifrado en reposo con llave externa a la DB (Fernet + HKDF).
- Nº de tarjeta enmascarado en eventos/auditoría (últimos 4).
- Horarios y feriados evaluados en la zona horaria del sitio.
- Difusión de eventos solo tras `commit` (nada de eventos fantasma en rollback).
- Asistencia con conversión UTC→local antes de agrupar.

**Incompleto (ver backlog abajo):**

- Flags avanzados de puerta: solo se guardan/exhiben, **ningún motor los aplica**.
- Doble aprobación: backend completo, **sin UI** en el SPA; el flag ni siquiera es seteable desde la interfaz.
- MFA/TOTP: backend completo, **sin pantallas** en el SPA.
- Turnos nocturnos (que cruzan medianoche): **no soportados**.
- Revocación de credencial/persona: surte efecto online, **no se propaga automáticamente a la placa**.
- Dry-run de importación: soportado en backend, el SPA importa directo.
- Export CSV de reportes: client-side, limitado a las filas paginadas cargadas.
- i18n: inexistente; strings en español hardcodeados.
- Tests E2E de frontend: ausentes.

## Backlog priorizado (P0–P3)

> Prioridad = riesgo × impacto. **Nada de esto se implementa sin que el líder
> asigne la tarea a un dev y sin tests+docs.** Los ítems que tocan hardware/
> producción quedan bloqueados por autorización explícita del dueño.

### P0 — Corrección/seguridad, seguros de implementar

| # | Ítem | Por qué | Dónde |
|---|---|---|---|
| P0-1 | **Falsa seguridad de flags mitigada en UI** (enforcement real sigue pendiente) | La UI ya NO presenta anti-passback/interlock/multicard/first-card como activos: badges "no aplicado", banner y **edición deshabilitada** (`ADVANCED_FLAGS_ENFORCED=false`). El **enforcement en el motor** sigue pendiente (requiere hardware). Estado: **PR #10 abierto** (mitigación UI); enforcement `PLANNED`. | `frontend/lib/doorFlags.ts`, `DoorsPage.tsx`, `ControllersPage.tsx` |
| P0-2 | **UI de doble aprobación** | El backend (CONFIRMADO por auditoría) rechaza (409) la apertura de puertas críticas y el SPA no ofrece forma de completar el flujo → puerta crítica inoperable desde la interfaz. Estado: `PLANNED` (pendiente). | `frontend/src/api/index.ts`, nueva página |
| P0-3 | **Backup/restore endurecido + probado** | ✅ **Corregido en PR #9 (abierto):** backup ya no oculta fallos de `pg_dump`; restore con swap **no destructivo** + rollback + mutex; 22 tests fake + test real en PostgreSQL en CI. Estado: **PR #9 abierto**, pendiente de confirmar CI real y prueba en entorno autorizado. | `scripts/`, `BACKUP_RESTORE.md` |

### P1 — Robustez / operación

| # | Ítem | Por qué |
|---|---|---|
| P1-1 | **Redis para rate-limit, fan-out de revocación WS y métricas** | Hoy todo es en memoria por-proceso → fuerza un solo worker; escalar rompe el límite de auth y la revocación inmediata. |
| P1-2 | **Migraciones como job previo (no en arranque) para réplicas** | `alembic upgrade head` corre en el arranque del backend; con réplicas = carrera. |
| P1-3 | **TLS cableado en el borde** | `nginx.tls.conf` existe pero es manual; sin HTTPS real el login con `cookie_secure=true` queda inutilizable. |
| P1-4 | **UI de MFA/TOTP** | Backend completo sin pantallas para activar/usar. |
| P1-5 | **Turnos nocturnos en asistencia** | Modelo `Shift` sin flag overnight; un turno 22:00→06:00 parte el par entrada/salida. |
| P1-6 | **pip-audit en CI backend** | El frontend audita deps; Python no tiene SCA. |

### P2 — Completitud funcional

| # | Ítem |
|---|---|
| P2-1 | Dry-run de importación en el SPA |
| P2-2 | Export CSV server-side de reportes (no solo filas paginadas) |
| P2-3 | Propagación de revocaciones a la placa (baja explícita hacia el puente) |
| P2-4 | Downgrade de migraciones ejercido en CI (upgrade→downgrade→upgrade) |
| P2-5 | Healthchecks de compose para backend/frontend + `condition: service_healthy` |
| P2-6 | Alertas mínimas sobre métricas (readiness 503, 5xx, lockouts, latencia) |

### P3 — Endurecimiento / futuro

| # | Ítem |
|---|---|
| P3-1 | Lockfile Python con hashes / builds reproducibles |
| P3-2 | Escaneo de imágenes (Trivy/Grype) |
| P3-3 | Frontend nginx no-root + healthcheck |
| P3-4 | i18n (marco + catálogos) |
| P3-5 | Tests E2E del SPA (Playwright/Cypress) |
| P3-6 | CD (build/push de imágenes versionadas) |

### Bloqueado por hardware / spec (no se toca sin autorización + placa real)

- Confirmar el **wire protocol N3000 real** (SDK del fabricante o captura PCAP) — hoy el codec usa un layout público UHPPOTE-compatible **no verificado** (`BLOCKED_SPEC`).
- Validar el **driver `l04_udp`** contra placa real (`BLOCKED_HARDWARE`).
- Daemon puente real (Windows/Linux) + eventos físicos reales (`BLOCKED_HARDWARE`).
- Alta de tarjeta por lector USB WG1028; módulos de nicho del legacy (Meal/Patrol/Meeting) (`PLANNED` / `BLOCKED_HARDWARE`).

## Estado de PRs (todos Draft, sin fusionar)

| PR | Rama | Base | Estado |
|---|---|---|---|
| #7 | `claude/develop` | `main` | Draft. Integración de Fases 1–7. **No fusionar** hasta auditar #7. |
| #8 | `claude/docs-consolidation` | `claude/develop` | Draft. Documentación canónica (este doc y los demás de estado). |
| #9 | `claude/backup-restore-hardening` | `claude/develop` | Draft. Backup/restore endurecido + tests (fakes + PG real en CI). |
| #10 | `claude/frontend-door-flags-advisory` | `claude/develop` | Draft. Flags "no aplicado" + edición deshabilitada + infra de tests. |
| #3–#6 | `claude/phase1-*`, `claude/access-control-saas-refactor-6wm329` | `main` | Abiertos, contenidos en #7 (verificado por `git merge-base`); **no cerrados**. |

## Hallazgos de seguridad pendientes (de PRs de fix separados)

La auditoría independiente arrojó **0 P0, 0 P1, 5 P2, 6 P3** (F-1…F-11 en `SECURITY.md`).
Ninguno tiene aún PR de corrección; prioridad sugerida: **F-2** (`--forwarded-allow-ips *`) y **F-1** (carrera de lockout), luego F-4/F-3, luego F-5.

Ver `AI_HANDOFF.md` para el índice maestro y `REQUIREMENTS_TRACEABILITY.md` para la matriz completa de requisitos.
