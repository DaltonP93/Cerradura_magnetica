# Handoff operativo para IA — Control de Acceso / Cerradura Magnética

> **Índice maestro y punto de entrada.** Una IA con solo la URL del repo + este
> archivo debe poder continuar. Este documento fija reglas e invariantes y
> **enlaza** el estado; no duplica estado que envejece — el estado vive en los
> docs enlazados. No autoriza acciones sobre puertas, controladoras ni producción.

## Propósito

Plataforma web SaaS multi-tenant para gestionar controladoras de acceso L04/N3000 compatibles: organizaciones, usuarios, RBAC, puertas, personas, credenciales, horarios, niveles de acceso, eventos, asistencia y auditoría. Reemplaza el software de escritorio legado conservando seguridad física y trazabilidad.

## Línea base — snapshot reproducible

> Un handoff debe decir **qué versión fue auditada** y además **cómo detectar
> divergencia**. Este es el snapshot; abajo están los comandos para comprobarlo.

- **Auditado:** 2026-09-06 13:36 UTC (2026-09-06 10:36 `America/Asuncion`).
- **SHA del código auditado:** `b97f5e3c89d4735e272c17be705a99877accf908`.
- **Rama del código:** `claude/develop` — **PR de integración #7**.
- **`main`:** `beec044f9250168abb7df9322ac045e2f7bd0a40` — **NO contiene** el trabajo actual. Nada de Fases 1–7 está fusionado a `main`.
- **Rama documental:** `claude/docs-consolidation` — **PR documental #8**.
- **Importante:** los documentos canónicos nuevos (`IMPLEMENTATION_STATUS`, `REQUIREMENTS_TRACEABILITY`, `TEST_EVIDENCE`, `HARDWARE_STATUS`, `SECURITY`, `BACKUP_RESTORE`) **existen solo en PR #8** hasta que se integren a `claude/develop`.
- Modo `simulated` por defecto. La comunicación real TCP/UDP con N3000/L04 es **experimental y no verificada** — ver `HARDWARE_STATUS.md`.

### Estado de los PRs (GitHub = fuente de verdad)

| PR | Rama | Base | Estado | Nota |
|---|---|---|---|---|
| #7 | `claude/develop` | `main` | Draft, sin fusionar | Integración de Fases 1–7. |
| #8 | `claude/docs-consolidation` | `claude/develop` | Draft, sin fusionar | Documentación canónica (este archivo y los demás docs de estado). |
| #9 | `claude/backup-restore-hardening` | `claude/develop` | Draft, sin fusionar | Endurecimiento de backup/restore + 12 tests. |
| #10 | `claude/frontend-door-flags-advisory` | `claude/develop` | Draft, sin fusionar | Flags de puerta "no aplicado/experimental" + infra Vitest. |
| #11 | `claude/sec-f2-forwarded-allow-ips` | `claude/develop` | Draft, sin fusionar | **F-2**: sin `--forwarded-allow-ips *`; prod rechaza `*` (fail-fast). |
| #12 | `claude/sec-f1-atomic-lockout` | `claude/develop` | Draft, sin fusionar | **F-1**: incremento atómico del contador de lockout (sin lost updates). |
| #13 | `claude/sec-f4-bridge-secret` | `claude/develop` | Draft, sin fusionar | **F-4**: secreto por-puente además del fingerprint mTLS (fail-closed). |
| #14 | `claude/sec-f3-ws-origin` | `claude/develop` | Draft, sin fusionar | **F-3**: validación de `Origin` en el handshake WS (anti-CSWSH). |
| #15 | `claude/sec-pip-audit` | `claude/develop` | Draft, sin fusionar | **P1 tooling**: `pip-audit` en CI + `cryptography` sin vulnerabilidades. |
| #16 | `claude/sec-card-revocation-outbox` | `claude/develop` | Draft, sin fusionar | **Revocación auto de tarjetas → outbox** (`REVOKE_CARD` por controladora en bridge). |
| #17 | `claude/sec-redis-ratelimit` | `claude/develop` | Draft, sin fusionar | **Redis rate-limit multi-worker (opt-in)** con fallback in-memory; Pub/Sub revocación = follow-up. |
| #18 | `claude/frontend-dual-approval` | `claude/develop` | Draft, sin fusionar | **UI de doble aprobación** (página Aprobaciones, solicitar/aprobar/rechazar) + infra Vitest. |
| #3–#6 | `claude/phase1-*`, `claude/access-control-saas-refactor-6wm329` | `main` | Abiertos | Contenidos en #7 (verificado por `git merge-base`); se conservan como evidencia granular; no cerrados. |

> **Protocolo de continuidad:** GitHub es la única fuente de verdad. Toda unidad
> de trabajo termina en commit → push → PR Draft creado/actualizado → este
> `AI_HANDOFF.md` actualizado (más los docs de estado que correspondan). No se
> deja trabajo importante solo en sesión/terminal/scratchpad/worktree. No se
> fusiona, despliega, cierra PR ni toca hardware/producción sin autorización.

### Comprobar el snapshot y detectar divergencia

```bash
git fetch --all --prune
git rev-parse origin/main
git rev-parse origin/claude/develop
# ¿cuánto cambió el código auditado respecto de main?
git diff --stat beec044f9250168abb7df9322ac045e2f7bd0a40..b97f5e3c89d4735e272c17be705a99877accf908
# ¿el HEAD de develop sigue siendo el auditado?
git rev-parse origin/claude/develop   # debería == b97f5e3... ; si difiere, el código avanzó
```

### Cómo obtener ambas ramas

```bash
git fetch origin claude/develop claude/docs-consolidation
git checkout claude/develop            # el código
git checkout claude/docs-consolidation # la documentación (PR #8)
```

### Orden de lectura recomendado

1. Este archivo (`AI_HANDOFF.md`).
2. `IMPLEMENTATION_STATUS.md` — qué está hecho + backlog P0–P3.
3. `REQUIREMENTS_TRACEABILITY.md` — matriz con IDs estables y evidencia al SHA.
4. `SECURITY.md` — controles + auditoría independiente + hallazgos F-1…F-11.
5. `HARDWARE_STATUS.md` — plataforma vs. placa (nada verificado en hardware).
6. `TEST_EVIDENCE.md`, `DEPLOYMENT.md`, `GATEWAY_BRIDGE.md` según la tarea.

### Primera tarea recomendada

Con #8/#9/#10 consistentes y verdes, la siguiente unidad de trabajo es la
**cola de PRs de fix de seguridad**, cada uno en rama aislada con tests
negativos/de concurrencia, CI verde, cuerpo y handoff actualizados, sin merge:
1. **F-2** — eliminar `--forwarded-allow-ips *`, confiar solo en proxies conocidos.
2. **F-1** — incremento atómico del contador de intentos fallidos (lockout).
3. **F-4** — autenticación real por bridge además del fingerprint.
4. **F-3** — validación de `Origin` en el WebSocket.
5. UI completa de doble aprobación (backend CONFIRMADO por la auditoría).
6. Revocación automática de tarjetas hacia el outbox.
7. Redis para rate-limit y revocación multi-worker.
8. `pip-audit` para backend.

No implementar enforcement real de flags de puerta hasta tener hardware; en su
lugar, reemplazar la constante `ADVANCED_FLAGS_ENFORCED` por capacidades
obtenidas del backend/controladora (la UI debe fallar-cerrado si no las conoce).

## Registro de continuidad (última sesión)

> Bloque que se actualiza al cerrar cada unidad de trabajo. Un agente nuevo debe
> poder continuar leyendo esto + los PRs, sin el historial de chat.

- **Fecha/hora:** 2026-09-07 ~00:45 UTC (2026-09-06 ~21:45 `America/Asuncion`).
- **Repositorio:** `DaltonP93/Cerradura_magnetica`.
- **Ramas / SHA (completo) / PR asociados:**
  - `claude/develop` → PR **#7** (base `main`) — SHA `b97f5e3c89d4735e272c17be705a99877accf908` — código de Fases 1–7. **Draft (verificado por API: `draft:true`).**
  - `claude/docs-consolidation` → PR **#8** (base `develop`) — documentación canónica (este commit avanza el HEAD).
  - `claude/backup-restore-hardening` → PR **#9** (base `develop`) — SHA `e8efcb72738b2d01b022e342112b800dc1677486`.
  - `claude/frontend-door-flags-advisory` → PR **#10** (base `develop`) — SHA `a1e993397938f6e6f1915895f11d56ef1d6997e7`.
- **Cambios en la 2ª ronda de correcciones de la auditoría Codex:**
  - **PR #9 (restore v2):** restore como **máquina de estados** (PREPARING→TEMP_READY→ACTIVE_RENAMED→PROMOTED→SMOKE_OK, +ROLLED_BACK/FATAL_MANUAL_RECOVERY) con **reconciliación por señal desde la verdad del servidor**, journal en el lock (PID/UTC/target/fase/temp/recovery), `--release-lock` explícito (no auto-borra lock abandonado), `--drop-recovery` bajo el mismo mutex, smoke query configurable. 26 tests fake (incl. SIGTERM pre-swap y durante la promoción, rollback fatal que conserva temp+recovery, lock abandonado fail-closed) + **PostgreSQL real en CI** (round-trip, aborto por validación, **rollback post-swap**) + **ShellCheck** en CI.
  - **PR #10 (falsa seguridad):** edición de flags **deshabilitada** con `ADVANCED_FLAGS_ENFORCED=false`; Interlock igual en `ControllersPage`; component tests (RTL+jsdom); Vite 5→7 / Vitest 2→3 → **`npm audit` 0**; CI audita el árbol completo.
  - **PR #8 (docs):** informe de seguridad **versionado** en `docs/audits/SECURITY_AUDIT_2026-09-06.md` (reemplaza el scratchpad); SECURITY/IMPLEMENTATION_STATUS/REQUIREMENTS_TRACEABILITY/BACKUP_RESTORE/este archivo al estado real; BACKUP-001/002 y UI-003 = `OPEN_PR_VERIFIED` (Probado en CI); se distingue **test PG descartable en CI** de **restore drill autorizado en staging**.
- **Pruebas (reales):**
  - Backend + scripts (rama #9) — suite completa **203 passed, 3 skipped** local; `ruff check .` limpio; `sh -n` + `shellcheck` limpios en los 3 scripts.
  - Frontend (rama #10) — `npm test` **7 passed**; `npm run build` (vite 7) OK; `npm audit` **0**.
- **CI (verificado por check runs):**
  - PR #8 `2ee45ea` — **verde** (frontend/backend/backend-postgres).
  - PR #9 `e8efcb7` — **backup-restore-postgres ✅ (PG real + ShellCheck + rollback post-swap)**, frontend ✅, backend ✅; general backend-postgres finalizando al registrar.
  - PR #10 `a1e9933` — **verde** (frontend; backend/backend-postgres del branch también verdes).
- **Migraciones:** ninguna nueva. `claude/develop` mantiene head único `e0f1a2b3c4d5`.
- **Riesgos:** F-1…F-11 (0 P0, 0 P1; 5 P2, 6 P3 — `SECURITY.md` + `docs/audits/`), sin PR de fix aún; backlog P1 (Redis, TLS, migraciones como job, pip-audit).
- **Bloqueos:** el **restore drill en staging** y la validación de hardware requieren autorización. Conteos de **hilos de revisión no consultados** (GraphQL con límites) — no se afirma "cero hilos".
- **PR #11 (F-2, abierto):** eliminado `--forwarded-allow-ips *`; `forwarded_allow_ips` configurable (default `127.0.0.1`), producción **rechaza `*`** (fail-fast); Dockerfile/compose/.env actualizados; 4 tests negativos (`test_production_safety.py` 12 passed). **CI verde (verificado: backend/backend-postgres/frontend).**
- **PR #12 (F-1, abierto):** contador de intentos fallidos con **incremento atómico** (`UPDATE ... failed_login_count + 1 RETURNING`), lockout al umbral en UPDATE atómico + auditoría; ambos caminos (contraseña y MFA) usan el helper. Tests: DB-authoritative + concurrencia (K bumps → K, sin lost updates); suite **179 passed** local. **CI verde (verificado, incl. concurrencia en PostgreSQL real).**
- **PR #13 (F-4, abierto):** SHA `c38bc1d`. La huella mTLS por sí sola ya no autentica: cada puente presenta además un **secreto compartido por-puente** (header configurable `X-Bridge-Secret`), verificado en **tiempo constante** (`secrets.compare_digest` sobre digest SHA-256) contra `GatewayBridge.secret_hash`. Registro genera el secreto (`token_urlsafe(32)`), guarda solo el hash y lo devuelve **una vez** (`GatewayBridgeCreated.secret`). `secret_hash` NULL **no autentica** (fail-closed). Migración `f1a2b3c4d5e6` (padre `e0f1a2b3c4d5`, head único; round-trip up/down/up limpio). Tests nuevos (sin secreto→401, secreto erróneo→401, sin `secret_hash`→401, registro devuelve secreto que autentica y uno erróneo no) + fixtures/tests existentes presentan el secreto. **Probado localmente: 181 passed; `ruff` limpio.** **CI verde (verificado por check runs: backend ✅, backend-postgres ✅ incl. concurrencia/PG real, frontend ✅ — run 34086981504).**
- **PR #14 (F-3, abierto):** SHA `d4b68e8`. El WS de monitoreo (`/ws/events`) autentica por cookie HttpOnly y el handshake WS no está cubierto por SOP/CORS → CSWSH. Se valida `Origin` **antes** de autenticar: si está presente debe estar en `cors_origin_list` (rechazo `1008`); ausente = cliente no-navegador (sin cookie ambiental, no es vector) → permitido, no rompe el path token. Sin migraciones. Tests: handshake cross-origin rechazado pese a token válido; origen permitido aceptado (y luego cerrado por logout). **Probado localmente: 179 passed; `ruff` limpio.** **CI verde (verificado por check runs: backend ✅, backend-postgres ✅, frontend ✅ — run 34087986792).**
- **PR #15 (P1 tooling — pip-audit, abierto):** SHA `f8d425f`. Nuevo paso en el job `backend` de CI: `pip-audit -r requirements.txt` (equivalente Python del `npm audit --omit=dev`; audita solo deps de producción, excluye pytest/ruff/pip-audit). `pip-audit>=2.7` en requirements-dev. `cryptography` sube `>=42,<46` → `>=50.0.1,<51`: la 45.0.7 (tope por `<46`) arrastraba 11 avisos (PYSEC-2026-35/36/2141/3552/3553/3554, GHSA-537c-gmf6-5ccf); 50.0.1 los resuelve todos (Fernet sin cambios de API). **pip-audit: sin vulnerabilidades. Probado localmente: 177 passed; `ruff` limpio.** Sin migraciones. **CI verde (verificado por check runs: backend ✅ incl. el nuevo paso pip-audit, backend-postgres ✅, frontend ✅ — run 34126460448).**
- **PR #16 (revocación auto de tarjetas → outbox, abierto):** SHA `dcb1886`. Desactivar/eliminar una credencial ahora propaga la revocación al caché offline de las placas: nuevo `GatewayCommandType.REVOKE_CARD` + migración `d1e2f3a4b5c6` (`ALTER TYPE ... ADD VALUE` en PostgreSQL vía `autocommit_block`; SQLite = VARCHAR sin CHECK, sin cambio; head único). `command_dispatch.revoke_card_from_boards()` encola en modo `bridge` un `REVOKE_CARD` por cada controladora de la org (no-op en `direct`; el motor ya deniega en línea). Wiring en `PATCH`(activa→inactiva)/`DELETE` de credenciales; auditoría con la tarjeta **enmascarada**. `gateway_effects` no-op seguro en el ack. Tests: bridge encola por-controladora, delete encola, update no-op no encola, direct no encola, aislamiento multi-tenant, claim+ack del REVOKE_CARD. **Probado localmente: 183 passed; `ruff` limpio; migración aplica en SQLite, head único.** **CI verde (verificado por check runs: backend ✅, backend-postgres ✅ — certifica el `ALTER TYPE` + insert de REVOKE_CARD en PostgreSQL real —, frontend ✅ — run 34128099902).** **Integración:** esta migración y la de PR #13 cuelgan ambas de `e0f1a2b3c4d5`; re-encadenar una al integrar a develop.
- **PR #17 (Redis rate-limit multi-worker, abierto):** SHA `0e03229`. El limitador de auth por IP era in-memory (cada worker su propia ventana → límite ×workers). Nuevo `RedisRateLimiter` (ventana fija atómica `INCR`+`EXPIRE NX`) que comparte el contador entre procesos; **fail-open** si Redis cae (el lockout por-cuenta en BD sigue). Selección por `ACP_REDIS_URL` (`config.redis_url`): con URL → Redis, sin URL → in-memory de siempre (default, sin cambios). `redis>=5,<6` (import solo si hay URL); `fakeredis` en dev; `.env.example` documenta la var. Tests con fakeredis (presupuesto compartido entre dos "workers", contraste in-memory, expiración, fail-open, reset). **Probado localmente: 184 passed; `ruff` limpio.** Sin migraciones. **CI verde (verificado por check runs: backend ✅, backend-postgres ✅, frontend ✅ — run 34129500278).** **Revocación multi-worker:** ya acotada por la revalidación de sesión por BD en el WS; Pub/Sub instantáneo queda como follow-up documentado.
- **PR #18 (UI de doble aprobación, abierto):** SHA `f17c962`. El backend ya tenía el flujo de dos personas; ahora el frontend lo expone. Nueva página **Aprobaciones** (`/aprobaciones`): solicitar apertura de puerta crítica (motivo opcional) + tabla de solicitudes con filtro por estado, badges por estado y Aprobar/Rechazar (operador+). Regla de dos personas en UI: *Aprobar* deshabilitado en la propia solicitud. DoorsPage: badge “Doble aprobación”, acción “Solicitar apertura” para puertas críticas, checkbox en el editor. `doorsApi.requestOpen/listOpenRequests/approve/reject`; tipos `DoorOpenRequest(+Status)`; `Door.requires_dual_approval`. **Infra Vitest** (dev-only, Vite 5-compatible → fuera del `npm audit --omit=dev`): vitest 1.x + RTL/jsdom/jest-dom, `vitest.config.ts`, `src/test/setup.ts`, script `npm test`; **5 component tests** de ApprovalsPage; CI (job frontend) corre `npm test` antes del build. **Probado localmente: `npm test` 5 passed; `npm run build` OK; `npm audit --omit=dev` 0.** Sin backend ni migraciones. **CI verde (verificado por check runs: frontend ✅ incl. el nuevo paso `npm test`, backend ✅, backend-postgres ✅ — run 34138265312).** **Integración:** toca `frontend/package.json`+lock y `ci.yml` como PR #10 (su infra Vitest sube Vite a 7); reconciliar al integrar.
- **Trabajo pendiente:** **cola de fixes de la auditoría cerrada** (F-2/F-1/F-4/F-3, pip-audit, revocación→outbox, Redis rate-limit, UI doble aprobación — PRs #11–#18, todos Draft, CI verde, sin fusionar). Follow-ups documentados: Redis Pub/Sub para revocación instantánea multi-worker; integración/re-encadenado de migraciones apiladas (#13 y #16) y de la infra frontend (#10 y #18) al fusionar a `develop`.
- **Próxima tarea recomendada:** a criterio del líder/Codex — integración ordenada de los PRs a `claude/develop`, o nuevos hallazgos. No hay más ítems de la cola de fixes pendientes.

## Diferenciación de estado (obligatoria; no declarar "terminado" a la ligera)

Al reportar una función usar exactamente uno de estos estados y su evidencia:

| Estado | Significado |
|---|---|
| **Implementado** | Código en la rama; aún sin correr pruebas. |
| **Probado localmente** | Pruebas verdes en esta máquina (no en CI). |
| **Probado en CI** | Job de GitHub Actions verde (verificado, con enlace/run). |
| **Simulado** | Funciona solo contra el gateway `simulated`. |
| **Pendiente de revisión** | En un PR Draft, esperando revisión/aprobación. |
| **Pendiente de hardware real** | Requiere placa N3000/L04 para validarse. |
| **Bloqueado** | Depende de spec/autorización/insumo no disponible. |

> "Compila" o "tests simulados en verde" **no** es "terminado". El detalle
> fase→estado→evidencia vive en `IMPLEMENTATION_STATUS.md` y la matriz.

## Mapa de documentación (fuente de verdad por tema)

| Tema | Documento |
|---|---|
| **Qué está hecho** (fase→estado→evidencia) + **backlog P0–P3** | `IMPLEMENTATION_STATUS.md` |
| Matriz de 54 requisitos (requisito→estado→evidencia→faltante) | `REQUIREMENTS_TRACEABILITY.md` |
| Evidencia de tests (177, por archivo, comandos, caveats) | `TEST_EVIDENCE.md` |
| Estado de hardware (plataforma vs. verificado en placa = nada) | `HARDWARE_STATUS.md` |
| Postura de seguridad + reconciliación de hallazgos + riesgos | `SECURITY.md` |
| Backup y **restore** de la DB | `BACKUP_RESTORE.md` |
| Arquitectura técnica | `ARCHITECTURE.md` |
| Integración de hardware / protocolo / codec / Wiegand | `HARDWARE.md` |
| Puente local (outbox/inbox, mTLS, idempotencia) | `GATEWAY_BRIDGE.md` |
| Endurecimiento de despliegue | `DEPLOYMENT.md` |
| Trazabilidad manual N3000 → plataforma (referencia) | `LEGACY.md` |
| Bitácora cronológica (**histórico**, ya no es fuente de estado) | `DEVELOPMENT_LOG.md` |

## Arquitectura confirmada

- `frontend/`: React 18, TypeScript, Vite y Tailwind.
- `backend/`: FastAPI, SQLAlchemy 2, Alembic, API REST y WebSocket.
- PostgreSQL, Docker Compose y Nginx para la interfaz.
- Capa de hardware aislada por `ControllerGateway` (implementaciones `simulated` y `l04_udp` experimental).
- Codec de protocolo aislado en `backend/app/services/protocol/`; puente/outbox en `services/gateway_*.py`; observabilidad en `core/observability.py`+`metrics.py`.
- Detalle en `ARCHITECTURE.md`.

## Invariantes de seguridad física y de datos

> Sede canónica en `SECURITY.md`; se repiten aquí por ser el entrypoint.

1. No abrir, cerrar, configurar ni sincronizar una puerta/controladora real sin autorización explícita.
2. Mantener aislamiento multi-tenant y RBAC; nunca filtrar personas, tarjetas, PIN, eventos o auditorías entre organizaciones.
3. Las decisiones de acceso deben respetar credencial, persona, vigencia, nivel, horario, feriados y modo de puerta.
4. Cambios de horarios, credenciales, permisos, puertas y eventos deben quedar auditados.
5. Importaciones CSV/Excel/MDB se validan fila por fila; no sobrescribir personas o credenciales silenciosamente.
6. No versionar ni publicar claves, credenciales de superadmin, IPs de controladoras, tokens JWT, datos de tarjetas o datos personales.
7. No ejecutar migraciones, `docker compose up`, despliegues, reinicios o cambios de firmware sobre entornos reales sin aprobación.

## Método de trabajo

1. Confirmar `git status --short`, `git log -1` y PRs antes de diagnosticar.
2. Leer `IMPLEMENTATION_STATUS.md` **antes de implementar** — evita reimplementar lo ya hecho (codec, outbox, doble aprobación, etc. ya existen).
3. Leer los documentos de hardware/legacy antes de tocar gateway, acceso, asistencia o migraciones.
4. Proponer un plan, pruebas y rollback antes de afectar control de puertas o datos.
5. Para protocolo/hardware, usar primero simulación y pruebas no destructivas; declarar toda compatibilidad no comprobada como experimental.
6. No confundir UI funcional o tests verdes con validación física en una placa real.

## Validación

```bash
cd backend
pytest tests -q        # 177 tests (ver TEST_EVIDENCE.md)
ruff check app tests
```

Para migraciones, revisar primero la cadena Alembic (`alembic heads` debe dar 1) y ejecutar solo en un entorno autorizado. Para frontend, usar los comandos de `frontend/package.json`.

## Inicio de una sesión

Claude debe empezar indicando: módulo afectado, si toca datos sensibles/hardware, hipótesis, evidencia, pruebas sin riesgo y autorizaciones faltantes. Las acciones físicas requieren confirmación humana explícita.
