# Evidencia de pruebas — Control de Acceso / Cerradura Magnética

> Fuente de verdad del conteo y la evidencia de tests. Reemplaza los números
> desactualizados de `LEGACY.md` (decía 51) y `DEVELOPMENT_LOG.md` (decía 112).
> Verificado en la auditoría del 2026-09-06 sobre `claude/develop`.

## Resumen

- **Total: 177 tests** (`def test_`) en **23 archivos**, todos en verde.
- Cubren backend sobre el gateway `simulated` y vectores de protocolo **sintéticos**.

> ⚠️ **Caveat central del proyecto:** **un test verde no equivale a validación
> contra una placa N3000/L04 real.** Ver `HARDWARE_STATUS.md`.

## Evidencia de CI (PR #8, rama `claude/docs-consolidation`)

| Job | Resultado | Duración aprox. |
|---|---|---|
| backend (SQLite) | **177 passed, 2 warnings** | ~294.59 s |
| backend-postgres (PostgreSQL 16) | **177 passed, 2 warnings** | ~313.72 s |
| frontend build (`npm run build`, tsc + vite) | **correcto** | — |
| `npm audit --omit=dev --audit-level=high` (deps de producción) | **0 vulnerabilidades** | — |

**Warnings registrados (no fallan la suite):**
- 2 warnings de `pytest` provenientes de **Starlette / `TestClient`** (deprecaciones de la librería de test), presentes en ambos jobs.
- GitHub Actions emite una **advertencia por acciones basadas en Node 20** (deprecación del runner), independiente del código de la app.

**Sobre auditoría de dependencias del frontend:**
- El gate de CI es `npm audit --omit=dev` (solo producción) → **0 vulnerabilidades**.
- `npm ci` (árbol completo, incluyendo dev/tooling) reporta **2 vulnerabilidades** de tooling de desarrollo. **No** se afirma "queda exactamente un advisory" sin adjuntar la salida de `npm audit`; el número vigente sale de correr `npm audit` en `frontend/`.

## Comandos canónicos

```bash
cd backend
pytest tests -q        # suite completa (SQLite por defecto)
ruff check .           # lint — comando EXACTO que corre CI (incluye migraciones y env.py)
```

En CI (`.github/workflows/ci.yml`):
- **job backend (SQLite):** `ruff check .`, guard de single Alembic head, `pytest`, `alembic upgrade head`.
- **job backend-postgres:** `alembic upgrade head` + `pytest` contra `postgres:16` (ejercita locking real, rotación de sesiones concurrente).
- **job frontend:** `npm ci`, `npm audit --omit=dev --audit-level=high`, `npm run build` (typecheck + bundle).

## Conteo por archivo

| Tests | Archivo | Cubre |
|---:|---|---|
| 22 | `test_sessions.py` | Sesiones server-side, rotación CAS, detección de reuso full-history, logout, cierre WS, suspensión usuario/org |
| 15 | `test_access_flow.py` | Motor de decisión: tarjeta, PIN, card+PIN, PIN-only, horarios, feriados, validez, enmascarado, virtual card number |
| 14 | `test_gateway_bridge.py` | API del puente: registro por fingerprint mTLS, claim/ack, inbox de eventos |
| 13 | `test_protocol_codec.py` | Codec 64 bytes (vectores hex **sintéticos**): frames, BCD, fecha, `CardRecord`, tarjeta 64-bit |
| 12 | `test_attendance.py` | Asistencia: estados por día, zona horaria, fichaje manual, tolerancias |
| 10 | `test_dual_approval.py` | Doble aprobación: CAS PENDING→EXECUTED/DISPATCHED, self-approve 403, TTL, fail-closed |
| 8 | `test_production_safety.py` | Fail-fast de config en prod; seed demo rehúsa en prod |
| 8 | `test_platform.py` | Aislamiento multi-tenant, scoping por org |
| 8 | `test_cookie_auth.py` | Cookies HttpOnly/Secure/SameSite + CSRF double-submit |
| 8 | `test_auth.py` | Login, refresh, me, cambio de contraseña |
| 7 | `test_infrastructure.py` | CRUD controladoras/puertas, apertura remota, sync |
| 7 | `test_import.py` | Importación CSV por etapas (plan/apply, dry-run, validación fila por fila) |
| 7 | `test_gateway_outbox.py` | Outbox: enqueue idempotente, claim con lease/CAS, ack idempotente |
| 6 | `test_observability.py` | request-id, logs JSON, correlación en auditoría |
| 5 | `test_pin_encryption.py` | Cifrado Fernet del PIN, ciphertext en DB, API omite PIN |
| 5 | `test_mfa.py` | TOTP setup/enable/disable |
| 5 | `test_login_protection.py` | Rate-limit + lockout por fuerza bruta |
| 4 | `test_mdb_import.py` | Importación MDB: detección de tabla, dry-run |
| 4 | `test_command_dispatch.py` | Dispatch directo vs puente tras `ACP_COMMAND_DISPATCH` |
| 3 | `test_masking.py` | Enmascarado de nº de tarjeta (últimos 4) |
| 2 | `test_wiegand.py` | Virtual card number de teclado (10 dígitos) |
| 2 | `test_health.py` | `/health` (liveness) y `/health/ready` (readiness) |
| 2 | `test_event_broadcast.py` | Difusión post-commit; descarte en rollback |

## Huecos de cobertura conocidos

- **Sin tests E2E de frontend.** `frontend/package.json` no tiene script `test` ni Playwright/Cypress/Vitest. Los 177 tests son de backend (pytest). El SPA no tiene pruebas automatizadas.
- **Camino 503 de `/health/ready`** (DB caída) no se ejercita explícitamente.
- **Downgrade de migraciones** no se ejercita en CI (solo `upgrade`); reversibilidad de esquema sin garantía.
- **Nada verificado contra hardware real.** El codec se prueba con vectores sintéticos, no con capturas de una placa.
