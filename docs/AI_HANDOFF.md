# Handoff operativo para IA — Control de Acceso / Cerradura Magnética

> Actualizado: 2026-09-01. Alcance: código versionado. No autoriza acciones sobre puertas, controladoras ni producción.

## Propósito

Plataforma web SaaS multi-tenant para gestionar controladoras de acceso L04/N3000 compatibles: organizaciones, usuarios, RBAC, puertas, personas, credenciales, horarios, niveles de acceso, eventos, asistencia y auditoría. Reemplaza el software de escritorio legado conservando seguridad física y trazabilidad.

## Arquitectura confirmada

- `frontend/`: React 18, TypeScript, Vite y Tailwind.
- `backend/`: FastAPI, SQLAlchemy 2, Alembic, API REST y WebSocket.
- PostgreSQL, Docker Compose y Nginx para la interfaz.
- Capa de hardware aislada por `ControllerGateway`.
- Documentación necesaria: `README.md`, `docs/ARCHITECTURE.md`, `docs/HARDWARE.md` y `docs/LEGACY.md`.

## Línea base verificada

- Rama principal: `main`.
- Último commit observado al redactar: `63b21ba` (2026-07-10), con interfaz de asistencia, importación legacy y controles avanzados de puerta.
- El modo `simulated` es el predeterminado para desarrollo.
- La comunicación real TCP/UDP con controladoras N3000/L04 es experimental y debe verificarse contra hardware/documentación oficial o capturas reales. Nunca inventar frames ni asumir compatibilidad.

## Invariantes de seguridad física y de datos

1. No abrir, cerrar, configurar ni sincronizar una puerta/controladora real sin autorización explícita.
2. Mantener aislamiento multi-tenant y RBAC; nunca filtrar personas, tarjetas, PIN, eventos o auditorías entre organizaciones.
3. Las decisiones de acceso deben respetar credencial, persona, vigencia, nivel, horario, feriados y modo de puerta.
4. Cambios de horarios, credenciales, permisos, puertas y eventos deben quedar auditados.
5. Importaciones CSV/Excel/MDB se validan fila por fila; no sobrescribir personas o credenciales silenciosamente.
6. No versionar ni publicar claves, credenciales de superadmin, IPs de controladoras, tokens JWT, datos de tarjetas o datos personales.
7. No ejecutar migraciones, `docker compose up`, despliegues, reinicios o cambios de firmware sobre entornos reales sin aprobación.

## Método de trabajo

1. Confirmar `git status --short`, `git log -1` y PRs antes de diagnosticar.
2. Leer los documentos de hardware/legacy antes de tocar gateway, acceso, asistencia o migraciones.
3. Proponer un plan, pruebas y rollback antes de afectar control de puertas o datos.
4. Para protocolo/hardware, usar primero simulación y pruebas no destructivas; declarar toda compatibilidad no comprobada como experimental.
5. No confundir UI funcional o tests verdes con validación física en una placa real.

## Validación

Para cambios backend:

```bash
cd backend
pytest tests -q
ruff check app tests
```

Para migraciones, revisar primero la cadena Alembic y ejecutar solo en un entorno autorizado. Para frontend, usar los comandos definidos en `frontend/package.json`.

## Inicio de una sesión

Claude debe empezar indicando: módulo afectado, si toca datos sensibles/hardware, hipótesis, evidencia, pruebas sin riesgo y autorizaciones faltantes. Las acciones físicas requieren confirmación humana explícita.
