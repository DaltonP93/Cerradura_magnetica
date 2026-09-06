# Matriz de trazabilidad de requisitos — Control de Acceso

> Requisito → Estado → Evidencia → Faltante. Consolida la auditoría funcional
> (2026-09-06) sobre `claude/develop`. Todo es `OPEN_PR_*` (nada en `main`).
> Estados definidos en `IMPLEMENTATION_STATUS.md`. Reemplaza la tabla de cobertura
> dispersa en `LEGACY.md`.

## A. Objetivo del sistema

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 1 | SaaS web que reemplaza el CRUD del N3000 | `OPEN_PR_VERIFIED` | `api/router.py:22-39` (15 routers), 14 páginas SPA | Validación hardware; merge |
| 2 | Reemplazo con seguridad física real | `BLOCKED_HARDWARE` | `HARDWARE_STATUS.md` | Adaptador validado en placa |

## B. Multi-tenant

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 3 | Aislamiento por `organization_id` | `OPEN_PR_VERIFIED` | `deps.py:69-90`, `OrgScopedMixin`; `test_platform` (8) | — |
| 4 | Suspensión de empresa corta sesiones/WS | `OPEN_PR_VERIFIED` | `organizations.py:69-85`, `deps.py:43-44` | Fan-out multi-worker (Redis) |

## C. RBAC

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 5 | 4 roles (super_admin/admin/operator/viewer) | `OPEN_PR_VERIFIED` | `deps.py:52-66`, `tenancy.py:35` | — |
| 6 | super_admin no secuestrable por admin de org | `OPEN_PR_VERIFIED` | `seed.py:49-56` (org_id=None), fix `b6690ff` | — |

## D. Personas y credenciales

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 7 | PIN-only y card+PIN exigen PIN | `OPEN_PR_VERIFIED` | `access_engine.py:41-49,148-153` | — |
| 8 | PIN cifrado en reposo, llave externa | `OPEN_PR_VERIFIED` | `crypto.py`, `EncryptedString`; `test_pin_encryption` | Rotación de llave automatizada |
| 9 | Nº de tarjeta enmascarado | `OPEN_PR_VERIFIED` | `masking.py`; `test_masking` | — |
| 10 | Alta por lector USB WG1028 / rango | `PLANNED` | `LEGACY.md:49` | Hardware en el puesto |
| 11 | Virtual card number de teclado | `OPEN_PR_VERIFIED` | `wiegand.py:12-19`; `test_wiegand` | Verificación con lectora real |

## E. Controladoras y puertas

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 12 | CRUD controladoras (S/N, IP, 4 puertas) | `OPEN_PR_VERIFIED` | `controllers.py`; `test_infrastructure` | — |
| 13 | Consola Check/Time/Upload | `SIMULATED_ONLY` | `controllers.py:189-250`, `simulated.py` | Adaptador real |
| 14 | Apertura remota con evento+auditoría | `SIMULATED_ONLY` | `doors.py:197-252` | Apertura física real |

## F. Flags avanzados de puerta

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 15 | anti-passback/interlock/multicard/first-card | `PARTIAL` (solo persistencia) | Solo en `models/`+`schemas/`; **cero** en `access_engine.py` | Enforcement en el motor (P0-1) |
| 16 | `requires_dual_approval` por puerta | `PARTIAL` | Backend `doors.py:184-194`; **UI no expone el toggle** | Control en UI |

## G. Horarios y niveles

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 17 | Horarios semanales + niveles N-a-N | `OPEN_PR_VERIFIED` | `access_engine.py:167-193`; `test_access_flow` | Perfiles a nivel placa |
| 18 | Horario en zona horaria del sitio | `OPEN_PR_VERIFIED` | `access_engine.py:80-109` | — |

## H. Feriados

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 19 | Feriados excluyen acceso salvo `allow_on_holidays` | `OPEN_PR_VERIFIED` | `access_engine.py:92-102` | — |

## I. Eventos y monitoreo

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 20 | Eventos + difusión WS por org | `OPEN_PR_VERIFIED` | `events.py:37-110`; `test_event_broadcast` | Fan-out multi-worker (Redis) |
| 21 | Difusión solo tras commit | `OPEN_PR_VERIFIED` | `events.py:151-165`, fix `5a95982` | — |
| 22 | Reconexión WS acotada ante sesión revocada | `OPEN_PR_VERIFIED` | fix `ed91d2b` | Re-verificación línea a línea del frontend |

## J. Apertura remota / doble aprobación

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 23 | Doble aprobación — backend | `OPEN_PR_VERIFIED` | `dual_approval.py`; `test_dual_approval` (10) | — |
| 24 | Doble aprobación — UI | `PARTIAL` (sin frontend) | `api/index.ts:107-112` solo `open` | Página crear/aprobar/rechazar (P0-2) |

## K. Asistencia

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 25 | Reporte con turnos/tolerancias/licencias/feriados | `OPEN_PR_VERIFIED` | `attendance.py:40-187`; `test_attendance` (12) | Ver 26-27 |
| 26 | Zona horaria explícita (UTC→local) | `OPEN_PR_VERIFIED` | `attendance.py:34-37,90-103` | — |
| 27 | Turnos nocturnos (cruzan medianoche) | `PARTIAL` (no soportado) | `models/attendance.py:29-30` (Time plano) | Flag overnight + lógica (P1-5) |
| 28 | Fichaje manual correctivo | `OPEN_PR_VERIFIED` | `attendance.py:93-103` | — |
| 29 | Historial de asistencia | `PARTIAL` | Recomputado; `MAX_RANGE_DAYS=92` | Cierres/snapshots inmutables |

## L. Importación legacy

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 30 | CSV por etapas (plan/apply) + dry-run | `OPEN_PR_VERIFIED` (backend) / `PARTIAL` (frontend) | `importer.py:73-186`; **SPA importa sin dry_run** | Preview en UI (P2-1) |
| 31 | MDB con detección de tabla + dry-run | `OPEN_PR_VERIFIED` (backend) / `PARTIAL` (frontend) | `legacy_mdb.py:58-86`; `test_mdb_import` | `mdbtools` en server; UI |

## M. Reportes

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 32 | Reporte de eventos + export CSV | `PARTIAL` | Backend `events.py:21-52`; **export client-side** | Export server-side (P2-2) |

## N. i18n

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 33 | i18n multi-idioma | `PARTIAL` (sin i18n) | Sin librería; español hardcodeado | Marco + catálogos (P3-4) |

## O. Consistencia frontend↔backend

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 34 | MFA/TOTP | `PARTIAL` (backend sin UI) | `auth.py`, `totp.py`; `test_mfa` | Pantallas en SPA (P1-4) |
| 35-37 | Flags puerta / doble aprobación / dry-run en UI | `PARTIAL` | Ver 15, 24, 30-31 | — |

## P. Gateway / puente / protocolo

| # | Requisito | Estado | Evidencia | Faltante |
|---|---|---|---|---|
| 38 | Codec de protocolo (frame 64B) | `OPEN_PR_VERIFIED` (puro) / `BLOCKED_SPEC` | `protocol/`; `test_protocol_codec` (13, vectores sintéticos) | Wire protocol real N3000 |
| 39 | Gateway UDP `tcp` real | `BLOCKED_SPEC` / `SIMULATED_ONLY` | `l04_udp.py:1-9` (EXPERIMENTAL) | Verificación en placa |
| 40 | Puente outbox/inbox mTLS | `OPEN_PR_VERIFIED` (contrato) / `BLOCKED_HARDWARE` | `gateway_outbox.py`, `gateway_bridge.py`; 25 tests | Daemon puente real |
| 41 | Ingesta de eventos de placa | `OPEN_PR_VERIFIED` (endpoint) / `BLOCKED_HARDWARE` | `gateway_inbox.py` | Productor físico |
| 42 | Revocaciones sincronizadas con placa | `PARTIAL` (no automático) | `cardholders.py` sin gateway | Baja automática (P2-3) |
| 43 | Eventos físicos reales | `SIMULATED_ONLY` | `simulated.py`, `gateway_inbox.py` | Placa/puente real |

## Q. Fase 1 — Seguridad web

| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| 44 | Sesiones + refresh rotativo + reuse + binding | `OPEN_PR_VERIFIED` | `sessions.py`; `test_sessions` (22) |
| 45 | Cookies HttpOnly/CSRF; JWT fuera de localStorage/URL | `OPEN_PR_VERIFIED` | `cookies.py`, `csrf.py`; `test_cookie_auth` |
| 46 | Rate-limit + lockout | `OPEN_PR_VERIFIED` | `ratelimit.py`; `test_login_protection` |
| 47 | Rechazo de defaults inseguros/seed en prod | `OPEN_PR_VERIFIED` | `config.py`; `test_production_safety` |
| 48 | React Router parcheado + npm audit | `OPEN_PR_VERIFIED` | `package.json:12` (7.18.3); esbuild advisory pendiente |

## R. Legacy

| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| 49 | Módulos Meal/Patrol/Meeting/One-To-More | `PLANNED` | `LEGACY.md:48` |
| 50 | Peripheral/keypad/task list | `PLANNED` / `BLOCKED_HARDWARE` | `LEGACY.md:50` |
| 51 | Multi-tenant SaaS (no existía en legacy) | `OPEN_PR_VERIFIED` | mejora neta |

## S. Calidad

| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| 52 | Suite backend verde | `OPEN_PR_VERIFIED` | 177 passed; ver `TEST_EVIDENCE.md` |
| 53 | Tests E2E frontend | `PARTIAL` (ausentes) | Sin Playwright/Cypress (P3-5) |
| 54 | Cadena Alembic lineal (single head) | `OPEN_PR_VERIFIED` | `alembic heads`=1 (`e0f1a2b3c4d5`); guard en CI |
