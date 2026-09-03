# Bitácora de desarrollo — Control de Acceso / Cerradura Magnética

> Documento vivo. Registra lo que el dueño del proyecto pidió y lo que efectivamente se
> desarrolló, para servir de bitácora, referencia y base de una auditoría externa posterior
> (proyecto "Codex").
>
> - **Rama documentada:** `claude/develop`
> - **Fecha de esta edición:** 2026-09-03
> - **Alcance:** solo código versionado. Este documento **no autoriza** acciones sobre
>   puertas, controladoras, migraciones ni producción.
> - **Confidencialidad:** no se incluyen secretos, PINs, IPs de controladoras, tokens JWT,
>   datos de tarjetas ni datos personales. El material legacy (RAR, `iCCard3000.mdb`,
>   ejecutables, DLLs, PCAP) se trata como confidencial y no se publica.

---

## Índice

1. [Requisitos del usuario](#1-requisitos-del-usuario)
2. [Estado actual del proyecto](#2-estado-actual-del-proyecto)
   - 2.1 [Arquitectura](#21-arquitectura)
   - 2.2 [Módulos y modelo de datos](#22-módulos-y-modelo-de-datos)
   - 2.3 [Endpoints principales](#23-endpoints-principales)
   - 2.4 [Invariantes de seguridad física y de datos](#24-invariantes-de-seguridad-física-y-de-datos)
3. [Fase 1 — Endurecimiento de seguridad (implementado)](#3-fase-1--endurecimiento-de-seguridad-implementado)
   - 3.1 [Tabla resumen de los 9 ítems](#31-tabla-resumen-de-los-9-ítems)
   - 3.2 [Detalle por ítem](#32-detalle-por-ítem)
   - 3.3 [Historial de commits de Fase 1](#33-historial-de-commits-de-fase-1)
4. [Pendiente — Fases 2 a 7](#4-pendiente--fases-2-a-7)
5. [Validación y pruebas](#5-validación-y-pruebas)
6. [Advertencia sobre hardware real](#6-advertencia-sobre-hardware-real)
7. [Dudas y gaps para el líder](#7-dudas-y-gaps-para-el-líder)

---

## 1. Requisitos del usuario

Reconstrucción fiel, en palabras del documentalista, de lo que el dueño del proyecto pidió.
La fuente primaria son los prompts de diseño del proyecto (`prompt_codex_*.md`, material
legacy confidencial) y las instrucciones persistentes del repositorio
(`CLAUDE.md`, `docs/AI_HANDOFF.md`).

### 1.1 Objetivo general

Reemplazar el software de escritorio Windows legado ("Professional Door Control Management" /
N3000, distribuido como `AccessControl.en software` y `WGACCESS_NUEVO_ACTUALIZADO`) por una
**plataforma web SaaS multi-tenant** profesional y robusta, conservando la seguridad física y
la trazabilidad del sistema original, para controladoras de acceso tipo **L04 / N3000** (placas
TCP/IP de hasta 4 puertas, lectoras Wiegand, identificadas por número de serie de 9 dígitos,
puerto 60000).

### 1.2 Hoja de ruta de 7 fases

El dueño definió un desarrollo por fases incrementales:

| Fase | Tema | Estado global |
|---|---|---|
| **1** | Endurecimiento de seguridad de la plataforma web (9 ítems, ver §3) | **Implementada en `claude/develop`** |
| **2** | Codec del protocolo de la controladora (framing binario, funciones) | Pendiente |
| **3** | Gateway local (agente puente) con mTLS y cola persistente SQLite (outbox/inbox) | Pendiente |
| **4** | Sincronización plataforma ↔ placa (permisos, hora, altas/bajas) | Pendiente |
| **5** | Ingesta de eventos desde la placa hacia la plataforma | Pendiente |
| **6** | Importador MDB (`iCCard3000.mdb`) por etapas, validado fila por fila | Parcial / por etapas |
| **7** | Asistencia y puesta en producción (endurecimiento operativo final) | Pendiente |

> **Nota:** la validación contra **hardware real** está explícitamente pendiente en todas las
> fases que tocan la placa (2–5 y parte de 7). El modo `simulated` es el predeterminado.

### 1.3 Restricciones y forma de trabajo exigidas por el dueño

- **No publicar material sensible en el repositorio:** archivos RAR del legacy,
  `iCCard3000.mdb`, ejecutables, DLLs (`n3k_comm.dll`, `n3k_jm.dll`, `n3k_extern.dll`),
  capturas PCAP, datos de tarjetas, PINs ni datos de empleados.
- **PRs chicos y verificables:** cada cambio en un PR acotado, con pruebas y posibilidad de
  revisión y rollback. Nada de grandes cambios monolíticos.
- **No declarar el proyecto "terminado":** la UI funcional o los tests en verde **no** equivalen
  a validación en placa real.
- **Auditoría posterior con "Codex":** el trabajo debe quedar documentado y trazable para una
  revisión técnica externa independiente.
- **No inventar el protocolo del hardware:** toda comunicación física aislada tras
  `ControllerGateway`; toda compatibilidad no comprobada se declara *experimental*.
- **No ejecutar acciones sobre hardware, migraciones o producción sin autorización explícita.**

### 1.4 Pedido reciente: equipo de agentes

El dueño solicitó montar un **equipo de agentes** con roles definidos para llevar adelante el
proyecto de forma organizada:

- **1 Líder** (coordina, revisa y commitea; único que integra a la rama).
- **1 Analista / desarrollo** (análisis funcional y diseño).
- **1 DevOps** (infraestructura, CI, despliegue).
- **1 Documentación** (este rol — redactor técnico / documentalista).
- **1 Seguridad** (revisión de invariantes y hallazgos).
- **2 de desarrollo** (implementación).

Este documento es producido por el rol de **Documentación** y queda a disposición del **Líder**
para su revisión e integración. El documentalista **no commitea ni hace push**.

---

## 2. Estado actual del proyecto

### 2.1 Arquitectura

Stack confirmado leyendo el repositorio:

- **`frontend/`** — React 18 + TypeScript + Vite + Tailwind (SPA servida por Nginx).
- **`backend/`** — FastAPI + SQLAlchemy 2 + Alembic (API REST versionada `/api/v1` + WebSocket).
- **Base de datos** — PostgreSQL en producción; SQLite en desarrollo/tests (mismo código, URL por
  `ACP_DATABASE_URL`).
- **Infra** — Docker Compose (Postgres + backend + frontend Nginx); CI en GitHub Actions
  (`.github/workflows/ci.yml`): lint + tests backend, verificación de migraciones y build tipado
  del frontend; hay un job adicional contra PostgreSQL para certificar el bloqueo de filas que
  SQLite no cubre.
- **Capa de hardware** — aislada por la interfaz `ControllerGateway`
  (`backend/app/services/gateway/base.py`) con dos implementaciones seleccionadas por
  `ACP_GATEWAY_MODE`:
  - `simulated` (`simulated.py`) — responde siempre; demo, desarrollo y tests. **Estable.**
  - `tcp` (`l04_udp.py`) — protocolo UDP binario de 64 bytes, puerto 60000, de placas de 4 puertas
    UHPPOTE-compatibles. **Experimental, no verificado contra las placas N3000 del proyecto.**

Documentación de soporte: `README.md`, `docs/ARCHITECTURE.md`, `docs/HARDWARE.md`,
`docs/LEGACY.md` y el handoff `docs/AI_HANDOFF.md`.

### 2.2 Módulos y modelo de datos

Modelos SQLAlchemy en `backend/app/models/`:

| Entidad | Archivo | Rol |
|---|---|---|
| `Organization` | `tenancy.py` | Tenant del SaaS (plan, estado) |
| `User` | `tenancy.py` | Usuario de plataforma con rol RBAC; campos de lockout y MFA (Fase 1) |
| `Site` | `infrastructure.py` | Ubicación física (zona horaria para horarios) |
| `Controller` | `infrastructure.py` | Placa L04: S/N, IP, puerto, online/offline, `interlock_enabled` |
| `Door` | `infrastructure.py` | 1–4 por placa: modo, tiempos, sensor, anti-passback, `first_card_open`, `multi_card_count`, `requires_dual_approval` (Fase 1) |
| `DoorOpenRequest` | `infrastructure.py` | Solicitud de apertura con doble aprobación (Fase 1) |
| `Department` / `Cardholder` / `Credential` | `people.py` | Personal y credenciales; `Credential.pin` cifrado en reposo (Fase 1) |
| `Schedule` + `ScheduleInterval` + `Holiday` | `access.py` | Perfiles horarios semanales y feriados |
| `AccessLevel` + `AccessLevelDoor` | `access.py` | Permisos: puerta + horario, N–N a personas |
| `Event` | `events.py` | Historial y monitoreo en tiempo real |
| `AuditLog` | `events.py` | Auditoría de acciones de usuarios |
| `AuthSession` + `AuthRefreshToken` | `auth_session.py` | Sesiones persistentes y generaciones de refresh (Fase 1) |
| Modelos de asistencia (turnos, licencias, viajes, fichajes) | `attendance.py` | Módulo de asistencia |

Multi-tenancy: cada fila de negocio lleva `organization_id` (mixin `OrgScopedMixin`); todas las
consultas filtran por él. `super_admin` puede operar sobre cualquier organización pasando
`?organization_id=` validado en `app/core/deps.py::get_org_id`. Se verifica con
`test_tenant_isolation`.

Motor de decisión de acceso: `backend/app/services/access_engine.py` replica el orden del
software original (credencial activa → PIN si aplica → persona activa y vigente → modo de puerta →
nivel de acceso incluye la puerta → horario/feriados). Cada lectura genera un `Event` que se
difunde por WebSocket.

### 2.3 Endpoints principales

Todo bajo `/api/v1` (OpenAPI en `/docs`): `auth`, `organizations`, `users`, `sites`,
`controllers`, `doors`, `departments`, `cardholders` (+credenciales, `+/import`,
`+/import-mdb`), `schedules`, `holidays`, `access-levels`, `events` (+`/swipe`), `dashboard`,
`audit-logs`, `attendance`, y WebSocket `/ws/events` para monitoreo en vivo.

Endpoints de `auth` (tras Fase 1), en `backend/app/api/v1/auth.py`:

- `POST /auth/login` — con rate limiting por IP (`auth.py:49`).
- `POST /auth/refresh` — refresh rotativo, con rate limiting (`auth.py:108`).
- `POST /auth/logout` — revoca la sesión actual, idempotente (`auth.py:148`).
- `GET /auth/me` — bootstrap del SPA (las cookies son invisibles a JS) (`auth.py:177`).
- `POST /auth/mfa/setup` · `POST /auth/mfa/enable` · `POST /auth/mfa/disable` — TOTP (`auth.py:182`,`193`,`205`).
- `POST /auth/change-password` (`auth.py:218`).

Endpoints de doble aprobación, en `backend/app/api/v1/doors.py`:

- `POST /doors/{id}/open` — apertura simple; **409** si la puerta requiere doble aprobación (`doors.py:160`).
- `POST /doors/{id}/open-requests` — crea la solicitud pendiente (primer operador) (`doors.py:194`).
- `POST /doors/open-requests/{id}/approve` — aprueba un segundo operador distinto (`doors.py:72`).
- `POST /doors/open-requests/{id}/reject` (`doors.py:120`).
- `GET /doors/open-requests` (`doors.py:53`).

Middleware: `CSRFMiddleware` + `CORSMiddleware` registrados en `backend/app/main.py:41-42`.

### 2.4 Invariantes de seguridad física y de datos

Del handoff (`docs/AI_HANDOFF.md`), vigentes:

1. No abrir/cerrar/configurar/sincronizar una puerta o controladora real sin autorización explícita.
2. Mantener aislamiento multi-tenant y RBAC; nunca filtrar personas, tarjetas, PIN, eventos o
   auditorías entre organizaciones.
3. Las decisiones de acceso respetan credencial, persona, vigencia, nivel, horario, feriados y
   modo de puerta.
4. Cambios de horarios, credenciales, permisos, puertas y eventos quedan auditados.
5. Importaciones CSV/Excel/MDB se validan fila por fila; no se sobrescriben personas ni
   credenciales silenciosamente.
6. No versionar ni publicar claves, credenciales de superadmin, IPs de controladoras, tokens JWT,
   datos de tarjetas ni datos personales.
7. No ejecutar migraciones, `docker compose up`, despliegues, reinicios ni cambios de firmware
   sobre entornos reales sin aprobación.

---

## 3. Fase 1 — Endurecimiento de seguridad (implementado)

La Fase 1 se implementó como una serie de integraciones sobre `claude/develop`. Cada ítem se
desarrolló como un PR acotado (varios "PR #N" reflejados en los commits de integración). Todas las
afirmaciones de esta sección están verificadas contra el árbol de la rama.

### 3.1 Tabla resumen de los 9 ítems

| # | Ítem pedido | Estado | Commit(s) principal(es) | Evidencia |
|---|---|---|---|---|
| 1 | Invalidar sesiones/refresh/WS al suspender | ✅ | `8c95a7d`, endurecido en `1e7eb62`, `13e8062` | `services/sessions.py`, `api/v1/ws.py`, `test_sessions.py` |
| 2 | Sesiones persistentes + refresh rotativo + revocación | ✅ | `8c95a7d`, `1e7eb62`, `13e8062` (integrado en `a8ee723`) | `models/auth_session.py`, `test_sessions.py` (22 tests) |
| 3 | Cookies HttpOnly/Secure/SameSite + CSRF | ✅ | `5d1f03c` | `core/cookies.py`, `core/csrf.py`, `test_cookie_auth.py` |
| 4 | Quitar el JWT de localStorage/URL | ✅ | `5d1f03c` | `frontend/src/api/client.ts`, `context/AuthContext.tsx` |
| 5 | Cifrar PIN recuperable con llave externa a la DB | ✅ | `ed2ec0d` (integrado en `e57d685`) | `core/crypto.py`, `models/people.py`, `test_pin_encryption.py` |
| 6 | Sin credenciales/seed demo en producción | ✅ | `bf81029` (integrado en `aeafefd`) | `core/config.py`, `app/seed.py`, `test_production_safety.py` |
| 7 | Rate limiting + bloqueo + MFA para admins | ✅ | `9399e4b` (7a), `3991f4f` (7b) | `core/ratelimit.py`, `core/totp.py`, `test_login_protection.py`, `test_mfa.py` |
| 8 | Migrar React Router a versión fija + npm audit | ✅ | `0c81394` (integrado en `d643216`) | `frontend/package.json`, `package-lock.json` |
| 9 | Doble aprobación en puertas críticas | ✅ | `d666481` | `services/dual_approval.py`, `api/v1/doors.py`, `test_dual_approval.py` |

Leyenda: ✅ implementado y con pruebas automatizadas en verde. Ninguno de estos ítems requiere
hardware real para su validación (son seguridad de la plataforma web).

### 3.2 Detalle por ítem

#### Ítems 1 y 2 — Sesiones persistentes, refresh rotativo, revocación, corte de WS

**Propósito.** Reemplazar el modelo JWT sin estado por sesiones persistentes y revocables, para
que una suspensión de usuario/organización, un logout o un cambio de contraseña surtan efecto en
la siguiente petición en lugar de esperar a que expire el access token.

**Diseño (tras el endurecimiento del re-audit).**
- Modelo `AuthSession` (una fila por login) + tabla de generaciones `AuthRefreshToken`
  (`session`, `token_hash`, `generation`, `used_at`, `revoked_at`, `replaced_by`, `expires_at`).
  Solo se almacena el **hash SHA-256** de cada refresh token, nunca el token.
- Los access/refresh tokens llevan el id de sesión (`sid`); el refresh además un `jti` aleatorio
  para que cada rotación sea única.
- **Detección de reuso de historia completa:** replay de *cualquier* generación ya emitida (no solo
  la última) revoca toda la familia (sesión + todas las generaciones) → invalida access y refresh.
- **Rotación atómica:** consumo de la generación con `UPDATE ... WHERE used_at IS NULL` y chequeo
  de `rowcount == 1`, respaldado por constraints únicos en `token_hash` y `(session, generation)`.
  Dos refresh concurrentes con el mismo token no pueden ambos tener éxito; el perdedor se trata
  como reuso y se revoca la familia (fail-closed). En SQLite se usa `busy_timeout`.
- **Corte activo de WebSockets:** `ConnectionManager` registra conexiones por org/usuario/sesión y
  expone `close_session/close_user/close_org` que señalan el loop de cada socket
  (`call_soon_threadsafe`). Se invocan desde logout, cambio de contraseña, cambio de rol,
  desactivación de usuario, suspensión de organización y detección de reuso. El loop WS además
  revalida la sesión periódicamente (`ACP_WS_REVALIDATE_SECONDS`) como red de seguridad
  cross-process (para despliegues multi-worker se documenta que hace falta Redis Pub/Sub para
  fan-out inmediato).
- **Enlace sesión↔sujeto:** la sesión debe pertenecer al `sub` del token; un token válidamente
  firmado cuyo `sid` y `sub` discrepan se rechaza sin tocar la sesión real (fix de re-audit
  `13e8062`).
- Purga segura de generaciones/sesiones expiradas al hacer login.

**Archivos/artefactos.** `backend/app/models/auth_session.py`,
`backend/app/services/sessions.py`, `backend/app/api/v1/ws.py`, `backend/app/api/v1/auth.py`,
`backend/app/api/v1/organizations.py`, `backend/app/api/v1/users.py`,
`backend/app/core/security.py`, `backend/app/core/deps.py`, `backend/app/services/events.py`.
Migración `ae2f708080f5_auth_sessions.py` (verificada up/down/up).

**Auditoría.** Se auditan `logout`, `refresh_reuse_detected` y las revocaciones administrativas
(sin almacenar tokens ni hashes).

**Validación.** `backend/tests/test_sessions.py` (22 tests), incluyendo refresh concurrente y
cierre de WebSocket vivo bajo tráfico continuo (regresión de *starvation*). Certificado también en
PostgreSQL vía CI (bloqueo de filas que SQLite no garantiza).

> **Trazabilidad de revisión.** El ítem pasó por dos rondas de auditoría adversarial:
> `1e7eb62` (hallazgos P1: reuso de historia completa, rotación atómica, cierre activo de WS) y
> `13e8062` (revalidación WS que podía ser starved por tráfico del cliente, y binding sesión↔sujeto).
> Es un buen ejemplo del método "PR chico + auditoría + fix" pedido por el dueño.

#### Ítems 3 y 4 — Cookies HttpOnly/Secure/SameSite + CSRF; JWT fuera de localStorage/URL

**Propósito.** Que las sesiones de navegador no expongan JWTs a JavaScript (mitiga robo por XSS) y
eliminar el token de `localStorage` y de las URLs (incluido el handshake WebSocket).

**Diseño.**
- `backend/app/core/cookies.py`: fija/limpia las cookies `acp_access` (HttpOnly, `path=/`),
  `acp_refresh` (HttpOnly, `path=/api/v1/auth`) y `acp_csrf` (legible por JS), con
  `Secure`/`SameSite`/dominio desde settings.
- `backend/app/core/csrf.py`: `CSRFMiddleware` aplica double-submit en métodos no seguros
  autenticados por cookie; las peticiones Bearer (programáticas) y el bootstrap de auth
  (login/refresh/logout, ya cubiertos por SameSite=Lax) quedan exentos.
- `deps.get_current_user` y el handshake `/ws/events` aceptan el access token desde la cookie
  (Bearer sigue soportado para clientes de API); **el WebSocket ya no lleva el token en la URL.**
- `config`: `cookie_secure` / `cookie_samesite` / `cookie_domain`; en producción se rechaza
  `cookie_secure=false` y `SameSite=None` sin `Secure` (ver `config.py:91-94`).
- **Frontend:** `api/client.ts` usa `withCredentials`, elimina todo manejo de token en
  `localStorage`, inyecta `X-CSRF-Token` desde la cookie `acp_csrf` en peticiones no seguras, y la
  URL del WebSocket de eventos no lleva token. `AuthContext` bootstrapea llamando a `/auth/me` y
  cierra sesión vía el endpoint del servidor.

**Archivos.** `backend/app/core/cookies.py`, `backend/app/core/csrf.py`,
`backend/app/api/v1/auth.py`, `backend/app/api/v1/ws.py`, `backend/app/core/deps.py`,
`backend/app/main.py`, `backend/app/core/config.py`, `backend/app/schemas/auth.py`;
`frontend/src/api/client.ts`, `frontend/src/api/index.ts`, `frontend/src/context/AuthContext.tsx`.

**Validación.** `backend/tests/test_cookie_auth.py` (8 tests: flags HttpOnly, auth por cookie,
CSRF requerido/mismatch, exención Bearer, refresh por cookie, logout limpia); la invariante de
cookie segura se cubre en `test_production_safety.py`. Frontend: `tsc` + build limpios.

#### Ítem 5 — Cifrado del PIN recuperable con llave externa a la DB

**Propósito.** El PIN debe seguir siendo **recuperable** (el motor de acceso lo compara y el
hardware real lo sube a la placa), por lo que no puede hashearse; se cifra con **Fernet** en lugar
de guardarse en claro.

**Diseño.**
- `backend/app/core/crypto.py`: Fernet construido desde `ACP_PIN_ENCRYPTION_KEY`, o una clave
  derivada de `ACP_SECRET_KEY` vía HKDF con un *info label* dedicado (distinto de la clave de
  firma JWT). En ambos casos la llave vive **fuera de la base de datos**. Un tipo SQLAlchemy
  `EncryptedString` cifra al escribir y descifra al leer, de modo que `credential.pin` sigue
  devolviendo texto plano al motor de acceso.
- La columna `credentials.pin` guarda ciphertext; se ensancha a 255 con migración
  `b1c2d3e4f5a6_encrypt_credential_pin.py` (up/down/up verificada). PINs en claro previos quedan
  indescifrables y deben reingresarse (no hay datos de producción todavía).
- `CredentialOut` nunca expuso el PIN y sigue sin hacerlo; la auditoría no registra PIN.

**Archivos.** `backend/app/core/crypto.py`, `backend/app/models/people.py`,
`backend/app/core/config.py`, `backend/requirements.txt` (agrega `cryptography`),
`.env.example` (documenta `ACP_PIN_ENCRYPTION_KEY`).

**Validación.** `backend/tests/test_pin_encryption.py` (5 tests: round-trip + rechazo de basura,
ciphertext en reposo, descifrado transparente por el ORM, respuesta omite el PIN, acceso concedido
solo con el PIN correcto).

#### Ítem 6 — Rechazar defaults inseguros y seed demo en producción

**Propósito.** Impedir que un despliegue de producción corra silenciosamente con las credenciales
demo/por defecto pensadas para desarrollo local.

**Diseño.**
- `Settings` falla al arranque (`model_validator`) cuando `ACP_ENVIRONMENT=production` y persiste
  algún default inseguro: `ACP_SECRET_KEY` por defecto o de menos de 32 caracteres, contraseña de
  superadmin por defecto, o `ACP_DEBUG` activo. `production_issues()` lista los problemas
  (`config.py:80-95`).
- El seed demo (contraseñas débiles y conocidas) se niega a correr en producción y ya no imprime
  contraseñas en claro; lee settings en tiempo de llamada para ser testeable.
- La app ya no auto-crea tablas en producción (el esquema lo gestiona Alembic allí).
- `docker-compose` por defecto en desarrollo; producción como opt-in explícito y su comando de
  arranque salta el seed demo cuando `ACP_ENVIRONMENT=production`. `.env.example` y `README`
  documentan los requisitos.

**Archivos.** `backend/app/core/config.py`, `backend/app/main.py`, `backend/app/seed.py`,
`docker-compose.yml`, `.env.example`, `README.md`.

**Validación.** `backend/tests/test_production_safety.py` (8 tests).

#### Ítem 7 — Rate limiting + bloqueo de cuenta + MFA (TOTP)

**7a — Protección de fuerza bruta (`9399e4b`).**
- **Bloqueo por cuenta:** tras `ACP_LOGIN_MAX_ATTEMPTS` fallos consecutivos, la cuenta se bloquea
  `ACP_LOGIN_LOCKOUT_MINUTES` (aun con la contraseña correcta); un login exitoso resetea los
  contadores. Eventos de bloqueo auditados. Columnas nuevas `failed_login_count` / `locked_until`
  en `users` (migración `c2d3e4f5a6b7_login_lockout_fields.py`).
- **Rate limit por IP:** `/auth/login` y `/auth/refresh` limitados a
  `ACP_AUTH_RATE_LIMIT_PER_MINUTE` por IP con un limitador *sliding-window* en memoria
  (`core/ratelimit.py`). Caveat multi-worker documentado (Redis para límite duro cross-process; el
  lockout en DB ya es compartido). El limitador se desactiva por defecto en el entorno de tests.

**7b — MFA TOTP (`3991f4f`).**
- MFA TOTP opt-in (RFC 6238) para cualquier cuenta, pensado sobre todo para admins.
- Endpoints `POST /auth/mfa/setup` (emite secreto + URI `otpauth://`), `/auth/mfa/enable`
  (confirma con un código), `/auth/mfa/disable` (contraseña + código).
- El login exige un TOTP válido si la cuenta tiene MFA: código ausente → prompt de dos pasos
  (401 "MFA code required"); código erróneo cuenta para el lockout. El secreto TOTP se guarda
  **cifrado en reposo** (reutiliza `EncryptedString`) en columnas `users.mfa_secret` /
  `users.mfa_enabled` (migración `d3e4f5a6b7c8_user_mfa_fields.py`). `UserOut` expone
  `mfa_enabled`. Dependencia `pyotp`; enable/disable auditados.

**Archivos.** `backend/app/core/ratelimit.py`, `backend/app/core/totp.py`,
`backend/app/api/v1/auth.py`, `backend/app/models/tenancy.py`, `backend/app/schemas/auth.py`,
`backend/app/core/config.py`.

**Validación.** `backend/tests/test_login_protection.py` (4 tests: lockout, expiración del lock,
reset en éxito, throttle por IP) y `backend/tests/test_mfa.py` (4 tests: flujo
setup+enable+login, código enable inválido, disable, secreto cifrado en reposo).

#### Ítem 8 — React Router a versión fija + npm audit

**Propósito.** Cerrar las advisories de React Router señaladas por `npm audit`.

**Diseño.**
- `react-router-dom` `6.28.1 → 7.18.3`, corrigiendo CVE-2025-68470 (open redirect vía backslash en
  `<Link>`/`useNavigate`) e inyección de constructor vía `deserializeErrors()` en hidratación SSR.
- Bumps transitivos de `nanoid` y `postcss` a versiones parcheadas.
- El uso del router (`BrowserRouter`, `Routes/Route`, `Navigate`, `NavLink`, `Outlet`, `Link`,
  `useLocation`, `useNavigate`) es compatible en v7: sin cambios de código fuente. `npm ci` +
  `npm run build` (tsc + vite) pasan.
- **Fuera de alcance (declarado):** advisory restante de `esbuild` (GHSA-67mh-4wv8-2f99), que solo
  afecta al dev-server local de Vite y cuyo fix requiere el salto mayor Vite 5 → 8; queda para su
  propio PR.

**Archivos.** `frontend/package.json`, `frontend/package-lock.json`.

#### Ítem 9 — Doble aprobación (two-person rule) en puertas críticas

**Propósito.** Una puerta marcada `requires_dual_approval` no puede abrirse por un solo operador.

**Diseño.**
- `POST /doors/{id}/open` sobre una puerta crítica responde **409**.
- Flujo: `POST /doors/{id}/open-requests` (primer operador crea solicitud pendiente) →
  `POST /doors/open-requests/{id}/approve` (un segundo operador **distinto** aprueba; solo esa
  aprobación dispara la apertura del gateway). La auto-aprobación se rechaza (403). Se completan
  con `.../reject` y `GET /doors/open-requests`.
- **Propiedades de seguridad:** la aprobación es un compare-and-set atómico
  (`PENDING → EXECUTED` guardado por estado y expiración): dos aprobadores en carrera no pueden
  abrir ambos. Las solicitudes expiran tras `dual_approval_ttl_seconds` (default 300); una
  solicitud expirada no puede aprobarse y se marca `EXPIRED`. Un comando de gateway fallido marca
  la solicitud `FAILED` (fail-closed): se exige una nueva doble aprobación, no es reutilizable
  silenciosamente. Cada request/approve/reject se audita; el evento de apertura registra los ids
  del solicitante y del aprobador.
- Aislamiento multi-tenant y RBAC preservados (viewers no pueden solicitar ni aprobar; otra
  organización no ve ni aprueba una solicitud).

**Archivos.** `backend/app/services/dual_approval.py`, `backend/app/api/v1/doors.py`,
`backend/app/models/infrastructure.py`, `backend/app/models/base.py`,
`backend/app/schemas/infrastructure.py`, `backend/app/core/config.py`. Migración
`e4f5a6b7c8d9_dual_approval_critical_doors.py` (agrega `doors.requires_dual_approval` y la tabla
`door_open_requests`).

**Validación.** `backend/tests/test_dual_approval.py` (10 tests).

### 3.3 Historial de commits de Fase 1

En orden cronológico sobre `claude/develop` (línea base previa: merge `63b21ba`, 2026-07-10, que ya
traía asistencia, importación legacy y controles avanzados de puerta):

| Commit | Fecha (UTC) | Descripción |
|---|---|---|
| `8c95a7d` | 2026-09-02 | Fase 1 (1–2): sesiones server-side con refresh rotativo y revocación |
| `1e7eb62` | 2026-09-02 | Hallazgos P1 de auditoría de sesiones (tabla de generaciones, rotación atómica, cierre WS) |
| `13e8062` | 2026-09-02 | Fixes de re-auditoría (starvation de revalidación WS, binding sesión↔sujeto) |
| `bf81029` | 2026-09-02 | Fase 1 (6): rechazar defaults inseguros y seed demo en producción |
| `ed2ec0d` | 2026-09-02 | Fase 1 (5): cifrar PINs recuperables en reposo con llave externa a la DB |
| `0c81394` | 2026-09-02 | Fase 1 (8): React Router a versión fija + fixes de npm audit |
| `a8ee723` | 2026-09-02 | Integrar PR #3: sesiones server-side, rotación, revocación |
| `aeafefd` | 2026-09-02 | Integrar PR #4: rechazar defaults/seed demo en producción |
| `e57d685` | 2026-09-02 | Integrar PR #5: cifrar PINs recuperables en reposo |
| `d643216` | 2026-09-02 | Integrar PR #6: React Router v7 + npm audit |
| `0fb75e0` | 2026-09-02 | Linealizar historia Alembic: encadenar migración de PIN tras la de auth-sessions |
| `9399e4b` | 2026-09-02 | Fase 1 (7a): bloqueo de login y rate limiting de auth |
| `3991f4f` | 2026-09-03 | Fase 1 (7b): MFA TOTP |
| `d666481` | 2026-09-03 | Fase 1 (9): doble aprobación (two-person rule) en puertas críticas |
| `5d1f03c` | 2026-09-03 | Fase 1 (3-4): auth por cookie HttpOnly + CSRF; JWT fuera de localStorage/URL |

**Estado de la cadena Alembic (verificado, lineal):**
`fad72c79e7db` (initial) → `995243b73005` (attendance + advanced door) → `ae2f708080f5`
(auth_sessions) → `b1c2d3e4f5a6` (encrypt PIN) → `c2d3e4f5a6b7` (login lockout) →
`d3e4f5a6b7c8` (user MFA) → `e4f5a6b7c8d9` (dual approval). Head único, sin ramas divergentes.

---

## 4. Pendiente — Fases 2 a 7

Nada de lo siguiente está implementado ni validado. Se enumera para que el líder y el auditor
tengan el mapa completo.

| Fase | Trabajo pendiente | Notas |
|---|---|---|
| **2 — Codec de protocolo** | Framing binario real de la controladora N3000/L04, códigos de función | Hoy solo existe el modo `tcp` experimental (`l04_udp.py`, UDP 64 bytes) con constantes `FUNC_*`; **no verificado** contra las placas del proyecto. **No inventar tramas.** |
| **3 — Gateway local (puente)** | Agente puente en Windows con **mTLS** y **cola persistente SQLite** (outbox/inbox), para envolver las DLLs legacy de 32 bits | Las DLLs (`n3k_comm.dll`, etc.) no corren desde el backend Linux. Concepto heredado del proyecto Codex. |
| **4 — Sincronización** | Sincronización plataforma ↔ placa: permisos ("Upload"/"Allow and Upload"), hora, altas/bajas | Los flags de puerta/controladora (anti-passback, interlock, multicard, first-card-open) ya se almacenan y exponen; su **aplicación física** ocurre solo con el adaptador real. |
| **5 — Ingesta de eventos** | Reporte de eventos de la placa a la API vía `POST /api/v1/events/swipe` a través del puente ("Download And Monitor") | El endpoint existe y el motor de decisión en línea funciona; falta el productor real de eventos desde hardware. |
| **6 — Importador MDB por etapas** | Importación robusta de `iCCard3000.mdb` validada fila por fila, sin sobrescribir silenciosamente | Existe `POST /api/v1/cardholders/import-mdb` con detección de tabla vía mdbtools (`services/legacy_mdb.py`); el endurecimiento "por etapas" pedido queda pendiente. |
| **7 — Asistencia / producción** | Endurecimiento operativo final y puesta en producción | El módulo `attendance` existe en la plataforma; la puesta en producción real y su validación quedan pendientes. |

**Funciones de nicho del legacy aún no cubiertas** (de `docs/LEGACY.md`): módulos multifunción
(Meal, Patrol, Meeting, One To More), alta de tarjeta por lector USB WG1028 y por rango,
peripheral control / keypad de acceso, y Controller Task List — todas dependen del adaptador de
hardware real.

---

## 5. Validación y pruebas

- **Suite backend:** `pytest tests -q` desde `backend/`. Conteo actual de funciones de test por
  archivo (verificado): `test_sessions.py` 22, `test_access_flow.py` 11, `test_dual_approval.py`
  10, `test_attendance.py` 9, `test_auth.py` 8, `test_cookie_auth.py` 8, `test_production_safety.py`
  8, `test_infrastructure.py` 7, `test_platform.py` 7, `test_import.py` 5, `test_pin_encryption.py`
  5, `test_login_protection.py` 4, `test_mdb_import.py` 4, `test_mfa.py` 4 → **112 tests**.
  (Los mensajes de commit reportan cifras intermedias — 59, 71, 73, 89, 93 — que reflejan el conteo
  al momento de cada PR; 112 es el total tras integrar todo en la rama.)
- **Lint:** `ruff check app tests` (limpio; CI lintea todo el backend incluido `alembic/`).
- **Migraciones:** cadena Alembic lineal (§3.3); cada migración de Fase 1 se verificó up/down/up.
  Revisar la cadena antes de aplicar y ejecutar **solo en entorno autorizado**.
- **PostgreSQL:** job de CI dedicado que corre la suite en Postgres para certificar el bloqueo de
  filas de la rotación de refresh (que SQLite no garantiza).
- **Frontend:** `npm run build` (`tsc` + `vite`) limpio tras el bump de React Router.

> **Recordatorio del handoff:** UI funcional o tests en verde **no** equivalen a validación en una
> placa real.

---

## 6. Advertencia sobre hardware real

- El modo por defecto es `ACP_GATEWAY_MODE=simulated`. Toda la lógica de negocio (personal,
  permisos, horarios, monitoreo, motor de decisión) funciona completa sin hardware.
- El modo `tcp` (`l04_udp.py`) implementa un protocolo público de placas de 4 puertas en el puerto
  60000, pero **NO está verificado contra las placas N3000 de este proyecto**. No debe usarse en
  producción sin confirmar el protocolo real con el SDK del fabricante o capturando tráfico del
  software legacy.
- **No inventar frames ni asumir compatibilidad.** Toda compatibilidad no comprobada se declara
  experimental.
- Ninguna acción física (abrir/cerrar/sincronizar/configurar puertas o controladoras) debe
  ejecutarse sin autorización humana explícita.

---

## 7. Dudas y gaps para el líder

Puntos detectados durante la reconstrucción, para que el líder decida:

1. **Estado de merge de los PRs de sesiones.** Los mensajes de `1e7eb62` y `13e8062` dicen
   "Not merged", pero sus cambios sí aparecen en el árbol actual de `claude/develop` (integrados vía
   `a8ee723`). Conviene confirmar que la rama refleja la versión endurecida final y no una
   intermedia. (La lectura del código sugiere que sí: existe la tabla `AuthRefreshToken` y el
   binding sesión↔sujeto.)
2. **Conteo de tests.** Los commits citan 59→93 tests en distintos momentos; el total actual en la
   rama es **112**. No pude ejecutar `pytest` en esta sesión (política de no ejecutar); el conteo es
   estático por `def test_`. El líder/DevOps debería correr la suite para confirmar que están todos
   en verde.
3. **Advisory de esbuild pendiente (ítem 8).** Declarada fuera de alcance por requerir el salto
   mayor Vite 5→8. Queda como PR futuro; conviene registrarlo en el backlog para la auditoría.
4. **Caveat multi-worker.** Rate limiter en memoria y fan-out de revocación de WS necesitan Redis
   (Pub/Sub) para un despliegue multi-proceso con garantías duras. Hoy documentado como caveat, no
   implementado. Relevante antes de producción (Fase 7).
5. **PINs legacy indescifrables.** El cambio a cifrado Fernet deja indescifrables los PINs en claro
   previos (el commit indica que no hay datos de producción). Si en algún momento se importa data
   real previa a este cambio, hay que contemplar re-ingreso o una migración de datos específica.
6. **Fase 6 (importador MDB).** Existe funcionalidad de import-mdb, pero el pedido de "por etapas"
   con validación fila por fila reforzada no está completo; conviene precisar el alcance esperado.
7. **Numeración de fases.** La correspondencia Fase 2–7 ↔ trabajo pendiente se infirió del handoff,
   `docs/HARDWARE.md`, `docs/LEGACY.md` y el enunciado del pedido; los prompts originales
   (`prompt_codex_*.md`) son material confidencial no versionado, así que conviene que el líder
   valide los límites exactos de cada fase.

---

*Fin del documento. Mantener actualizado a medida que avancen las fases. Producido por el rol de
Documentación; pendiente de revisión e integración por el Líder.*
