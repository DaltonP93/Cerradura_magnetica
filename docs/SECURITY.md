# Postura de seguridad — Control de Acceso / Cerradura Magnética

> Documento canónico de seguridad. Consolida invariantes, controles
> implementados y la **reconciliación de hallazgos históricos** contra el código
> actual (`claude/develop`, auditoría 2026-09-06). Un ítem se marca RESUELTO solo
> con evidencia actual (archivo:línea o test).
>
> **Nota de método:** la **auditoría de seguridad independiente ya se completó**
> (solo lectura, SHA `b97f5e3`, 177 tests verdes; ver la sección "Auditoría de
> seguridad independiente" más abajo con los hallazgos F-1…F-11). Las
> reconciliaciones están respaldadas por lectura de código y tests. Ya no quedan
> ítems `NO_VERIFICADO` de la primera tanda: IDOR endpoint-por-endpoint, doble
> aprobación bajo carrera y fuga en logs fueron verificados.

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

## Auditoría de seguridad independiente (2026-09-06)

Un agente de seguridad independiente (solo lectura) auditó el SHA
`b97f5e3` (verificado vía `git worktree`, 177 tests en verde). **Resultado:
postura sólida — 0 P0, 0 P1, 5 P2, 6 P3.** Sin fuga de aislamiento multi-tenant
ni de PIN. Los hallazgos son de defensa-en-profundidad y dependencia del borde.

**Ítems antes `NO_VERIFICADO`, ahora resueltos por la auditoría:**
- **IDOR endpoint-por-endpoint:** revisado `api/v1/*.py` completo; todo handler con id filtra por `organization_id`. Sin IDOR explotable (único hueco *latente*: F-9 abajo).
- **Doble aprobación bajo carrera:** `claim_for_approval` usa CAS real (`UPDATE ... WHERE status=PENDING AND expires_at>now` + `rowcount==1`); dos aprobadores concurrentes **no** pueden ejecutar dos aperturas. Correcto.
- **Fuga en logs/errores:** tarjetas enmascaradas en eventos/auditoría/inbox/swipe; PIN nunca sale y viaja cifrado; solo se guardan hashes de tokens. Excepción: F-6 (importador).

Los 11 controles marcados resueltos por el líder fueron **confirmados** por la
auditoría (con 2 matices: F-2 y F-6).

### Hallazgos nuevos (cada uno → **PR separado**, no se corrigen en PR #8)

| ID | Sev | Hallazgo | Archivo:función | Corrección mínima |
|---|---|---|---|---|
| F-1 | P2 | Carrera lost-update en el lockout (`+=1` read-modify-write no atómico) debilita anti-fuerza-bruta | `api/v1/auth.py::login` | ✅ **PR #12 (abierto):** `_register_failed_login()` con `UPDATE ... failed_login_count + 1 RETURNING` (atómico) + test de concurrencia (K→K) |
| F-2 | P2 | `--forwarded-allow-ips *`: confía en `X-Forwarded-For` de cualquier peer → bypass rate-limit por IP + IP falsificable en auditoría/sesión | `backend/Dockerfile`; `core/ratelimit.py`, `services/audit.py`, `services/sessions.py` | ✅ **PR #11 (abierto):** `forwarded_allow_ips` configurable (default `127.0.0.1`), producción rechaza `*` (fail-fast); Dockerfile/compose sin `*` literal |
| F-3 | P2 | WebSocket sin verificación de `Origin` → CSWSH si `ACP_COOKIE_SAMESITE=none` | `api/v1/ws.py::events_ws` | ✅ **PR #14 (abierto):** `Origin` presente debe estar en `cors_origin_list` (rechazo 1008 antes de autenticar); `Origin` ausente = cliente no-navegador (sin cookie ambiental) permitido; tests cross-origin/allowlist |
| F-4 | P2 | Confianza ciega en el header de fingerprint del bridge (no es secreto) → suplantación si el edge no strippea el header | `api/v1/gateway_bridge.py::get_current_bridge` | ✅ **PR #13 (abierto):** secreto por-bridge (token `urlsafe(32)` emitido al registrar, guardado hasheado y devuelto una vez) verificado en tiempo constante además del fingerprint; `secret_hash` NULL no autentica (fail-closed) + tests negativos |
| F-5 | P2 | MFA sin códigos de recuperación ni reset por admin → lockout permanente ante pérdida del TOTP | `api/v1/auth.py`, `schemas/auth.py` (UserUpdate sin campos mfa) | Recovery codes de un uso (hasheados) y/o endpoint de reset admin auditado |
| F-6 | P3 | Nº de tarjeta en claro en errores del importador (inconsistente con masking) | `services/importer.py::_build_plan` | `mask_card()` en los mensajes de error |
| F-7 | P3 | `/metrics` abierto por defecto (no en `production_issues`) + compare no constante | `main.py::prometheus_metrics`, `core/config.py` | Exigir token en prod; `secrets.compare_digest` |
| F-8 | P3 | Enumeración de usuarios/tenants (timing bcrypt; 409 de unicidad global de email/serial) | `api/v1/auth.py::login`, `users.py`, `controllers.py` | Hash dummy en tiempo constante; 409 genéricos |
| F-9 | P3 | `get_or_404` con fallback `getattr(obj,"organization_id",org_id)` → IDOR latente para futuros modelos sin `organization_id` | `api/helpers.py::get_or_404` | Requerir el atributo; fallar-cerrado |
| F-10 | P3 | Inbox: duplicado concurrente del mismo `event_uid` rompe el lote entero (sin manejo de IntegrityError por-fila) | `services/gateway_inbox.py::ingest_events` | `INSERT ... ON CONFLICT DO NOTHING` o savepoints por evento |
| F-11 | P3 | Apertura remota no idempotente ante doble-submit (modo bridge): `uuid4` por llamada → doble apertura | `services/command_dispatch.py::enqueue_command` | Aceptar `Idempotency-Key` del cliente como clave del outbox |

> Prioridad de PRs sugerida por la auditoría: **F-2 y F-1** primero (habilitan
> fuerza bruta combinada), luego F-4 y F-3, luego F-5 (disponibilidad), y los P3
> como higiene. **Ninguno se corrige en el PR documental (#8);** cada uno va en su
> propia rama con tests. **Informe completo versionado:** [`docs/audits/SECURITY_AUDIT_2026-09-06.md`](audits/SECURITY_AUDIT_2026-09-06.md).

## Riesgos abiertos priorizados (operacionales / funcionales)

| ID | Riesgo | Severidad | Impacto | Mitigación propuesta |
|---|---|---|---|---|
| R-1 | Rate-limit, revocación WS y métricas **en memoria por-proceso** | Alta (operacional) | Escalar a >1 worker rompe el límite de auth y demora la revocación al `ws_revalidate_seconds` | Introducir Redis (store + pub/sub) antes de multi-worker; hoy: **mandar un solo worker** |
| R-2 | Revocaciones **no propagadas a la placa** | Alta (seguridad física) | Una credencial revocada sigue válida en la memoria de la placa hasta un sync manual | Encolar baja en el outbox al revocar; sincronización automática |
| R-3 | Flags avanzados de puerta **sin enforcement** | Alta (falsa seguridad) | La UI sugiere protección (anti-passback, interlock) que no existe | Marcar "no aplicado/experimental" en la UI (PR frontend en curso) o implementar en el motor |
| R-4 | Sin **pip-audit** en backend | Media | Vulnerabilidades de deps Python sin detectar | Agregar `pip-audit` al job de CI |
| R-5 | Backup ocultaba fallos + sin restore probado | Media (operacional) | Backup no confiable/verificable | Endurecido en PR #9 (falta prueba real autorizada) |
