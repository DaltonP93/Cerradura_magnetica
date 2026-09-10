# Auditoría de seguridad independiente — Agente 4 (solo lectura)

## SHA auditado y verificación del árbol

- **SHA:** `b97f5e3c89d4735e272c17be705a99877accf908`
  (commit "Fase 2: 64-bit Wiegand card numbers + keypad virtual-card-number resolution").
- **Cómo verifiqué el árbol:**
  - `git fetch origin claude/develop` (OK).
  - `git worktree add /tmp/sec-audit b97f5e3c89d4735e272c17be705a99877accf908` → worktree en HEAD desprendido.
  - Dentro del worktree: `git rev-parse HEAD` → `b97f5e3c89d4735e272c17be705a99877accf908` (coincide).
  - Toda la lectura y las pruebas se hicieron sobre `/tmp/sec-audit`, NO sobre el árbol de trabajo del usuario (que estaba en `claude/docs-consolidation`, HEAD distinto). No modifiqué ningún archivo de la aplicación.
- **Tests:** `pytest tests -q` con el venv del proyecto (`/home/user/Cerradura_magnetica/backend/.venv`, que tiene las deps) ejecutado *contra el código del worktree*: **177 passed** en ~275 s. Confirma la línea base de `TEST_EVIDENCE.md`. (El intérprete del sistema `/usr/local/bin/python` no tiene las deps; por eso usé el venv del repo, sin tocar el worktree.)

> Nota sobre docs: en este SHA **no existen** `SECURITY.md`, `IMPLEMENTATION_STATUS.md`, `REQUIREMENTS_TRACEABILITY.md`, `TEST_EVIDENCE.md`, `HARDWARE_STATUS.md`, `BACKUP_RESTORE.md` (los referencia `AI_HANDOFF.md` pero pertenecen a `claude/docs-consolidation`, posterior). La reconciliación de "controles resueltos por el líder" se hizo contra la sección 8 de `docs/DEVELOPMENT_LOG.md`, que sí existe en este SHA y consolida la remediación previa.

## Resumen ejecutivo

Postura general **sólida**. El aislamiento multi-tenant es consistente y correcto en todos los endpoints revisados; RBAC coherente; PIN cifrado en reposo (Fernet); enmascaramiento de tarjetas en eventos/auditoría; rotación de refresh atómica con detección de reuso; doble aprobación con compare-and-set real; outbox idempotente. No encontré P0 ni fuga de aislamiento entre organizaciones ni fuga de PIN.

Los hallazgos son **defensa-en-profundidad y dependencias del borde (edge)**: varios controles de seguridad delegan por completo en una configuración de despliegue correcta (nginx que strippea headers, SameSite, red aislada) sin refuerzo secundario en la app. El más accionable es la confianza en `X-Forwarded-For` desde cualquier peer y la carrera en el lockout.

**Conteo por severidad:**

| Severidad | Cantidad |
|---|---|
| P0 | 0 |
| P1 | 0 |
| P2 | 5 |
| P3 | 6 |

- P2: (1) carrera de lost-update en el lockout; (2) `--forwarded-allow-ips *` → bypass del rate-limit y falsificación de IP; (3) WebSocket sin verificación de Origin (CSWSH bajo SameSite=none); (4) confianza ciega en el header de fingerprint del bridge; (5) MFA sin códigos de recuperación ni reset por admin.
- P3: (6) nº de tarjeta en claro en errores del importador; (7) `/metrics` abierto por defecto + compare no constante; (8) enumeración de usuarios/tenants; (9) fallback latente de `get_or_404`; (10) duplicado concurrente en inbox rompe el lote; (11) doble-submit no idempotente de apertura remota.

---

## Hallazgos (ordenados por severidad)

### P2-1 — Carrera de lost-update en el bloqueo de cuenta (lockout)

```
Hallazgo: El contador de intentos fallidos se incrementa con un read-modify-write en Python
          (no atómico), así que intentos de login concurrentes pierden incrementos y el
          umbral de bloqueo se alcanza más tarde (o nunca bajo suficiente concurrencia),
          debilitando la protección anti-fuerza-bruta.
Severidad: P2
Archivo y función: backend/app/api/v1/auth.py :: login (líneas 61-92); campos en
          app/models/tenancy.py (failed_login_count, locked_until).
Escenario reproducible:
  1. Cuenta existente con login_max_attempts=5, failed_login_count=0.
  2. Enviar N=20 requests POST /api/v1/auth/login concurrentes con contraseña incorrecta.
  3. Cada request ejecuta: SELECT user  ->  user.failed_login_count += 1  ->  db.commit().
     Como el "+=1" opera sobre el valor cargado en cada sesión, varias sesiones leen el
     mismo valor base y escriben base+1 (lost update). El contador final es << 20 y el
     lockout puede no dispararse, permitiendo muchas más adivinanzas de las previstas.
Prueba adversarial (descrita; VERIFICADO por lectura de código, NO ejecutada
  empíricamente por ser una carrera dependiente del scheduler/SQLite y por tanto flaky):
  - Test con threads: crear usuario, lanzar 20 hilos que POSTean credenciales inválidas
    contra TestClient; al terminar, leer user.failed_login_count y user.locked_until.
    Con incremento atómico el usuario quedaría bloqueado (locked_until != None); con el
    código actual, se observa failed_login_count < 20 y frecuentemente locked_until=None.
  - Correcto sería: UPDATE users SET failed_login_count = failed_login_count + 1 ... (SQL
    atómico) o SELECT ... FOR UPDATE dentro de la transacción.
Impacto: Debilitamiento del control de fuerza bruta (invariante de seguridad de acceso).
  Combinado con P2-2 (bypass del rate-limit por IP) el ataque de diccionario se vuelve
  práctico.
Corrección mínima: Incrementar failed_login_count con expresión SQL atómica
  (update(User).where(id==...).values(failed_login_count=User.failed_login_count+1)) y
  releer, o bloquear la fila (with_for_update) antes del read-modify-write. PR separado.
```

### P2-2 — `--forwarded-allow-ips *`: se confía en `X-Forwarded-For` de cualquier peer

```
Hallazgo: uvicorn arranca con "--proxy-headers --forwarded-allow-ips *", así que confía en
          X-Forwarded-For/X-Forwarded-Proto provisto por CUALQUIER cliente. request.client.host
          (usado como clave del rate-limit y como IP registrada en auditoría/sesión) es entonces
          spoofeable si la app es alcanzable fuera del edge de confianza.
Severidad: P2
Archivo y función:
  - backend/Dockerfile líneas 22-25 (CMD uvicorn ... --proxy-headers --forwarded-allow-ips *).
  - Uso: app/core/ratelimit.py :: rate_limit_auth (l.61, ip = request.client.host);
          app/services/audit.py :: record_audit (l.28); app/services/sessions.py :: _client_ip (l.323).
Escenario reproducible:
  1. La app se despliega tal cual (o queda accesible directamente por un fallo de red/routing).
  2. Atacante envía POST /api/v1/auth/login con "X-Forwarded-For: <IP-aleatoria-por-request>".
  3. rate_limit_auth clasifica cada request bajo una IP distinta -> el límite de
     auth_rate_limit_per_minute por IP nunca se alcanza -> intentos ilimitados desde un solo host.
  4. Además, la IP guardada en audit_logs.ip_address y auth_sessions.ip_address es la que el
     atacante elija -> falsificación/repudio de la traza (invariante #4).
Prueba adversarial: enviar 200 logins con XFF rotatorio y observar 0 respuestas 429; y crear
  una sesión con "X-Forwarded-For: 8.8.8.8" y verificar que auth_sessions.ip_address = 8.8.8.8.
  VERIFICADO por lectura (config del CMD + uso directo de request.client.host).
Impacto: Bypass del rate-limit de autenticación; falsificación de la IP en auditoría y en el
  registro de sesión. Solo es seguro si la app es ESTRICTAMENTE inalcanzable salvo por el edge.
Corrección mínima: Restringir --forwarded-allow-ips a la(s) IP(s) del reverse proxy (nunca "*"),
  o derivar la IP del cliente de una cadena XFF validada contra proxies de confianza. PR separado.
```

### P2-3 — WebSocket `/ws/events` sin verificación de Origin (CSWSH bajo SameSite=none)

```
Hallazgo: El handshake del WebSocket acepta autenticación por cookie (fallback al access cookie)
          y NO valida la cabecera Origin. Si ACP_COOKIE_SAMESITE se configura en "none" (valor
          soportado por config.py), un sitio atacante puede abrir el socket con las cookies de la
          víctima (Cross-Site WebSocket Hijacking) y leer el stream de eventos en vivo de su
          organización.
Severidad: P2 (condicionado a SameSite=none; con el default "lax" el navegador no envía la
           cookie cross-site y el ataque no procede -> por eso no es P1).
Archivo y función: backend/app/api/v1/ws.py :: events_ws (l.69-86) — usa
          websocket.cookies.get(ACCESS_COOKIE) y nunca inspecciona websocket.headers["origin"].
          Config: app/core/config.py cookie_samesite: "lax|strict|none".
Escenario reproducible (SameSite=none):
  1. Víctima autenticada (cookie acp_access) visita página del atacante.
  2. La página ejecuta new WebSocket("wss://plataforma/ws/events?organization_id=<org>").
  3. El navegador adjunta la cookie (SameSite=none); _authenticate valida y el socket queda
     abierto; el atacante recibe todos los eventos (ACCESO_CONCEDIDO/DENEGADO con nombre de
     persona en el mensaje, tarjetas enmascaradas, aperturas remotas) de esa organización.
Prueba adversarial: con SameSite=none, conectar el WS desde un Origin ajeno sin token en query
  y confirmar recepción de eventos. VERIFICADO por lectura (ausencia de chequeo de Origin).
Impacto: Exfiltración del stream de monitoreo cross-site -> fuga parcial de PII y de la
  actividad física de puertas. Nota secundaria: /auth/refresh y /auth/logout están exentos de
  CSRF (core/csrf.py _EXEMPT_PATHS) confiando en SameSite; bajo SameSite=none también se vuelven
  forzables cross-site (rotación/logout forzado).
Corrección mínima: Validar Origin en el handshake del WS contra cors_origin_list (rechazar
  1008 si no coincide) cuando la autenticación es por cookie; documentar que SameSite=none
  requiere esa validación. PR separado.
```

### P2-4 — Autenticación del bridge: confianza ciega en el header de fingerprint (spoofeable)

```
Hallazgo: El bridge se autentica SOLO con el fingerprint del certificado cliente pasado en un
          header (ACP_BRIDGE_CERT_HEADER, default X-Client-Cert-Fingerprint). La app confía en
          el header sin secreto secundario. El fingerprint no es secreto (se devuelve en
          GET /gateway/bridges y es derivable de cualquier copia del certificado público). Si el
          edge no strippea un header suministrado por el cliente, o la app es alcanzable
          directamente, un atacante que conozca un fingerprint suplanta al bridge.
Severidad: P2 (depende de config del edge; sin defensa-en-profundidad en la app).
Archivo y función: backend/app/api/v1/gateway_bridge.py :: get_current_bridge (l.41-53);
          endpoints /gateway/commands/claim, /commands/{id}/ack, /gateway/events dependen solo
          de CurrentBridge. Fingerprint expuesto en GatewayBridgeOut (schemas/gateway.py l.19)
          vía list_bridges.
Escenario reproducible:
  1. Atacante obtiene un fingerprint válido (de un admin, de la respuesta de list_bridges, o
     del certificado público del bridge).
  2. POST /api/v1/gateway/commands/claim con "X-Client-Cert-Fingerprint: <fp>" (sin mTLS real).
  3. Si nginx no sobreescribe/strippea ese header, o si la app es accesible sin pasar por nginx,
     get_current_bridge lo acepta -> el atacante reclama y ackea comandos de puerta y, vía
     /gateway/events, inyecta eventos falsos (ACCESO_CONCEDIDO, aperturas) para toda la org.
Prueba adversarial: POST directo al backend con el header y un fingerprint registrado; observar
  200 y comandos leaseados. VERIFICADO por lectura; el enforcement de mTLS vive 100% en el edge.
Impacto: Suplantación de bridge -> control de comandos de hardware encolados y falsificación de
  eventos/auditoría de toda una organización (invariantes #1, #4). Se contiene solo por
  configuración del edge + aislamiento de red.
Corrección mínima: Añadir un secreto por-bridge (token aleatorio emitido en el registro,
  almacenado hasheado, presentado además del fingerprint) de modo que el header por sí solo no
  baste; y/o restringir la red del endpoint /gateway/* al edge. Documentar el strip obligatorio
  del header en el edge (ya está en GATEWAY_BRIDGE.md, pero sin refuerzo en la app). PR separado.
```

### P2-5 — MFA sin códigos de recuperación ni reset administrativo (lockout permanente)

```
Hallazgo: No existen códigos de recuperación de MFA, y NINGÚN endpoint de admin/super_admin puede
          resetear o deshabilitar el MFA de otro usuario. El único deshabilitado es self-service
          (/auth/mfa/disable) y exige contraseña + un código TOTP válido. Un usuario que pierde su
          dispositivo TOTP queda sin forma de recuperación salvo intervención directa en la BD.
Severidad: P2 (disponibilidad/operacional; no compromete confidencialidad).
Archivo y función: backend/app/api/v1/auth.py :: mfa_setup/mfa_enable/mfa_disable (l.182-223).
          update_user (app/api/v1/users.py l.81-110) NO toca campos mfa (UserUpdate no los
          incluye: schemas/auth.py l.61-66) -> ni un admin puede limpiar mfa_secret/mfa_enabled.
Escenario reproducible:
  1. Usuario habilita MFA; luego pierde/borra el authenticator.
  2. Login exige "MFA code required"; /mfa/disable exige un código válido que ya no puede generar.
  3. No hay recovery codes; ningún admin puede resetearlo -> cuenta inaccesible.
Prueba adversarial: N/A (gap funcional verificado por lectura: no hay grep de "recovery" ni
  endpoint de reset; UserUpdate sin campos mfa). VERIFICADO.
Impacto: Pérdida de disponibilidad de la cuenta; incentiva "soluciones" fuera de banda
  (edición directa de BD) que evaden auditoría. Lo positivo: mfa_secret se guarda cifrado
  (EncryptedString) y setup exige 409 si ya está activo (no se puede apagar por re-enrol).
Corrección mínima: Emitir códigos de recuperación de un solo uso al habilitar MFA (hasheados),
  aceptarlos en login/disable; y/o un endpoint de reset de MFA para admin/super_admin con
  auditoría. PR separado.
```

---

### P3-1 — El importador devuelve números de tarjeta en claro en los mensajes de error

```
Hallazgo: Los errores del importador incluyen el número de tarjeta completo sin enmascarar,
          contradiciendo el enmascaramiento (core/masking.py) aplicado en eventos/auditoría
          (invariante #6). Se devuelven al cliente en ImportResult.errors y podrían terminar en
          logs si el cliente/registro los persiste.
Severidad: P3 (el operador que sube el CSV ya conoce las tarjetas; impacto real bajo, pero es
          una inconsistencia con la política de masking).
Archivo y función: backend/app/services/importer.py :: _build_plan
          (l.119 "Card {card} already assigned", l.123 "Card {card} duplicated within the file").
Escenario reproducible: POST /cardholders/import (dry_run) con un CSV cuyas tarjetas ya existen;
  la respuesta ImportResult.errors lista los números completos.
Prueba adversarial: N/A funcional. VERIFICADO por lectura.
Impacto: Exposición de números de tarjeta en claro en respuestas de API y potencialmente en logs.
Corrección mínima: Enmascarar con mask_card() en los mensajes de error del importador. PR separado.
```

### P3-2 — `/metrics` abierto por defecto y comparación de token no constante

```
Hallazgo: Si ACP_METRICS_TOKEN no está configurado (default None) /metrics queda abierto, y esto
          NO figura en production_issues() (no hay fail-fast en producción). Además la comparación
          del token usa "!=" (no tiempo constante).
Severidad: P3.
Archivo y función: backend/app/main.py :: prometheus_metrics (l.79-88);
          app/core/config.py :: production_issues (l.100-115, no valida metrics_token).
Escenario reproducible: desplegar en producción sin ACP_METRICS_TOKEN y sin restricción en el
  edge -> GET /metrics responde 200 con contadores. (Los datos son solo conteos de requests y
  latencia agregada — sin PII — por lo que el impacto es bajo.)
Prueba adversarial: GET /metrics sin cabecera -> 200. VERIFICADO por lectura.
Impacto: Exposición de métricas operativas; timing sobre el token (marginal).
Corrección mínima: Exigir metrics_token en producción (agregar a production_issues) o cerrar por
  defecto; usar secrets.compare_digest para el token. PR separado.
```

### P3-3 — Enumeración de usuarios / tenants

```
Hallazgo: (a) En login, bcrypt solo se ejecuta cuando el usuario existe (verify_password se
          omite si user is None) -> canal de temporización que distingue email existente de
          inexistente. (b) create_user y create_controller comprueban unicidad GLOBAL de email y
          serial (sin filtro de org) y devuelven 409 -> revelan existencia entre organizaciones.
Severidad: P3.
Archivo y función: backend/app/api/v1/auth.py :: login (l.61); app/api/v1/users.py ::
          create_user (l.51, email global); app/api/v1/controllers.py :: create_controller
          (l.64-67, serial global).
Escenario reproducible: medir la latencia de /login para email conocido vs desconocido; o crear
  un usuario con un email de otra org y observar 409 "Email already registered".
Prueba adversarial: descrita; VERIFICADO por lectura.
Impacto: Enumeración de cuentas y de identificadores entre tenants (bajo).
Corrección mínima: Ejecutar un hash "dummy" cuando el usuario no existe (tiempo constante);
  considerar mensajes 409 genéricos. PR separado.
```

### P3-4 — `get_or_404`: fallback latente que evade el filtro de tenant

```
Hallazgo: get_or_404 usa getattr(obj, "organization_id", org_id): si un modelo NO tuviera
          organization_id, el chequeo de tenant pasaría siempre (el default es el propio org_id).
          Hoy NO es explotable: todos los modelos consultados con org_id definen organization_id
          (vía OrgScopedMixin); Organization se consulta sin org_id y solo por super_admin. Es un
          riesgo latente para futuros modelos.
Severidad: P3 (latente, no explotable en este SHA).
Archivo y función: backend/app/api/helpers.py :: get_or_404 (l.13-17).
Prueba adversarial: N/A hoy. VERIFICADO que ningún modelo actual dispara el fallback (revisión de
  app/models/*: todos usan OrgScopedMixin salvo Organization/User/AuthSession, no scoped por org).
Impacto: IDOR cross-tenant si en el futuro se pasa un modelo sin organization_id con org scoping.
Corrección mínima: Requerir el atributo explícitamente (getattr(obj, "organization_id", None) y
  comparar; o hasattr-check que falle cerrado). PR separado.
```

### P3-5 — Inbox: duplicado concurrente del mismo `event_uid` rompe todo el lote

```
Hallazgo: ingest_events deduplica en Python (conjuntos "already"/"seen") pero la unicidad real la
          da la constraint UNIQUE(organization_id, external_id). Dos lotes concurrentes con el
          mismo event_uid pasan ambos el chequeo Python y colisionan en el commit -> IntegrityError
          que falla el lote completo (sin captura por-fila).
Severidad: P3 (robustez; la idempotencia sí se preserva -no hay duplicado almacenado-, pero se
          pierde disponibilidad del lote).
Archivo y función: backend/app/services/gateway_inbox.py :: ingest_events (l.63-101, sin
          try/except sobre IntegrityError); constraint en app/models/events.py l.19.
Escenario reproducible: dos POST /gateway/events concurrentes que compartan un event_uid.
Prueba adversarial: descrita; VERIFICADO por lectura (no hay manejo de IntegrityError).
Impacto: Un reintento concurrente del bridge puede provocar 500 y rechazo de eventos válidos del
  mismo lote.
Corrección mínima: Capturar IntegrityError por evento (savepoints) o hacer INSERT ... ON CONFLICT
  DO NOTHING. PR separado.
```

### P3-6 — Apertura remota no idempotente ante doble-submit (modo bridge)

```
Hallazgo: enqueue_command genera una idempotency_key aleatoria (uuid4) por llamada, así que un
          doble-click / reintento del cliente en POST /doors/{id}/open (modo bridge) encola DOS
          comandos OPEN_DOOR -> la puerta pulsa dos veces. Es una decisión deliberada (comentada)
          para no colapsar dos acciones explícitas, pero no hay soporte de idempotency-key del
          cliente para distinguir "reintento" de "segunda acción".
Severidad: P3 (operacional; para /open no crítico; las puertas críticas van por doble aprobación
          con CAS y no se ven afectadas).
Archivo y función: backend/app/services/command_dispatch.py :: enqueue_command (l.20-34);
          consumido por app/api/v1/doors.py :: open_door (l.217-229).
Escenario reproducible: doble POST /doors/{id}/open con la misma intención -> dos filas en el
  outbox -> dos aperturas.
Prueba adversarial: descrita; VERIFICADO por lectura.
Impacto: Doble apertura física por reintentos de red/UI.
Corrección mínima: Aceptar un Idempotency-Key opcional del cliente y usarlo como clave del
  outbox para colapsar reintentos. PR separado.
```

---

## Cobertura de los 17 puntos solicitados

1. **IDOR endpoint por endpoint** — Revisado `api/v1/*.py` completo. Todo handler que recibe un id filtra por `organization_id` (vía `get_or_404(..., org_id)` o `select(...).where(Model.organization_id==org_id)`). Sin IDOR explotable. Único hueco latente: P3-4.
2. **Aislamiento super_admin vs admin de org** — Correcto. `get_org_id` (core/deps.py l.69-90) fuerza al admin a su org y bloquea `organization_id` ajeno; super_admin debe elegir org explícita. `_get_scoped_user` (users.py l.19-29) impide que un admin alcance un super_admin o usuarios de otra org. Organizations es super_admin-only. VERIFICADO.
3. **`session.user_id` vs JWT `sub`** — Binding real. `get_active_session(db, sid, subject)` exige `session.user_id == sub` (sessions.py l.267-282; deps.py l.34-38; ws.py l.45). `rotate_refresh` rechaza si `session.user_id != expected_user_id` (sessions.py l.130-131). VERIFICADO, correcto.
4. **Cookies / CSRF / fallback token WS** — Cookies HttpOnly + CSRF double-submit con `secrets.compare_digest` (csrf.py). Bearer exento (correcto). Exención de /login /refresh /logout apoyada en SameSite -> ver P2-3 (secundario). Fallback de token WS por query aceptado (para no-browser); WS sin Origin check -> P2-3.
5. **MFA** — setup/enable/disable revisados. Disable exige contraseña + código (re-auth real). Setup 409 si ya activo (no apaga 2FA sin re-auth). **No hay códigos de recuperación ni reset admin** -> P2-5. mfa_secret cifrado. (Nota: la remediación previa del líder cubría el "setup sin re-auth"; confirmado corregido.)
6. **Rate limit multi-worker** — In-process, por proceso (documentado); purga periódica de claves inactivas (ratelimit.py l.44-46). El lockout en BD sí es compartido. Clave = IP -> spoofeable vía P2-2.
7. **Bloqueo concurrente de cuenta** — Carrera de lost-update -> P2-1.
8. **Doble aprobación concurrente** — `claim_for_approval` usa CAS `UPDATE ... WHERE status=PENDING AND expires_at>now` + `rowcount==1` (dual_approval.py l.109-127). Self-approve bloqueado (l.88-91). TTL respetado (l.94-105). Fail-closed. **CORRECTO** — dos aprobadores concurrentes no pueden ejecutar dos aperturas.
9. **Estados tras error del gateway** — Path directo: si el gateway falla, `mark_failed` deja el request en FAILED (doors.py l.144-147). Path bridge: si el comando agota reintentos -> FAILED -> `_finalize_dual_approval(success=False)` -> request FAILED (gateway_effects.py). Sin estados "abiertos" colgados salvo DISPATCHED mientras el bridge no ackea (se resuelve al ack o al agotar lease/reintentos). Correcto.
10. **Reutilización / idempotencia** — Refresh: rotación atómica + revocación de familia ante reuso (sessions.py). Outbox: idempotente por (org, idempotency_key) con manejo de IntegrityError (gateway_outbox.py l.44-79). Inbox: idempotente por (org, event_uid) — con caveat P3-5. enqueue_command deliberadamente no-idempotente -> P3-6.
11. **Expiración** — Sesiones (`expires_at` + `_expired`), open-requests (TTL dual_approval), tokens (exp JWT), lease de comandos (leased_until). Todo verificado.
12. **RBAC en endpoints mutantes** — Coherente: create/update/delete de infraestructura = ADMIN; personas/eventos/asistencia = OPERATOR+; comandos de puerta = OPERATOR+; organizaciones/usuarios = ADMIN/super_admin. super_admin siempre pasa (por diseño). Sin endpoint mutante sin guarda de rol.
13. **Fuga de tokens/PIN/tarjetas/PII** — Tarjetas enmascaradas en eventos/auditoría/inbox/swipe; PIN nunca sale (CredentialOut no lo expone) y viaja cifrado; solo se guardan hashes de tokens; logs estructurados sin query string ni body. Excepción: P3-1 (tarjeta en claro en errores del importador) y payload de sync-permissions guarda nº de tarjeta en claro en el outbox (necesario para el board; auditoría solo cuenta, no números — aceptable por diseño).
14. **Importadores CSV/MDB** — Validación fila por fila, sin sobrescritura silenciosa (tarjeta existente -> error). MDB vía tempfile + subprocess sin shell (sin inyección ni path traversal). Sin inyección de fórmulas (es importación, no exportación). Correcto salvo P3-1.
15. **Auth del gateway / fingerprint mTLS** — Spoofeable si el edge no strippea el header o la app es directa -> P2-4.
16. **`/metrics` sin token** — Abierto por defecto -> P3-2.
17. **Apertura remota e idempotencia** — Puerta crítica -> doble aprobación (bloqueada en /open). /open directo libera la conexión antes de la red. Idempotencia -> P3-6.

---

## Tabla de reconciliación de controles marcados RESUELTOS por el líder

Fuente: `docs/DEVELOPMENT_LOG.md` sección 8 (única fuente de "resueltos" presente en este SHA).

| # | Control marcado resuelto (líder) | Commit citado | Veredicto | Evidencia (archivo:función:línea) |
|---|---|---|---|---|
| 8.1-a | Admin de org podía secuestrar super_admin | `b6690ff` | **CONFIRMADO** | `users.py:_get_scoped_user:19-29` (bloquea target super_admin y otra org); `users.py:update_user:87-88` (solo super_admin otorga super_admin); super_admin platform-level `organization_id=None` soportado en `deps.py:get_org_id:78-85` |
| 8.1-b | `/mfa/setup` rotaba secreto y ponía enabled=False sin re-auth | `b6690ff` | **CONFIRMADO** | `auth.py:mfa_setup:189-193` (409 si mfa_enabled); rotar exige `mfa_disable` con contraseña+código `auth.py:213-223` |
| 8.1-c | Credencial PIN concedida sin PIN (invariante #3) | `511d648` | **CONFIRMADO** | `access_engine.py:_PIN_REQUIRED:42` incluye PIN y CARD_PLUS_PIN; `evaluate_access:148-153` exige PIN; `_pin_matches:45-49` usa `secrets.compare_digest` (tiempo constante) |
| 8.2 | Nº de tarjeta en claro en eventos/auditoría (inv. #6) | `d05bf8f` | **CONFIRMADO con excepción** | Enmascarado en `access_engine.py:219,232`, `events.py(swipe):68`, `gateway_inbox.py:86`. **Excepción NO cubierta:** mensajes de error del importador (`importer.py:119,123`) siguen en claro -> ver P3-1 |
| 8.2 | Evento fantasma si hay rollback (broadcast en flush) | `5a95982` | **CONFIRMADO** | `events.py`: broadcast en `after_commit` (`_flush_pending_broadcasts:151-158`) y descarte en `after_rollback:161-164`; `record_event` bufferiza y no emite en flush (l.204) |
| 8.2 | Rate-limiter acumulaba una entrada por IP | `878b7e0` | **CONFIRMADO** | `ratelimit.py:_sweep:32-36` + gatillo periódico `allow:44-46` |
| 8.2 | Reconexión WS infinita ante sesión revocada | `ed91d2b` | **PARCIAL / NO_VERIFICADO (frontend)** | Backend: WS cierra con 1008 al revocar (`ws.py:110-126`). El tope de reintentos es del frontend (fuera del alcance backend; no verificado en esta auditoría) |
| 8.2 | Desfase TZ (acceso en zona del sitio, asistencia en UTC) | `15a8242` | **CONFIRMADO** | `attendance.py:attendance_report:166-187` recibe `timezone` (IANA, default UTC); `access_engine.py:_local_now:80-89` evalúa horarios en TZ del sitio; fichaje manual convierte aware->UTC (`attendance.py:143-145`) |
| 8.3 | `--proxy-headers` para "IP real" del rate-limit | `6d0f124`/`daaa95e` | **CONFIRMADO pero INTRODUCE RIESGO** | `Dockerfile:22-25` usa `--proxy-headers --forwarded-allow-ips *`; el `*` hace la IP spoofeable -> ver P2-2. El control existe pero su configuración es insegura |
| 8.3 | Relación cookie_secure<->HTTPS + validación fail-fast prod | `6d0f124` | **CONFIRMADO (parcial)** | `config.py:production_issues:100-115` valida secret_key, superuser pass, debug, cookie_secure, SameSite=none+secure. **No** valida metrics_token -> ver P3-2 |
| 8.4 | Liberar transacción antes de la llamada de red al gateway | `7bbd518` | **CONFIRMADO** | `doors.py:open_door:233-237` y `approve_open_request:123-129` (expunge+commit antes de `call_gateway`); `controllers.py:ping/sync_*` igual |

**Conclusión de la reconciliación:** todos los controles críticos que el líder marcó como resueltos están efectivamente presentes y correctos en el SHA auditado. Dos matices: (1) el enmascaramiento de tarjetas no se aplicó a los mensajes del importador (P3-1); (2) el control de "IP real" se implementó con `--forwarded-allow-ips *`, que reintroduce un riesgo de spoofing (P2-2). Ninguno de mis hallazgos refuta un control marcado resuelto; los P2 nuevos son áreas no cubiertas por la ronda previa (lockout concurrente, Origin del WS, secreto del bridge, recuperación de MFA).

---

## Notas de método y limitaciones

- **VERIFICADO** = confirmado por lectura directa del código en el SHA (y, para la línea base, por los 177 tests en verde). **NO_VERIFICADO** se marca explícitamente donde no ejecuté una PoC (P2-1 carrera: descrita, no ejecutada por ser flaky; 8.2 WS reconnect: es lógica de frontend).
- No ejecuté pruebas destructivas, ni contra hardware, ni migraciones. Modo solo lectura respetado: no edité/creé/borré archivos de la aplicación (solo este informe y el worktree temporal `/tmp/sec-audit`).
- Alcance: backend. Frontend (almacenamiento de tokens, tope de reintentos WS, XSS) no auditado en profundidad; el diseño de cookies HttpOnly reduce la superficie de robo de token por XSS.
- Recomendación de priorización de PRs separados: P2-2 (forwarded-allow-ips) y P2-1 (carrera lockout) primero por habilitar fuerza bruta combinada; luego P2-4 (secreto de bridge) y P2-3 (Origin WS); P2-5 (recuperación MFA) por disponibilidad; los P3 como higiene.
```
