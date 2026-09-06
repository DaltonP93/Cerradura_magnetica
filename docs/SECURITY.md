# Postura de seguridad — Control de Acceso / Cerradura Magnética

> Documento canónico de seguridad. Consolida invariantes, controles
> implementados y la **reconciliación de hallazgos históricos** contra el código
> actual (`claude/develop`, auditoría 2026-09-06). Un ítem se marca RESUELTO solo
> con evidencia actual (archivo:línea o test).
>
> **Nota de método:** la auditoría de seguridad dedicada quedó parcialmente
> cubierta por el líder tras un corte de sesión del agente de seguridad. Las
> reconciliaciones de abajo están respaldadas por lectura de código y por los
> tests verdes citados; los ítems marcados `NO_VERIFICADO` requieren una pasada
> adversarial adicional.

## Invariantes (única sede canónica; el resto de docs enlaza aquí)

1. No abrir/cerrar/configurar/sincronizar una puerta o controladora real sin autorización humana explícita.
2. Mantener aislamiento multi-tenant y RBAC; nunca filtrar personas, tarjetas, PIN, eventos o auditorías entre organizaciones.
3. Las decisiones de acceso respetan credencial, persona, vigencia, nivel, horario, feriados y modo de puerta.
4. Cambios de horarios, credenciales, permisos, puertas y eventos quedan auditados.
5. Importaciones CSV/Excel/MDB se validan fila por fila; no se sobrescribe silenciosamente.
6. No versionar ni exponer claves, credenciales de superadmin, IPs de controladoras, tokens JWT, datos de tarjetas ni datos personales.
7. No ejecutar migraciones, `docker compose up`, despliegues ni cambios de firmware sobre entornos reales sin aprobación.

## Controles implementados (Fase 1)

| Control | Evidencia | Tests |
|---|---|---|
| Sesiones server-side (una fila por login, solo hash SHA-256 del refresh) | `app/models/auth_session.py`, `app/services/sessions.py` | `test_sessions` (22) |
| Refresh rotativo + detección de reuso full-history + revocación de familia | `services/sessions.py` | `test_sessions` |
| Binding sesión ↔ sujeto del token (sid+sub) | `deps.py:34-38`, `ws.py:41-45` (`get_active_session(db, session_id, subject)`) | `test_sessions` |
| Revocación por suspensión de usuario/org, cambio de rol/contraseña | `api/v1/organizations.py:69-85`, `deps.py:43-44` | `test_sessions` |
| Cookies HttpOnly/Secure/SameSite | `app/core/cookies.py` | `test_cookie_auth` (8) |
| CSRF double-submit | `app/core/csrf.py`, `main.py:41-42` | `test_cookie_auth` |
| JWT fuera de localStorage/URL (SPA usa cookies; WS usa cookie del handshake) | `frontend/src/api/client.ts`, `ws.py:75-78` | — |
| PIN cifrado en reposo (Fernet, llave externa vía `ACP_PIN_ENCRYPTION_KEY` o HKDF de `ACP_SECRET_KEY`) | `app/core/crypto.py`, `EncryptedString` | `test_pin_encryption` (5) |
| PIN comparado en tiempo constante; PIN obligatorio en PIN-only y card+PIN | `access_engine.py:45-49,148-153` | `test_access_flow` |
| Nº de tarjeta enmascarado (últimos 4) en eventos/auditoría | `app/core/masking.py`, `access_engine.py:219,232` | `test_masking` (3) |
| Rate-limit por IP + lockout de cuenta por fuerza bruta | `app/core/ratelimit.py`, `users.locked_until` | `test_login_protection` (5) |
| MFA TOTP (backend) | `api/v1/auth.py`, `core/totp.py` | `test_mfa` (5) |
| Fail-fast de config insegura en producción | `config.py:100-126` | `test_production_safety` (8) |
| Doble aprobación (two-person rule) en puertas críticas — backend | `services/dual_approval.py` (CAS, self-approve 403, TTL, fail-closed) | `test_dual_approval` (10) |
| Auditoría sin tokens, con correlación request-id | `services/audit.py`, migración `e0f1a2b3c4d5` | `test_observability` (6) |

## Reconciliación de hallazgos históricos

| Hallazgo histórico | Estado | Evidencia |
|---|---|---|
| WS revalidation "starvable" (no revalida si no hay tráfico) | **RESUELTO** | `ws.py:90-118`: revalidación por **deadline** con `next_revalidate`/`select` timeout, independiente del tráfico entrante. |
| Sesión no ligada al `sub` del JWT | **RESUELTO** | `deps.py`/`ws.py:44-45` exigen que la sesión activa pertenezca al `subject` del token (`get_active_session(db, session_id, subject)`). |
| Asserts de test con `or True` | **RESUELTO** | `grep "or True"` en `tests/` = **0 resultados**. |
| Tests concurrentes permisivos | **RESUELTO (parcial)** | `test_sessions` cubre refresh concurrente y cierre WS bajo tráfico; corre también en el job PostgreSQL de CI (locking real). |
| Credenciales demo en producción | **RESUELTO** | `seed.py:34-36` rehúsa el seed en prod y no imprime contraseñas; `test_production_safety`. |
| Secretos por defecto inseguros | **RESUELTO** | `config.py:100-126` no arranca en prod con secret default/corta, password default, `debug`, o `cookie_secure=false`. |
| PIN en texto plano | **RESUELTO** | Fernet + `EncryptedString`; `test_pin_encryption` verifica ciphertext en DB y que la API omite el PIN. |
| JWT en localStorage | **RESUELTO** | SPA usa cookies HttpOnly (`client.ts` con `withCredentials`); sin token en JS. |
| Token WS en la URL | **RESUELTO** | El WS se autentica con la cookie del handshake (`ws.py:75-78`); el query token queda solo como fallback documentado para clientes no-navegador. |
| Falta CSRF | **RESUELTO** | Middleware double-submit (`csrf.py`); `test_cookie_auth`. |
| Falta rate-limiting | **RESUELTO (con caveat multi-worker)** | `ratelimit.py`; es **en memoria por-proceso** → ver riesgo abierto R-1. |
| Falta MFA | **RESUELTO (backend) / PARCIAL (sin UI)** | Backend `totp.py`; sin pantallas en el SPA. |
| Falta Redis pub/sub | **ABIERTO** | No existe Redis; fan-out de revocación y rate-limit son por-proceso. Ver R-1. |
| Falta doble aprobación | **RESUELTO (backend) / PARCIAL (sin UI)** | `dual_approval.py`; sin UI para completar el flujo. |
| Sesiones activas tras suspensión de org | **RESUELTO** | `organizations.py:69-85` + `deps.py:43-44` cortan sesión y WS. |
| Revocaciones no sincronizadas con la placa | **ABIERTO** | `cardholders.py` no encola ni llama al gateway al revocar; el push es manual y simulado. Ver R-2. |
| Flags de puerta (anti-passback/interlock/multicard/first-card) solo almacenados | **ABIERTO** | Sin enforcement en `access_engine.py`. Ver R-3. |

## Riesgos abiertos priorizados

| ID | Riesgo | Severidad | Impacto | Mitigación propuesta |
|---|---|---|---|---|
| R-1 | Rate-limit, revocación WS y métricas **en memoria por-proceso** | Alta (operacional) | Escalar a >1 worker rompe el límite de auth y demora la revocación al `ws_revalidate_seconds` | Introducir Redis (store + pub/sub) antes de multi-worker; hoy: **mandar un solo worker** |
| R-2 | Revocaciones **no propagadas a la placa** | Alta (seguridad física) | Una credencial revocada sigue válida en la memoria de la placa hasta un sync manual | Encolar baja en el outbox al revocar; sincronización automática |
| R-3 | Flags avanzados de puerta **sin enforcement** | Alta (falsa seguridad) | La UI sugiere protección (anti-passback, interlock) que no existe | Implementar en el motor o marcar explícitamente "no aplicado" en la UI |
| R-4 | Sin **pip-audit** en backend | Media | Vulnerabilidades de deps Python sin detectar | Agregar `pip-audit` al job de CI |
| R-5 | `/metrics` abierto si no se setea `ACP_METRICS_TOKEN` | Media | Exposición de métricas internas | Exigir token o restringir en el borde en prod |
| R-6 | Sin restore probado de la DB | Media (operacional) | Backup no verificable | Ver `BACKUP_RESTORE.md` (P0-3) |

## Pendiente de verificación (NO_VERIFICADO)

- Pasada adversarial completa de **IDOR** endpoint por endpoint (Agente 1 verificó el patrón de scoping en `deps.py`, pero no se recorrieron todos los handlers con IDs cross-org).
- Tests negativos reproducibles de bypass de doble aprobación bajo carrera más allá de los 10 tests actuales.
- Revisión de fuga de datos en mensajes de error / logs (más allá del enmascarado de tarjeta).

> Estos ítems deben cubrirse en una segunda tanda del agente de seguridad; no se
> declaran resueltos.
