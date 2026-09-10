# Backup y restauración — Control de Acceso / Cerradura Magnética

> Procedimiento canónico de backup **y** restore de la base PostgreSQL.
> `DEPLOYMENT.md` enlaza aquí en lugar de duplicar esta sección.
>
> ⚠️ Los dumps contienen **datos personales, metadata de credenciales y
> auditorías**. Guardarlos en almacenamiento separado y con control de acceso.
> No versionarlos (invariante #6).

## Estado

| Componente | Estado | Nota |
|---|---|---|
| Backup (`scripts/backup_db.sh`) | Probado en CI (fakes) + PG real | Un `pg_dump` fallido hace fallar el script; sin dump parcial. |
| Restore (`scripts/restore_db.sh`) | Probado en CI (fakes + PG real) | Máquina de estados, swap **no destructivo** con reconciliación por señal. |
| Prueba real en PostgreSQL descartable (CI) | **Probado en CI** | Job `backup-restore-postgres`: round-trip, aborto por validación, **rollback post-swap**, `--drop-recovery`, ShellCheck. |
| **Restore drill autorizado en staging** | `PLANNED` / requiere autorización | Distinto del test de CI: ejecución real contra una copia de datos de staging, con el backend detenido. No se corre sin autorización (invariante #7). |

> **Distinción importante:** el job de CI usa una **base PostgreSQL descartable**
> creada y destruida dentro del pipeline — prueba la lógica del script, no los
> datos reales. Un **restore drill** valida el procedimiento contra una copia de
> datos de staging y es una acción operativa separada que requiere autorización.
>
> El endurecimiento vive en **PR #9** (`claude/backup-restore-hardening`),
> pendiente de revisión. No se ejecuta contra producción sin autorización.

## Backup — `scripts/backup_db.sh`

- `umask 077` (dumps solo-dueño).
- **No** usa el pipe `pg_dump | gzip`: vuelca a un temp, **verifica el código de
  salida de `pg_dump`**, rechaza dump vacío, comprime, valida con `gzip -t` y
  publica con **rename atómico**. Un fallo no deja `.sql.gz` ni temporales.
- La retención (`RETENTION_DAYS`) corre **solo tras un backup exitoso**.

```bash
BACKUP_DIR=/srv/acp-backups RETENTION_DAYS=14 scripts/backup_db.sh
```

## Restore — `scripts/restore_db.sh` (máquina de estados, swap no destructivo)

**La base activa nunca se elimina antes de instalar un reemplazo validado.**
Estados: `PREPARING → TEMP_READY → ACTIVE_RENAMED → PROMOTED → SMOKE_OK`, con
`ROLLED_BACK` y `FATAL_MANUAL_RECOVERY` como salidas de recuperación. El estado
se persiste en el journal del lock.

```bash
scripts/restore_db.sh backups/acp-20260906T020000Z.sql.gz --confirm access_control
```

Flujo:
1. Valida argumentos y `gzip -t` **antes** de tocar PostgreSQL.
2. Toma un **mutex** (lockdir con journal: PID, UTC, base objetivo, fase, temp,
   recovery). Un lock existente **nunca** se borra automáticamente.
3. Restaura en una **base temporal** y la **valida** (`alembic_version` +
   `organizations`); código de salida y valor se verifican por separado.
4. Swap por renames: `activa → <db>_recovery_<stamp>`, luego `temp → activa`.
   Si la promoción falla → **rollback automático** `recovery → activa`.
5. **Smoke test** post-swap (`RESTORE_SMOKE_SQL`, configurable); si falla,
   rollback a la recovery (la sospechosa queda como `<db>_failed_<stamp>`).
6. La base anterior se **conserva** como `<db>_recovery_<stamp>` y **NO se borra**.

### Reconciliación ante señales (EXIT/TERM/INT/HUP)

El handler reconcilia desde la **verdad del servidor** (qué bases existen), no
del estado en memoria:
- activa existe, recovery no → pre-swap: elimina solo la temporal.
- activa no, recovery sí → mid-swap: restaura `recovery → activa`.
- activa y recovery existen → post-swap: conserva ambas.
- ninguna existe → **ambiguo: no borra nada y conserva el lock** (fail closed).

### Recuperación de un lock abandonado (explícita, nunca automática)

```bash
scripts/restore_db.sh --release-lock --confirm access_control
```
Muestra el journal y **rehúsa** si el PID registrado sigue vivo. Revisá el
journal y, si un restore quedó interrumpido, **volvé a correr el restore para
reconciliar antes** de liberar el lock.

### Borrado definitivo de una recovery (explícito, separado)

```bash
scripts/restore_db.sh --drop-recovery <db>_recovery_<stamp> --confirm <db>_recovery_<stamp>
```
Adquiere el mismo mutex (rechaza si hay un restore activo), acepta solo
`${POSTGRES_DB}_recovery_*`, exige confirmación exacta y audita el borrado.

## Restore drill en staging (obligatorio antes de confiar en un backup)

1. Entorno **aislado** con una copia de datos de staging (no producción).
2. **Detener el backend** (o escalar a 0) para que no reconecte durante el swap.
3. Restaurar el último dump; verificar conteos, `alembic current`, login de humo.
4. Borrar la recovery con `--drop-recovery`. Registrar fecha y resultado.

## Objetivos (a definir con el dueño)

- **RPO / RTO:** no definidos. Con backup diario, RPO por defecto ≤24 h.
- **DR / failover de DB:** no implementado (sin réplica). Riesgo operacional documentado.
