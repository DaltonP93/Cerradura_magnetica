# Backup y restauración — Control de Acceso / Cerradura Magnética

> Procedimiento canónico de backup **y restore** de la base PostgreSQL.
> `DEPLOYMENT.md` enlaza aquí en lugar de duplicar esta sección.
>
> ⚠️ Los dumps contienen **datos personales, metadata de credenciales y
> auditorías**. Guardarlos en almacenamiento separado y con control de acceso.
> No versionarlos (invariante #6).

## Backup

Script: `scripts/backup_db.sh`. Corre `pg_dump` dentro del servicio compose `db`
(no requiere cliente en el host), comprime con gzip, marca con timestamp UTC y
poda dumps más viejos que `RETENTION_DAYS`.

```bash
# manual
BACKUP_DIR=/srv/acp-backups RETENTION_DAYS=14 scripts/backup_db.sh

# cron (diario 02:00)
0 2 * * *  BACKUP_DIR=/srv/acp-backups /path/to/scripts/backup_db.sh >> /var/log/acp-backup.log 2>&1
```

Variables: `BACKUP_DIR` (def. `./backups`), `RETENTION_DAYS` (def. 14),
`POSTGRES_USER` (def. `acp`), `POSTGRES_DB` (def. `access_control`), `COMPOSE`.

## Restauración

Script: `scripts/restore_db.sh`. **Operación destructiva**: dropea y recrea la
base destino, por eso exige `--force` y está pensado para un **entorno de
verificación aislado**, no para producción a ciegas.

```bash
scripts/restore_db.sh backups/acp-20260906T020000Z.sql.gz --force
```

Pasos que ejecuta:
1. Termina las conexiones abiertas a la base destino.
2. `DROP DATABASE IF EXISTS` + `CREATE DATABASE`.
3. Carga el dump gunzip → `psql` con `ON_ERROR_STOP=1`.

Verificación post-restore (manual):
```bash
docker compose exec -T db psql -U acp -d access_control -c "SELECT count(*) FROM organizations;"
cd backend && alembic current   # confirmar que el head del esquema coincide con el código
```

## Prueba periódica (obligatoria)

**Un backup no probado no es un backup.** Al menos una vez por período de
release:

1. Levantar un entorno compose **aislado** (no producción).
2. Restaurar el último dump con `restore_db.sh ... --force`.
3. Verificar conteos, `alembic current`, y un login de humo.
4. Registrar fecha y resultado.

## Objetivos (a definir con el dueño)

- **RPO / RTO:** no definidos aún. Con backup diario, el RPO por defecto es ≤24 h;
  ajustar la frecuencia del cron según el RPO acordado.
- **DR / failover de DB:** no implementado (sin réplica). Fuera del alcance
  actual; documentar como riesgo operacional.

## Estado

- Backup: **implementado** (`scripts/backup_db.sh`), no ejercido en CI.
- Restore: **implementado** (`scripts/restore_db.sh`), **pendiente de prueba real
  en entorno autorizado** — no se ejecuta sin autorización del dueño (invariante #7).
