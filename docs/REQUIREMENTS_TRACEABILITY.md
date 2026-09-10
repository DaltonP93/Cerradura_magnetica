# Matriz de trazabilidad de requisitos — Control de Acceso

> Trazabilidad con **IDs estables**. Evidencia anclada al SHA auditado
> **`b97f5e3c89d4735e272c17be705a99877accf908`** (rama `claude/develop`, PR #7).
> Las rutas son completas (`backend/app/...`); las referencias de línea pueden
> cambiar — el ancla confiable es el SHA + archivo/función.
>
> Estados definidos en `IMPLEMENTATION_STATUS.md`. **Todo es `OPEN_PR_*`** (nada
> en `main`). Donde la seguridad no fue verificada de forma independiente, el
> estado es `OPEN_PR_UNVERIFIED`, **no** `OPEN_PR_VERIFIED` (la auditoría de
> seguridad independiente está pendiente; ver `SECURITY.md`).
>
> Convención de capa: **[P]** plataforma · **[S]** simulador · **[H]** hardware real.

> **🔄 Actualización 2026-09-07 — deltas por la cola de fixes #11–#20 (Draft, CI verde, sin fusionar).**
> Las filas de abajo están ancladas al SHA auditado `b97f5e3`; estos PRs aún **no
> están en `develop`**, así que la matriz se **rehará al SHA integrado** cuando se
> fusionen. Deltas a nivel requisito:
> - **AUTH-004** (rate-limit + lockout): F-1 lockout ahora atómico (**#12**); límite por IP cross-worker con Redis opt-in (**#17**). Carrera de lockout cerrada.
> - **AUTH-005 / UI-002** (MFA): sigue **PARTIAL** (backend ok, **sin UI**); F-5 (recovery/reset) pendiente.
> - **AUTH-001 / TENANT-002** ("Faltante: multi-worker"): cubierto por Redis Pub/Sub de revocación (**#19**) + rate-limit (**#17**), opt-in.
> - **DOOR-004** (flags aplicados): sigue `PARTIAL`; UI mitigada (#10), enforcement pendiente (hardware).
> - **DOOR-005** (`requires_dual_approval` + flujo): ✅ **UI completada (#18)** — toggle en el editor + página Aprobaciones.
> - **AUTH-003 (WS Origin/CSWSH):** F-3 añadido (**#14**). **Bridge auth:** secreto por-puente (F-4, **#13**).
> - **Credenciales**: revocación se propaga al outbox (**#16**). **Importador (F-6)** y **`get_or_404` (F-9)**: pendientes.
> Detalle y estado global en `IMPLEMENTATION_STATUS.md` §"Camino a operativo 100%".

## Multi-tenant

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| TENANT-001 | Multi-tenant [P] | Aislamiento por `organization_id` en todas las consultas de negocio | `OPEN_PR_VERIFIED` | `backend/app/core/deps.py` (`get_org_id`), `OrgScopedMixin` en modelos. **Auditoría independiente: sin IDOR explotable** (recorrió `api/v1/*.py`); único hueco *latente* F-9 (`get_or_404`). | #7 | `backend/tests/test_platform.py` (8) | Endurecer F-9 (PR separado) | Ningún handler devuelve filas de otra org |
| TENANT-002 | Multi-tenant [P] | Suspensión de empresa corta sesiones y WS vivos | `OPEN_PR_VERIFIED` | `backend/app/api/v1/organizations.py` (`revoke_org_sessions`), `backend/app/core/deps.py` (`organization_active`) | #7 | `test_sessions.py` | Fan-out inmediato multi-worker (Redis) | Tras suspender, siguiente request 403 y socket cerrado |

## Autenticación / sesiones

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| AUTH-001 | Auth [P] | Sesiones server-side + refresh rotativo + detección de reuso full-history | `OPEN_PR_VERIFIED` | `backend/app/models/auth_session.py`, `backend/app/services/sessions.py` | #7 | `test_sessions.py` (22) | Certificación multi-worker (Redis) | Replay de cualquier generación revoca la familia |
| AUTH-002 | Auth [P] | Binding sesión ↔ `sub` del JWT (`session.user_id` == JWT sub) | `OPEN_PR_VERIFIED` | `backend/app/core/deps.py`, `backend/app/api/v1/ws.py` (`get_active_session(db, session_id, subject)`); `rotate_refresh` rechaza si `user_id != expected`. **Auditoría independiente: CONFIRMADO.** | #7 | `test_sessions.py` | — | Un token cuyo `sub` no coincide con la sesión es rechazado |
| AUTH-003 | Auth [P] | Cookies HttpOnly/Secure/SameSite + CSRF double-submit; sin JWT en localStorage/URL | `OPEN_PR_UNVERIFIED` | `backend/app/core/cookies.py`, `backend/app/core/csrf.py`, `frontend/src/api/client.ts` | #7 | `test_cookie_auth.py` (8) | Revisión CSRF/fallback WS por seguridad | CSRF rechaza sin token doble; WS autentica por cookie |
| AUTH-004 | Auth [P] | Rate-limit + lockout de cuenta por fuerza bruta | `OPEN_PR_VERIFIED` (con fixes #12/#17) | `backend/app/core/ratelimit.py`, `users.locked_until`; **F-1 atómico (#12)**, **Redis opt-in (#17)** | #7, #12, #17 | `test_login_protection.py` (+concurrencia), `test_redis_ratelimit.py` | Re-verificación independiente tras integrar | Tras N fallos la cuenta se bloquea; límite por IP; sin lost-update en el contador |
| AUTH-005 | Auth [P] | MFA TOTP (setup/enable/disable) | `PARTIAL` | Backend `backend/app/api/v1/auth.py`, `backend/app/core/totp.py`; **sin UI** | #7 | `test_mfa.py` (5) | UI (UI-002); códigos de recuperación (revisar) | Admin activa/usa TOTP desde el SPA |

## RBAC / permisos

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| RBAC-001 | RBAC [P] | 4 roles (super_admin/admin/operator/viewer) por endpoint | `OPEN_PR_VERIFIED` | `backend/app/core/deps.py` (`require_roles`), `backend/app/models/tenancy.py`. **Auditoría independiente: coherente** — ningún endpoint mutante sin guarda de rol. | #7 | dispersos | — | Cada endpoint mutante exige rol adecuado |
| RBAC-002 | RBAC [P] | super_admin platform-level no secuestrable por admin de org | `OPEN_PR_VERIFIED` | `backend/app/seed.py` (superadmin `organization_id=None`), fix `b6690ff` | #7 | — | — | Un admin de org nunca escala a super_admin |

## Personas y credenciales

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| PEOPLE-001 | Credenciales [P] | PIN-only y card+PIN exigen PIN (sin bypass por nº de tarjeta) | `OPEN_PR_VERIFIED` | `backend/app/services/access_engine.py` (`_PIN_REQUIRED`, `_pin_matches`) | #7 | `test_access_flow.py` | — | Sin PIN correcto → `WRONG_PIN` en ambos tipos |
| SEC-001 | Seguridad [P] | PIN recuperable cifrado en reposo, llave externa a la DB | `OPEN_PR_VERIFIED` | `backend/app/core/crypto.py` (Fernet+HKDF), `EncryptedString` | #7 | `test_pin_encryption.py` (5) | Rotación de llave automatizada | Ciphertext en DB; API nunca expone PIN |
| SEC-002 | Seguridad [P] | Nº de tarjeta enmascarado en eventos/auditoría | `OPEN_PR_VERIFIED` | `backend/app/core/masking.py`, `backend/app/services/access_engine.py` | #7 | `test_masking.py` (3) | — | Eventos/auditoría guardan últimos 4 |
| SEC-003 | Seguridad [P] | Sin fuga de PIN/tarjeta/PII/tokens en errores, logs y auditoría | `OPEN_PR_VERIFIED` | `backend/app/services/audit.py`, `backend/app/core/observability.py`, `core/masking.py`. **Auditoría independiente: sin fuga** (tarjetas enmascaradas, PIN cifrado, solo hashes de tokens); única excepción F-6 (nº de tarjeta en claro en errores del importador). | #7 | `test_masking.py` | Corregir F-6 (PR separado) | Auditoría independiente no encuentra fuga (salvo F-6) |
| PEOPLE-002 | Credenciales [P] | Virtual card number de teclado (PIN como nº de 10 dígitos) | `OPEN_PR_VERIFIED` (plataforma) | `backend/app/services/wiegand.py`, `backend/app/services/access_engine.py` | #7, `b97f5e3` | `test_wiegand.py` (2) | Verificación con lectora real [H] | Nº de 10 dígitos resuelve a su credencial PIN |
| PEOPLE-003 | Credenciales [H] | Alta por lector USB WG1028 / por rango | `PLANNED` | `docs/LEGACY.md` (roadmap) | — | — | Hardware en el puesto | — |

## Puertas / controladoras

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| DOOR-001 | Puertas [P] | CRUD controladoras (S/N, IP, puerto 60000, 4 puertas) | `OPEN_PR_VERIFIED` | `backend/app/api/v1/controllers.py` | #7 | `test_infrastructure.py` (7) | — | Alta con S/N único crea 4 puertas |
| DOOR-002 | Puertas [S] | Consola Check/Adjust Time/Upload | `SIMULATED_ONLY` | `backend/app/api/v1/controllers.py`, `backend/app/services/gateway/simulated.py` | #7 | `test_infrastructure.py` | Adaptador real [H] | Sobre `simulated` responde OK |
| DOOR-003 | Puertas [S] | Apertura remota con evento + auditoría | `SIMULATED_ONLY` | `backend/app/api/v1/doors.py` | #7 | `test_infrastructure.py` | Apertura física [H] | Genera evento/auditoría; no abre físicamente |
| DOOR-004 | Puertas [P] | Flags avanzados (anti-passback/interlock/multicard/first-card) **aplicados** | `PARTIAL` (solo persistencia) | `backend/app/models/infrastructure.py`, `backend/app/schemas/infrastructure.py`; **cero refs en `access_engine.py`** | #7 | — | Enforcement (P0-1); mientras tanto marcarlos "no aplicado" en UI (UI-003) | El motor aplica cada flag con estado en tiempo real |
| DOOR-005 | Puertas [P] | `requires_dual_approval` configurable por puerta + flujo completo | `OPEN_PR_VERIFIED` (con UI #18) | Backend `backend/app/api/v1/doors.py`; **UI: toggle en el editor + página Aprobaciones (#18)** | #7, #18 | `test_dual_approval.py` (10), `ApprovalsPage.test.tsx` (5) | Integrar #18 | Marcar puerta crítica y completar aprobación desde la interfaz |

## Horarios / feriados

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| SCHED-001 | Horarios [P] | Horarios semanales + niveles de acceso N-a-N | `OPEN_PR_VERIFIED` | `backend/app/models/access.py`, `backend/app/services/access_engine.py` | #7 | `test_access_flow.py` (15) | Perfiles a nivel placa [H] | Regla 24/7 concede; fuera de intervalo deniega |
| SCHED-002 | Horarios [P] | Evaluación en zona horaria del sitio | `OPEN_PR_VERIFIED` | `backend/app/services/access_engine.py` (`_local_now`) | #7 | `test_access_flow.py` | — | Horario en hora local del sitio |
| SCHED-003 | Feriados [P] | Feriados excluyen acceso salvo `allow_on_holidays` | `OPEN_PR_VERIFIED` | `backend/app/services/access_engine.py` (`_schedule_allows`) | #7 | `test_access_flow.py` | — | En feriado sin flag, deniega |

## Eventos / monitoreo

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| EVT-001 | Eventos [P] | Registro + difusión WS por org | `OPEN_PR_VERIFIED` | `backend/app/services/events.py`, `backend/app/api/v1/ws.py` | #7 | `test_event_broadcast.py` (2) | Fan-out multi-worker (Redis) | Cada evento se persiste y emite a su org |
| EVT-002 | Eventos [P] | Difusión solo tras commit (nada en rollback) | `OPEN_PR_VERIFIED` | `backend/app/services/events.py` (`after_commit`/`after_rollback`), fix `5a95982` | #7 | `test_event_broadcast.py` | — | Rollback nunca difunde |
| EVT-003 | Eventos [P] | Reconexión WS acotada ante sesión revocada (frontend) | `OPEN_PR_UNVERIFIED` | `frontend/src/...`, fix `ed91d2b` | #7 | — | Re-verificación frontend | Sin bucle infinito de reconexión |

## Doble aprobación

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| DA-001 | Doble aprob. [P] | Two-person rule en puertas críticas (backend) | `OPEN_PR_VERIFIED` | `backend/app/services/dual_approval.py` (`claim_for_approval` CAS `UPDATE ... WHERE status=PENDING AND expires_at>now` + `rowcount==1`, self-approve 403, TTL, fail-closed). **Auditoría independiente: CONFIRMADO** — dos aprobadores concurrentes NO ejecutan dos aperturas. | #7 | `test_dual_approval.py` (10) | UI (UI-001) | Solo un 2º operador abre; carreras no abren dos veces |
| UI-001 | Doble aprob. [P] | UI crear/aprobar/rechazar solicitud | `PARTIAL` (sin frontend) | `frontend/src/api/index.ts` (solo `open`) | #7 | — | Página en el SPA (bloqueada hasta auditar DA-001) | Un 2º operador completa el flujo desde la UI |

## Asistencia

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| ATT-001 | Asistencia [P] | Reporte con turnos/tolerancias/licencias/feriados/fichaje | `OPEN_PR_VERIFIED` | `backend/app/services/attendance.py`, `backend/app/api/v1/attendance.py` | #7 | `test_attendance.py` (12) | Ver ATT-003 | Estados por día correctos |
| ATT-002 | Asistencia [P] | Zona horaria explícita (UTC→local antes de agrupar) | `OPEN_PR_VERIFIED` | `backend/app/services/attendance.py` | #7, `15a8242` | `test_attendance.py` | — | Marcas convertidas a local antes de agrupar |
| ATT-003 | Asistencia [P] | Turnos nocturnos (cruzan medianoche) | `PARTIAL` (no soportado) | `backend/app/models/attendance.py` (`Shift` Time plano) | #7 | — | Flag overnight + lógica (P1-5) | Turno 22:00→06:00 empareja entrada/salida |
| ATT-004 | Asistencia [P] | Fichaje manual correctivo (aware→UTC) | `OPEN_PR_VERIFIED` | `backend/app/api/v1/attendance.py` (`ManualSign`) | #7 | `test_attendance.py` | — | Fichaje manual aparece como marca del día |
| ATT-005 | Asistencia [P] | Historial (cierres de período inmutables) | `PARTIAL` | Recomputado por rango; `MAX_RANGE_DAYS=92` | #7 | `test_attendance.py` | Snapshots/cierres | Período cerrado inmutable consultable |

## Importación legacy

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| IMPORT-001 | Importación [P] | CSV por etapas (plan/apply) + dry-run, validación fila por fila | `OPEN_PR_VERIFIED` (backend) / `PARTIAL` (UI) | `backend/app/services/importer.py`, `backend/app/api/v1/cardholders.py` | #7 | `test_import.py` (7) | Dry-run en UI (UI-004) | Backend valida y reporta; UI previsualiza |
| IMPORT-002 | Importación [P] | MDB con detección de tabla + dry-run | `OPEN_PR_VERIFIED` (backend) / `PARTIAL` (UI) | `backend/app/services/legacy_mdb.py` | #7, `aab9b32` | `test_mdb_import.py` (4) | `mdbtools` en server; UI | Detecta tabla y valida antes de persistir |

## Reportes / UI

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| REPORT-001 | Reportes [P] | Reporte de eventos con filtros + export CSV completo | `PARTIAL` | Backend `backend/app/api/v1/events.py`; export client-side (`frontend/src/pages/ReportsPage.tsx`) | #7 | — | Export server-side (P2-2) | Export cubre todo el resultado, no solo lo paginado |
| UI-002 | UI [P] | Pantallas de MFA en el SPA | `PARTIAL` (falta) | `frontend/src/api/index.ts` sin `mfa` | #7 | — | Ver AUTH-005 | — |
| UI-003 | UI [P] | Flags de puerta/controladora mostrados "no aplicado/experimental" + edición deshabilitada (evitar falsa seguridad) | `OPEN_PR_VERIFIED` (Probado en CI) | `frontend/src/lib/doorFlags.ts`, `DoorsPage.tsx`, `ControllersPage.tsx` (badges ámbar, banner, controles deshabilitados con `ADVANCED_FLAGS_ENFORCED=false`) | **PR #10** | `doorFlags.test.ts`, `DoorsPage.test.tsx`, `ControllersPage.test.tsx` | **Seguimiento (P3):** reemplazar la constante manual por capacidades del backend/controladora; la UI debe fallar-cerrado si no las conoce | La UI no sugiere protección inexistente |
| UI-004 | UI [P] | Dry-run/preview de importación en el SPA | `PARTIAL` (falta) | `frontend/src/api/index.ts` importa directo | #7 | — | Ver IMPORT-001/002 | — |
| I18N-001 | i18n [P] | Internacionalización real (multi-idioma) | `PARTIAL` (sin i18n) | Sin librería; español hardcodeado | #7 | — | Marco + catálogos (P3-4) | Idioma conmutable con catálogos |

## Hardware / gateway / protocolo

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| HW-001 | Protocolo [P] | Codec 64 bytes (builders/parsers `FUNC_*`) | `OPEN_PR_VERIFIED` (codec puro) | `backend/app/services/protocol/frames.py`, `codec.py` | #7, `3533614` | `test_protocol_codec.py` (13, vectores **sintéticos**) | — | Round-trip de vectores sintéticos |
| HW-002 | Protocolo [H] | Wire protocol real N3000 confirmado | `BLOCKED_SPEC` | `docs/HARDWARE.md`, `docs/HARDWARE_STATUS.md` | — | — | SDK del fabricante o PCAP real | Tramas confirmadas contra placa |
| HW-003 | Transporte [H] | Driver UDP `tcp` (`l04_udp`) verificado | `BLOCKED_HARDWARE` | `backend/app/services/gateway/l04_udp.py` (EXPERIMENTAL) | #7 | — | Placa real | Comunicación real validada |
| GW-001 | Puente [P] | Outbox: enqueue idempotente, claim lease/CAS, ack idempotente | `OPEN_PR_UNVERIFIED` | `backend/app/services/gateway_outbox.py` | #7, `2ae52ea` | `test_gateway_outbox.py` (7), `test_command_dispatch.py` (4) | Estados tras error del gateway (seguridad) | Idempotencia y recuperación por lease |
| GW-002 | Puente [P] | API del puente + auth por fingerprint mTLS | `OPEN_PR_UNVERIFIED` | `backend/app/api/v1/gateway_bridge.py`. **Auditoría independiente: F-4** — confía en el header de fingerprint sin secreto secundario; suplantable si el edge no strippea el header. | #7, `afbd432` | `test_gateway_bridge.py` (14) | F-4: secreto por-bridge (PR separado) | Solo un puente con cert válido registra/opera |
| GW-003 | Puente [H] | Daemon puente real (Windows/Linux) | `BLOCKED_HARDWARE` | `docs/GATEWAY_BRIDGE.md` (componente externo) | — | — | Implementación + hardware | — |
| GW-004 | Puente [P] | Inbox de eventos de placa (idempotente, enmascarado) | `OPEN_PR_UNVERIFIED` | `backend/app/services/gateway_inbox.py` | #7, `d72464b` | `test_gateway_bridge.py` | Productor físico [H] | Dedup por `event_uid`; enmascara y difunde |
| GW-005 | Puente [P] | Revocaciones sincronizadas hacia la placa | `PARTIAL` (no automático) | `backend/app/api/v1/cardholders.py` no encola al revocar | #7 | — | Baja automática (P2-3) | Revocar propaga baja al puente |

## Infraestructura / despliegue / observabilidad

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| INFRA-001 | Deploy [P] | Fail-fast de config insegura en producción | `OPEN_PR_VERIFIED` | `backend/app/core/config.py` (`production_issues`) | #7 | `test_production_safety.py` (8) | — | Prod con defaults no arranca |
| INFRA-002 | Deploy | Secretos no versionados | `OPEN_PR_VERIFIED` | `.gitignore`; `git ls-files` sin `.env`/certs | #7 | — | — | No hay secretos en el repo |
| INFRA-003 | Deploy | TLS cableado en el borde | `PARTIAL` | `frontend/nginx.tls.conf` (manual, no en compose) | #7 | — | Montaje + certs (P1-3) | HTTPS real end-to-end |
| INFRA-004 | Deploy | Escalado multi-worker (Redis para rate-limit/fan-out/métricas) | `PLANNED` | `backend/app/core/ratelimit.py`, `metrics.py` (en memoria por-proceso) | #7 | — | Redis (P1-1) | >1 worker sin romper límites/revocación |
| INFRA-005 | Deploy | Migraciones como job previo (no en arranque) para réplicas | `PARTIAL` | `docker-compose.yml` corre `alembic upgrade` en arranque | #7 | — | Job dedicado (P1-2) | Sin carrera de migración con réplicas |
| INFRA-006 | CI | SCA backend (`pip-audit`) | `PLANNED` | `.github/workflows/ci.yml` sin pip-audit | — | — | Job pip-audit (P1-6) | Deps Python auditadas en CI |
| OBS-001 | Observabilidad [P] | request-id + logs JSON + correlación en auditoría | `OPEN_PR_VERIFIED` | `backend/app/core/observability.py`, `metrics.py`; migración `e0f1a2b3c4d5` | #7, `e863ee3`/`12b790e` | `test_observability.py` (6) | — | Auditoría correlaciona `request_id` |
| OBS-002 | Observabilidad [P] | `/metrics` protegido | `PARTIAL` | `backend/app/main.py` (token opcional `ACP_METRICS_TOKEN`) | #7 | — | Exigir token o borde (R-5) | `/metrics` no accesible sin token en prod |
| OBS-003 | Observabilidad | Alertas (readiness/5xx/lockouts/latencia) | `PLANNED` | — | — | — | Reglas/Alertmanager (P2-6) | Alertas mínimas activas |

## Backup / restore

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| BACKUP-001 | Backup | Backup confiable (falla si `pg_dump` falla; sin dump parcial) | `OPEN_PR_VERIFIED` (Probado en CI) | `scripts/backup_db.sh` **endurecido** (sin pipe, verifica exit de `pg_dump`, `gzip -t`, rename atómico, `umask 077`) | **PR #9** | `test_backup_restore_scripts.py` + PG real | Revisión | `pg_dump` fallido → código≠0, sin `.gz` final |
| BACKUP-002 | Restore | Restore seguro (máquina de estados, swap no destructivo + reconciliación por señal) y **probado** | `OPEN_PR_VERIFIED` (Probado en CI) | `scripts/restore_db.sh` **máquina de estados** (temp→validar→rename activa→recovery, temp→activa, rollback; reconcile por señal; mutex+journal; `--release-lock`/`--drop-recovery`) | **PR #9** | `test_backup_restore_scripts.py` (26 fakes) + `test_backup_restore_integration.py` (PG real: round-trip, aborto por validación, rollback post-swap); ShellCheck en CI | **Restore drill autorizado en staging** (distinto del test CI descartable) | Restore validado; base activa nunca se pierde |

## Calidad / pruebas

| ID | Área | Requisito | Estado | Evidencia (@`b97f5e3`) | PR/commit | Tests | Faltante | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|
| TEST-001 | Calidad | Suite backend verde | `OPEN_PR_VERIFIED` | `backend/tests/` (23 archivos) | #7 | 177 passed (ver `TEST_EVIDENCE.md`) | — | `pytest tests -q` en verde (SQLite + PG) |
| TEST-002 | Calidad | Tests de frontend (componentes / E2E) | `PARTIAL` | Infra Vitest + React Testing Library agregada; tests de componentes de `DoorsPage`/`ControllersPage` | **PR #10** | `doorFlags.test.ts`, `DoorsPage.test.tsx`, `ControllersPage.test.tsx` | E2E de navegador (Playwright) — P3-5 | SPA ejercitado (componentes ✅; E2E pendiente) |
| TEST-003 | Calidad | Cadena Alembic lineal (single head) | `OPEN_PR_VERIFIED` | `alembic heads`=1 (`e0f1a2b3c4d5`); guard en CI | #7 | — | Downgrade en CI (P2-4) | Un solo head; guard verde |

## Legacy (referencia)

| ID | Área | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|---|
| LEG-001 | Legacy | Módulos Meal/Patrol/Meeting/One-To-More | `PLANNED` | `docs/LEGACY.md` | — |
| LEG-002 | Legacy [H] | Peripheral/keypad/task list | `PLANNED` / `BLOCKED_HARDWARE` | `docs/LEGACY.md` | Adaptador real |
| LEG-003 | Legacy | Multi-tenant SaaS (no existía en legacy) | `OPEN_PR_VERIFIED` | ver TENANT-001/002 | mejora neta |
