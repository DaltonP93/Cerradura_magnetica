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
4. `SECURITY.md` — controles + hallazgos + qué está `NO_VERIFICADO`.
5. `HARDWARE_STATUS.md` — plataforma vs. placa (nada verificado en hardware).
6. `TEST_EVIDENCE.md`, `DEPLOYMENT.md`, `GATEWAY_BRIDGE.md` según la tarea.

### Primera tarea recomendada

Completar la **auditoría de seguridad independiente** (endpoint-por-endpoint IDOR,
doble aprobación bajo carrera, fuga en logs) y recién después decidir merge de #7.
No implementar enforcement de flags de puerta ni UI de doble aprobación hasta ese informe.

## Registro de continuidad (última sesión)

> Bloque que se actualiza al cerrar cada unidad de trabajo. Un agente nuevo debe
> poder continuar leyendo esto + los PRs, sin el historial de chat.

- **Fecha/hora:** 2026-09-06 18:46 UTC (2026-09-06 15:46 `America/Asuncion`).
- **Repositorio:** `DaltonP93/Cerradura_magnetica`.
- **Ramas / SHA / PR asociados:**
  - `claude/develop` → PR **#7** (base `main`) — SHA `b97f5e3` — código de Fases 1–7.
  - `claude/docs-consolidation` → PR **#8** (base `develop`) — documentación canónica.
  - `claude/backup-restore-hardening` → PR **#9** (base `develop`) — SHA `4e1e9d8`.
  - `claude/frontend-door-flags-advisory` → PR **#10** (base `develop`) — SHA `20856e0`.
- **Cambios realizados esta sesión:**
  - Auditoría multiagente (funcional, DevOps, documentación, seguridad independiente) consolidada.
  - PR #8: docs canónicos (este archivo, `IMPLEMENTATION_STATUS`, `REQUIREMENTS_TRACEABILITY`, `TEST_EVIDENCE`, `HARDWARE_STATUS`, `SECURITY`, `BACKUP_RESTORE`); `DEVELOPMENT_LOG` marcado histórico; README con "Estado y continuidad".
  - PR #9: `backup_db.sh`/`restore_db.sh` endurecidos (propagación de error real, `gzip -t`, restore por base temporal + swap, `--confirm <DB_NAME>`) + 12 tests con `docker compose` falso.
  - PR #10: flags de puerta marcados "no aplicado/experimental" en la UI (sin enforcement) + infra Vitest + 5 tests + paso de CI.
- **Pruebas ejecutadas (reales):**
  - Backend (develop + tests de scripts) — **189 passed** local (177 + 12); `ruff check .` limpio.
  - Frontend — **5 passed** (`npm test`); `npm run build` (tsc + vite) OK.
  - CI de #8/#9/#10 en GitHub Actions: **pendiente de verificar** (ver "Bloqueos").
- **Migraciones:** ninguna nueva en #8/#9/#10. `claude/develop` mantiene head único `e0f1a2b3c4d5`.
- **Riesgos:** seguridad F-1…F-11 (0 P0, 0 P1; 5 P2, 6 P3 — ver `SECURITY.md`), cada uno pendiente de su PR de fix; backlog operativo P1 (Redis, TLS, migraciones como job, prueba real de restore). Vitest agrega vulns de tooling dev (no afectan `npm audit --omit=dev`).
- **Bloqueos:**
  - Al momento de este registro, la API REST de GitHub estuvo con *rate limit*; la conversión de **PR #7 a Draft** y su tabla de contención de #3–#6 quedó **pendiente de aplicar** (los `git push` sí funcionaron).
  - Prueba real de restore y toda validación de hardware: requieren entorno/placa autorizados.
- **Trabajo pendiente:** aplicar Draft+cuerpo a #7; abrir PRs de fix para F-1…F-11; verificar CI de #8/#9/#10; UI de doble aprobación (tras auditar su backend); enforcement de flags (P0-1).
- **Próxima tarea recomendada:** PRs de fix **F-2** (`--forwarded-allow-ips *`) y **F-1** (carrera de lockout) — juntos habilitan fuerza bruta; ramas separadas con tests. Luego F-4/F-3.

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
