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

1. **Verificar en CI la prueba real de restore** (PR #9, job `backup-restore-postgres`) y revisar el PR — el P0 destructivo de restore ya fue corregido allí.
2. Abrir los **PRs de fix de seguridad** empezando por **F-2** (`--forwarded-allow-ips *`) y **F-1** (carrera de lockout), luego F-4/F-3 (ver `SECURITY.md`).
3. UI de doble aprobación: el backend está CONFIRMADO por la auditoría; se puede construir la UI (PR aparte).
No implementar enforcement real de flags de puerta hasta tener hardware.

## Registro de continuidad (última sesión)

> Bloque que se actualiza al cerrar cada unidad de trabajo. Un agente nuevo debe
> poder continuar leyendo esto + los PRs, sin el historial de chat.

- **Fecha/hora:** 2026-09-06 ~19:30 UTC (~16:30 `America/Asuncion`).
- **Repositorio:** `DaltonP93/Cerradura_magnetica`.
- **Ramas / SHA (completo) / PR asociados:**
  - `claude/develop` → PR **#7** (base `main`) — SHA `b97f5e3c89d4735e272c17be705a99877accf908` — código de Fases 1–7. **PR #7 en Draft (verificado por API: `draft:true`).**
  - `claude/docs-consolidation` → PR **#8** (base `develop`) — documentación canónica (este commit avanza el HEAD).
  - `claude/backup-restore-hardening` → PR **#9** (base `develop`) — SHA `df6166c85512744434b5d1199fd80a94f8d6c2fb`.
  - `claude/frontend-door-flags-advisory` → PR **#10** (base `develop`) — SHA `a1e993397938f6e6f1915895f11d56ef1d6997e7`.
- **Cambios en la ronda de correcciones de la auditoría Codex:**
  - **PR #9 (P0 restore):** restore reescrito como **swap no destructivo** (activa→recovery, temp→activa, rollback automático; nunca se dropea la activa antes de instalar el reemplazo), mutex, `ALLOW_CONNECTIONS=false` en la ventana, sin `psql | grep` (exit y valor por separado), `--drop-recovery` explícito. 22 tests fake (rename original/temp/rollback OK/rollback FATAL/smoke/concurrentes/SIGTERM/validación-exit≠0/conservación) + **test real en PostgreSQL** (`test_backup_restore_integration.py` + `scripts/ci/pg_compose_shim.sh` + job CI `backup-restore-postgres`).
  - **PR #10 (falsa seguridad):** edición de anti-passback/first-card/multicard **deshabilitada** mientras `ADVANCED_FLAGS_ENFORCED=false`; Interlock igual en `ControllersPage`; component tests (RTL+jsdom) de `DoorsPage`/`ControllersPage`; Vite 5→7 / Vitest 2→3 → **`npm audit` 0 vulnerabilidades**; CI audita el árbol completo (`--audit-level=high`).
  - **PR #8 (docs):** SECURITY/IMPLEMENTATION_STATUS/REQUIREMENTS_TRACEABILITY/BACKUP_RESTORE/este archivo actualizados al estado real; DA-001 = `OPEN_PR_VERIFIED` (auditoría confirmó CAS); #9/#10 reflejados como PR abiertos (no "PLANNED").
- **Pruebas ejecutadas (reales, locales):**
  - Backend + scripts — `test_backup_restore_scripts.py` **22 passed**, integración **2 skipped** (sin PG local); `ruff check .` limpio; `sh -n` OK.
  - Frontend — `npm test` **7 passed**; `npm run build` (tsc + vite 7) OK; `npm audit` **0**.
- **CI (run IDs reales; conclusión a confirmar al leer GitHub):**
  - PR #8: run `34052867996` — **success** (último commit previo; este commit dispara uno nuevo).
  - PR #9: run `34054465968` (head `df6166c`) — **in_progress** al registrar; incluye el job real de PostgreSQL. **No declarar verde hasta confirmar.**
  - PR #10: run `34054721663` (head `a1e9933`) — **in_progress** al registrar. **No declarar verde hasta confirmar.**
- **Migraciones:** ninguna nueva. `claude/develop` mantiene head único `e0f1a2b3c4d5`.
- **Riesgos:** F-1…F-11 (0 P0, 0 P1; 5 P2, 6 P3 — `SECURITY.md`), sin PR de fix aún; backlog P1 (Redis, TLS, migraciones como job).
- **Bloqueos:** confirmar conclusión de CI de #9/#10; prueba de restore en entorno autorizado y validación de hardware requieren autorización. Los conteos de **hilos de revisión no se consultaron** (API GraphQL con límites) — no se afirma "cero hilos".
- **Trabajo pendiente:** confirmar CI de #9/#10; PRs de fix F-1…F-11; UI de doble aprobación; enforcement real de flags (hardware).
- **Próxima tarea recomendada:** ver "Primera tarea recomendada" arriba (verificar CI real de restore #9; luego F-2 y F-1).

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
