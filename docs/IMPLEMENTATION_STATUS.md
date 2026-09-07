# Estado de implementación — Control de Acceso / Cerradura Magnética

> **Fuente de verdad del "qué está hecho".** Este documento reemplaza cualquier
> afirmación de estado en `DEVELOPMENT_LOG.md` (histórico). Actualizado a partir
> de la auditoría multiagente del 2026-09-06.
>
> - **Rama de trabajo:** `claude/develop` — para el commit exacto, `git log -1`
>   (no fijamos un hash aquí para que no envejezca).
> - **Base:** `main` (`beec044`) **no** contiene este trabajo. Todo vive en la
>   rama de integración = **PR #7**. Nada está fusionado a `main`.
> - **Evidencia de tests:** `pytest tests -q` → **177 passed** en el SHA auditado.
>   Ver `TEST_EVIDENCE.md`.
>
> ---
> ### 🔄 Actualización 2026-09-07 — cola de fixes #11–#20 (todos Draft, CI verde, sin fusionar)
>
> Este documento es el **snapshot de la auditoría** (`b97f5e3`). Desde entonces se
> abrió una cola de PRs de corrección/endurecimiento, **todos verificados en CI y
> sin fusionar** (el continuity log de `AI_HANDOFF.md` es la fuente viva). Deltas:
>
> | PR | Cierra | Antes → Ahora |
> |---|---|---|
> | #11 | **F-2** | `--forwarded-allow-ips *` → configurable, prod rechaza `*` (fail-fast) |
> | #12 | **F-1** | lockout `+=1` no atómico → `UPDATE ... +1 RETURNING` + test de concurrencia |
> | #13 | **F-4** | fingerprint del bridge sin secreto → secreto por-puente hasheado (fail-closed) + migración |
> | #14 | **F-3** | WS sin `Origin` → validación anti-CSWSH |
> | #15 | **P1-6 / R-4** | sin SCA Python → `pip-audit` en CI + `cryptography` sin vulnerabilidades |
> | #16 | **P2-3 / R-2** | revocación no propagada a placa → `REVOKE_CARD` al outbox por controladora (modo bridge) |
> | #17 | **P1-1 / R-1 (rate-limit)** | rate-limit in-memory → `RedisRateLimiter` cross-worker opt-in (fallback in-memory) |
> | #18 | **P0-2 / DOOR-005 / UI-002-dual** | sin UI de doble aprobación → página Aprobaciones + toggle en el editor + infra Vitest |
> | #19 | **P1-1 / R-1 (revocación)** | revocación WS intra-proceso → fan-out Redis Pub/Sub opt-in (revalidación BD sigue de red) |
> | #20 | **P1-2** | migraciones en el arranque del backend → servicio one-shot `migrate` en compose |
>
> **Aún pendientes** tras esta cola: F-5, F-6, F-7, F-8, F-9, F-10, F-11 (seguridad
> P2/P3, sin PR); enforcement real de flags (P0-1, requiere hardware); UI de MFA
> (P1-4); turnos nocturnos (P1-5); y todo lo `BLOCKED_HARDWARE`/`BLOCKED_SPEC`.
> Ver la sección final **"Camino a operativo 100%"**.
> ---

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

- Flags avanzados de puerta: solo se guardan/exhiben, **ningún motor los aplica** (mitigado en UI por #10; enforcement requiere hardware).
- Doble aprobación: ✅ **UI completada en PR #18** (página Aprobaciones + toggle en el editor de puerta). Backend ya estaba.
- MFA/TOTP: backend completo, **sin pantallas** en el SPA (P1-4).
- Turnos nocturnos (que cruzan medianoche): **no soportados** (P1-5).
- Revocación de credencial/persona: efecto online + ✅ **propagación automática a la placa vía outbox en modo bridge (PR #16)**; el efecto físico depende de hardware.
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
| P0-2 | **UI de doble aprobación** | ✅ **RESUELTO — PR #18 (abierto, CI verde):** página **Aprobaciones** (solicitar/aprobar/rechazar, regla de dos personas en UI), toggle "requiere doble aprobación" en el editor de puerta, y "Solicitar apertura" en puertas críticas + infra Vitest (5 component tests). | `frontend/src/pages/ApprovalsPage.tsx`, `DoorsPage.tsx`, `api/index.ts` |
| P0-3 | **Backup/restore endurecido + probado** | ✅ **Corregido en PR #9 (abierto):** restore como **máquina de estados** con swap no destructivo, reconciliación por señal desde la verdad del servidor, journal en el lock, `--release-lock`/`--drop-recovery` explícitos; 26 tests fake + **prueba real en PostgreSQL en CI verde** (round-trip, aborto por validación, rollback post-swap) + ShellCheck. Estado: **PR #9 abierto**, `Probado en CI`. Falta el **restore drill autorizado en staging** (distinto del test de CI descartable). | `scripts/`, `BACKUP_RESTORE.md` |

### P1 — Robustez / operación

| # | Ítem | Por qué |
|---|---|---|
| P1-1 | **Redis para rate-limit, fan-out de revocación WS y métricas** | ✅ **RESUELTO (rate-limit + revocación) — PR #17 y #19 (abiertos, CI verde):** `RedisRateLimiter` cross-worker opt-in + `revocation_bus` (Pub/Sub) opt-in por `ACP_REDIS_URL`, con fallback in-memory. *Métricas por-worker siguen como caveat (P2-6).* |
| P1-2 | **Migraciones como job previo (no en arranque) para réplicas** | ✅ **RESUELTO — PR #20 (abierto, CI verde):** servicio one-shot `migrate` en compose; backend `depends_on: service_completed_successfully`. |
| P1-3 | **TLS cableado en el borde** | Implementado (`frontend/nginx.tls.conf`) y documentado (`DEPLOYMENT.md`); su activación (montar cert + reemplazar config) es un paso operativo del despliegue. |
| P1-4 | **UI de MFA/TOTP** | ⏳ Pendiente. Backend completo sin pantallas para activar/usar. |
| P1-5 | **Turnos nocturnos en asistencia** | ⏳ Pendiente. Modelo `Shift` sin flag overnight; un turno 22:00→06:00 parte el par entrada/salida. |
| P1-6 | **pip-audit en CI backend** | ✅ **RESUELTO — PR #15 (abierto, CI verde):** `pip-audit -r requirements.txt` en el job backend + `cryptography` sin vulnerabilidades. |

### P2 — Completitud funcional

| # | Ítem |
|---|---|
| P2-1 | Dry-run de importación en el SPA |
| P2-2 | Export CSV server-side de reportes (no solo filas paginadas) |
| P2-3 | ✅ **RESUELTO — PR #16:** propagación de revocaciones a la placa (`REVOKE_CARD` al outbox por controladora en modo bridge; efecto físico depende de hardware) |
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
| #11 | `claude/sec-f2-forwarded-allow-ips` | `claude/develop` | Draft, CI verde. **F-2**. |
| #12 | `claude/sec-f1-atomic-lockout` | `claude/develop` | Draft, CI verde. **F-1**. |
| #13 | `claude/sec-f4-bridge-secret` | `claude/develop` | Draft, CI verde. **F-4** (+ migración `f1a2b3c4d5e6`). |
| #14 | `claude/sec-f3-ws-origin` | `claude/develop` | Draft, CI verde. **F-3**. |
| #15 | `claude/sec-pip-audit` | `claude/develop` | Draft, CI verde. **pip-audit** + `cryptography`. |
| #16 | `claude/sec-card-revocation-outbox` | `claude/develop` | Draft, CI verde. **REVOKE_CARD → outbox** (+ migración `d1e2f3a4b5c6`). |
| #17 | `claude/sec-redis-ratelimit` | `claude/develop` | Draft, CI verde. **Redis rate-limit** opt-in. |
| #18 | `claude/frontend-dual-approval` | `claude/develop` | Draft, CI verde. **UI doble aprobación** + Vitest. |
| #19 | `claude/sec-redis-revocation-bus` | `claude/sec-redis-ratelimit` (#17) | Draft, CI verde. **Redis Pub/Sub revocación** (apilado en #17). |
| #20 | `claude/deploy-hardening` | `claude/develop` | Draft, CI verde. **Migraciones como job** en compose. |
| #3–#6 | `claude/phase1-*`, `claude/access-control-saas-refactor-6wm329` | `main` | Abiertos, contenidos en #7 (verificado por `git merge-base`); **no cerrados**. |

> **Solapes a reconciliar al integrar** (cada PR es lineal por sí mismo; el
> conflicto solo aparece al fusionar varios a `develop`): migraciones apiladas
> #13 (`f1a2b3c4d5e6`) y #16 (`d1e2f3a4b5c6`) cuelgan ambas de `e0f1a2b3c4d5`
> → re-encadenar una; infra frontend/CI #10 y #18 (versión de Vite/Vitest, pasos
> de CI); apilado Redis #17 → #19; y el `command:` de compose #11 (F-2) + #20
> (job de migración).

## Hallazgos de seguridad pendientes (de PRs de fix separados)

La auditoría independiente arrojó **0 P0, 0 P1, 5 P2, 6 P3** (F-1…F-11 en `SECURITY.md`).
**Corregidos (PRs abiertos, CI verde):** F-1 (#12), F-2 (#11), F-3 (#14), F-4 (#13).
**Pendientes (sin PR):** F-5 (MFA recovery/reset — P2), F-6 (nº de tarjeta en claro en errores del importador — P3), F-7 (`/metrics` abierto + compare no constante — P3), F-8 (enumeración de usuarios/tenants — P3), F-9 (`get_or_404` IDOR latente — P3), F-10 (inbox: IntegrityError por-fila — P3), F-11 (apertura remota no idempotente por `Idempotency-Key` — P3).

Ver `AI_HANDOFF.md` para el índice maestro y `REQUIREMENTS_TRACEABILITY.md` para la matriz completa de requisitos.

## Camino a operativo 100%

> Qué falta, exactamente, para declarar el sistema **100% operativo y funcional**
> — según el proyecto solicitado **y** la auditoría funcional. Ordenado por peso.
> `[ ]` pendiente · `[~]` hecho a nivel software (en PR Draft, falta integrar/validar).

### A. Bloqueantes duros (sin esto no es "operativo")
- [ ] **Integración y despliegue.** Nada está en `main`; todo son PRs Draft. Integrar
      #7 + fixes #9–#20 a `claude/develop` (reconciliando los solapes de arriba),
      correr la suite sobre el árbol integrado, y luego a `main`. **Requiere
      autorización explícita para fusionar.**
- [ ] **Validación contra hardware real (N3000/L04).** Es el mayor faltante para un
      control de acceso *físico*. Hoy **NADA** está verificado en placa
      (`HARDWARE_STATUS.md`): confirmar el wire protocol real, ajustar el adaptador
      detrás de `ControllerGateway`, validar no-destructivo con autorización. Sin
      esto, abrir/validar puertas solo funciona en `simulated`.

### B. Enforcement de flags avanzados (ligado a B-hardware)
- [ ] **anti-passback / interlock / multicard / first-card-open aplicados.** Hoy solo
      se persisten/muestran (mitigado en UI por #10). Reemplazar la constante
      `ADVANCED_FLAGS_ENFORCED` por **capacidades reales** del backend/controladora
      (UI fail-closed si no las conoce) e implementar el enforcement — requiere hardware.

### C. Funcionalidad de producto faltante
- [~] UI de doble aprobación — **PR #18** (falta integrar).
- [~] Propagación de revocación a la placa — **PR #16** (falta integrar; efecto físico depende de hardware).
- [ ] **UI de MFA/TOTP** (P1-4): activar/usar/deshabilitar desde el SPA + (F-5) recovery codes / reset por admin.
- [ ] **Turnos nocturnos** en asistencia (P1-5).
- [ ] Dry-run de importación en el SPA (P2-1); export CSV server-side completo (P2-2).
- [ ] i18n (P3-4); tests **E2E** de frontend (P3-5).

### D. Seguridad restante (auditoría F-1…F-11)
- [~] F-1/F-2/F-3/F-4 — PRs #12/#11/#14/#13 (falta integrar).
- [ ] **F-5** (P2): MFA recovery codes / reset admin.
- [ ] **F-6, F-7, F-8, F-9, F-10, F-11** (P3): higiene (ver `SECURITY.md`).
- [ ] Re-verificar los requisitos aún `OPEN_PR_UNVERIFIED` (AUTH-003 CSRF/fallback WS, AUTH-004) tras integrar los fixes.

### E. Operación / despliegue
- [~] Redis rate-limit (#17) + revocación (#19); migraciones-como-job (#20); TLS implementado/documentado (falta integrar/activar).
- [ ] **Restore drill autorizado en staging** (distinto del test descartable de CI) — `BACKUP_RESTORE.md`.
- [ ] Provisión de secretos reales; healthchecks de compose backend/frontend (P2-5); alertas sobre métricas (P2-6); métricas cross-worker; escaneo de imágenes (P3-2); CD (P3-6).

### F. Cierre documental / auditoría
- [~] Este doc, `SECURITY.md`, `REQUIREMENTS_TRACEABILITY.md`, `HARDWARE_STATUS.md` actualizados a la cola #11–#20 (2026-09-07).
- [ ] Rehacer la matriz de trazabilidad **al SHA integrado** una vez fusionado a `develop`, y correr la auditoría independiente sobre ese árbol final.

> **Veredicto honesto:** la **plataforma web (SaaS)** está funcionalmente
> completa y probada en CI, pero **en PRs sin fusionar**. Como **control de acceso
> físico**, está **bloqueada por hardware**. No es 100% operativo hasta cerrar A
> (integración + hardware) como mínimo; B–F son para completitud plena del producto.
