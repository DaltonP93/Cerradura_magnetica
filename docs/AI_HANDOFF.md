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

### Estado de los PRs

| PR | Rama | Estado | Nota |
|---|---|---|---|
| #7 | `claude/develop` | **Draft, sin fusionar** | Integración de Fases 1–7. |
| #8 | `claude/docs-consolidation` | **Draft, sin fusionar** | Solo documentación; base `claude/develop`. |
| #3–#6 | `claude/phase1-*`, `claude/access-control-saas-refactor-6wm329` | **Abiertos** | Contenidos en #7; se conservan como evidencia granular hasta auditar #7 (no cerrados aún). |

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
