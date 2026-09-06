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
| Backup (`scripts/backup_db.sh`) | `OPEN_PR_UNVERIFIED` | Script existe, **pero tiene un defecto conocido** (ver abajo). No ejercido en CI. |
| Restore | `PLANNED` | **No hay script confiable todavía.** El endurecimiento (backup + restore + tests) va en un PR operativo separado: rama `claude/backup-restore-hardening`. |
| Prueba de restore | `PLANNED` | Un backup sin restore probado **no es un backup**. |
| RPO / RTO | `PLANNED` | A definir con el dueño. |

> **Este documento (PR #8) es solo documentación.** El script y sus pruebas se
> entregan en el PR operativo, no acá.

## Defecto conocido del backup actual (P0)

`scripts/backup_db.sh` corre bajo `#!/usr/bin/env sh` con `set -eu` pero **sin
`pipefail`**, y usa un pipeline `pg_dump ... | gzip > out`. Como `sh` toma el
código de salida del **último** comando del pipeline (`gzip`), **un `pg_dump`
fallido puede reportarse como éxito** y dejar un `.gz` parcial (~20 bytes) que
parece un backup válido. Reproducción:

```sh
COMPOSE=/bin/false scripts/backup_db.sh   # imprime "Backup complete", código 0, gz basura
```

Esto se corrige en el PR operativo `claude/backup-restore-hardening`.

## Backup — uso previsto (una vez endurecido)

```bash
# manual
BACKUP_DIR=/srv/acp-backups RETENTION_DAYS=14 scripts/backup_db.sh

# cron (diario 02:00)
0 2 * * *  BACKUP_DIR=/srv/acp-backups /path/to/scripts/backup_db.sh >> /var/log/acp-backup.log 2>&1
```

Variables: `BACKUP_DIR` (def. `./backups`), `RETENTION_DAYS` (def. 14),
`POSTGRES_USER` (def. `acp`), `POSTGRES_DB` (def. `access_control`), `COMPOSE`.

## Restore — requisitos del PR operativo (aún no implementado)

El script de restore **no existe todavía como componente confiable**. El PR
operativo debe garantizar, con pruebas automatizadas (fakes):

- Validar argumentos **antes** de contactar PostgreSQL.
- `gzip -t` sobre el dump **antes** de tocar la base; rechazar dump vacío o corrupto.
- Validación estricta de `DB_NAME`/`DB_USER`; rechazar `postgres`, `template0`, `template1`.
- Confirmación asociada al **nombre exacto** de la base (no un `--force` genérico).
- Propagación de errores en pipelines (`pipefail` o equivalente POSIX); nunca anunciar éxito si `gunzip`/`psql`/validación fallan.
- Restaurar preferentemente en una **base temporal**, validar (esquema, org de prueba, revisión Alembic) y recién entonces reemplazar el destino; limpiar la temporal ante error.
- Impedir que el backend esté reconectándose durante el reemplazo.
- Documentar el rollback de una restauración fallida.

## Prueba periódica (obligatoria una vez exista el restore)

1. Levantar un entorno compose **aislado** (no producción).
2. Restaurar el último dump.
3. Verificar conteos, `alembic current`, y un login de humo.
4. Registrar fecha y resultado.

> No ejecutar restore contra producción. No se ejecuta sin autorización del
> dueño (invariante #7).
