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
| Backup (`scripts/backup_db.sh`) | `OPEN_PR_UNVERIFIED` (PR #9) | Endurecido: un `pg_dump` fallido hace fallar el script; sin dump parcial. |
| Restore (`scripts/restore_db.sh`) | `OPEN_PR_UNVERIFIED` (PR #9) | **Swap no destructivo** con rollback (ver abajo). |
| Tests de scripts (fakes) | Probado localmente + en CI | `backend/tests/test_backup_restore_scripts.py` (22). |
| Prueba real en PostgreSQL | Probado en CI | Job `backup-restore-postgres` (`test_backup_restore_integration.py`). |
| Prueba en entorno autorizado / hardware | `PLANNED` / `BLOCKED` | Requiere autorización (invariante #7). |

> El endurecimiento vive en **PR #9** (`claude/backup-restore-hardening`),
> pendiente de revisión. No se ejecuta contra producción sin autorización.

## Backup — `scripts/backup_db.sh`

Corre `pg_dump` dentro del servicio compose `db`. Garantías:

- `umask 077` (dumps solo-dueño).
- **No** usa el pipe `pg_dump | gzip`: vuelca a un temp, **verifica el código de
  salida de `pg_dump`**, rechaza dump vacío, comprime, valida con `gzip -t` y
  publica con **rename atómico**. Un fallo no deja `.sql.gz` ni temporales.
- La retención (`RETENTION_DAYS`) corre **solo tras un backup exitoso**.

```bash
BACKUP_DIR=/srv/acp-backups RETENTION_DAYS=14 scripts/backup_db.sh
# cron diario 02:00
0 2 * * *  BACKUP_DIR=/srv/acp-backups /path/to/scripts/backup_db.sh >> /var/log/acp-backup.log 2>&1
```

## Restore — `scripts/restore_db.sh` (swap no destructivo)

**La base activa nunca se elimina antes de instalar un reemplazo validado.**

```bash
scripts/restore_db.sh backups/acp-20260906T020000Z.sql.gz --confirm access_control
```

Flujo:
1. Valida argumentos y `gzip -t` **antes** de tocar PostgreSQL.
2. Toma un **mutex** (lockdir) para impedir dos restores simultáneos.
3. Restaura el dump en una **base temporal** y la **valida** (`alembic_version` +
   `organizations`); el código de salida y el valor se verifican por separado
   (sin `psql | grep`).
4. Swap por renames: `activa → <db>_recovery_<stamp>`, luego `temp → activa`.
   - Si el segundo rename falla → **rollback automático** `recovery → activa`
     (la base original nunca se pierde). Si el rollback también falla → `FATAL`
     con instrucciones de recuperación manual (no se borra nada).
   - Durante la ventana: `ALLOW_CONNECTIONS=false` + `pg_terminate_backend` para
     que el backend no reconecte. **Aun así, detené el backend antes.**
5. **Smoke test** post-swap; si falla, rollback a la recovery (la sospechosa
   queda como `<db>_failed_<stamp>` para inspección).
6. La base anterior se **conserva** como `<db>_recovery_<stamp>` y **NO se borra**.

Borrado definitivo (acción explícita, separada, solo tras verificar la app):

```bash
scripts/restore_db.sh --drop-recovery <db>_recovery_<stamp> --confirm <db>_recovery_<stamp>
```

## Prueba periódica (obligatoria)

1. Entorno compose **aislado** (no producción).
2. Restaurar el último dump; verificar conteos, `alembic current`, login de humo.
3. Borrar la recovery con `--drop-recovery`. Registrar fecha y resultado.

## Objetivos (a definir con el dueño)

- **RPO / RTO:** no definidos. Con backup diario, RPO por defecto ≤24 h.
- **DR / failover de DB:** no implementado (sin réplica). Riesgo operacional documentado.
