# Access Control Platform (Cerradura Magnética)

Plataforma SaaS web multi-tenant para gestionar placas de control de acceso tipo **L04** (controladoras TCP/IP de 4 puertas con lectoras Wiegand). Reemplaza el software de escritorio Windows original ("Access Control Board Software") por una aplicación 100% web, robusta y profesional.

## Funcionalidades

- **Multi-tenant (SaaS)**: organizaciones aisladas, planes, y super administrador de plataforma.
- **Usuarios y roles (RBAC)**: `super_admin`, `admin`, `operator`, `viewer`, con JWT (access + refresh) y auditoría de cada acción.
- **Controladoras L04**: alta por número de serie, IP/puerto, estado online/offline, ping, sincronización de hora y carga de permisos a la placa.
- **Puertas**: 4 por placa, modo (controlada / normalmente abierta / normalmente cerrada), tiempo de apertura, alarma de puerta retenida, sensor, anti-passback y **apertura remota**.
- **Personal y credenciales**: departamentos, personas con vigencia (desde/hasta) y turno asignado, tarjetas, PIN y tarjeta+PIN.
- **Horarios y feriados**: perfiles semanales por intervalos, feriados que bloquean el acceso.
- **Niveles de acceso**: combinaciones puerta + horario asignables a cada persona.
- **Asistencia**: turnos con tolerancias, licencias y viajes de trabajo, fichaje manual correctivo y reporte diario (presente / tarde / salida temprana / ausente / licencia / feriado) calculado desde los mismos eventos de acceso.
- **Funciones avanzadas de puerta**: anti-passback, interlock por controladora, apertura con primera tarjeta y acceso multicard, como el software original.
- **Migración desde el sistema legacy**: importación de personal desde Excel/CSV y directamente desde la base `iCCard3000.mdb` del software viejo (detección automática de la tabla).
- **Monitoreo en tiempo real**: WebSocket con todos los eventos (acceso concedido/denegado, apertura remota, alarmas, online/offline) y panel de prueba de lectura de tarjeta.
- **Motor de decisión de acceso**: replica las reglas del software original (credencial activa → persona activa → vigencia → nivel de acceso → horario → feriados → modo de puerta).
- **Reportes**: historial de eventos filtrable y exportable; dashboard con estadísticas del día.
- **Auditoría**: registro completo de quién hizo qué, cuándo y desde qué IP.

## Arquitectura

```
frontend/   React 18 + TypeScript + Vite + Tailwind (SPA)
backend/    FastAPI + SQLAlchemy 2 + Alembic (API REST + WebSocket)
  app/services/gateway/   Abstracción de hardware:
    simulated.py   Simulador (demo/desarrollo/tests)
    l04_udp.py     Protocolo UDP binario de 64 bytes de las placas L04
docker-compose.yml   Postgres + backend + frontend (nginx)
```

Detalles en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) y [docs/HARDWARE.md](docs/HARDWARE.md).

## Inicio rápido (Docker)

```bash
cp .env.example .env
# editar .env: poner ACP_SECRET_KEY (openssl rand -hex 32)
docker compose up --build
```

- Frontend: http://localhost:8080
- API + documentación OpenAPI: http://localhost:8000/docs

Usuarios demo creados por el seed:

| Rol | Email | Contraseña |
|---|---|---|
| Super admin | `admin@example.com` | `admin1234` |
| Admin organización | `demo-admin@example.com` | `demo1234` |
| Operador | `demo-operator@example.com` | `demo1234` |

> Cambiar estas credenciales en producción (variables `ACP_FIRST_SUPERUSER_*`).

## Desarrollo local

Backend (Python 3.11+):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.seed                 # datos demo (SQLite por defecto)
uvicorn app.main:app --reload      # http://localhost:8000
```

Frontend (Node 22+):

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173 (proxy a :8000)
```

Tests y lint:

```bash
cd backend
pytest tests -q
ruff check app tests
```

Migraciones (producción usa Alembic; en desarrollo las tablas se crean solas):

```bash
cd backend
alembic upgrade head
alembic revision --autogenerate -m "cambio"
```

## Hardware real

Por defecto la plataforma corre con `ACP_GATEWAY_MODE=simulated` (ideal para operar y probar sin placas). Toda la comunicación física está aislada detrás de la interfaz `ControllerGateway`, siguiendo el principio de diseño del proyecto: **no inventar el protocolo del hardware**. Existe además un modo `tcp` experimental (protocolo UDP de 64 bytes, puerto 60000, de controladoras de 4 puertas UHPPOTE-compatibles) que debe verificarse contra las placas N3000 reales antes de producción. Ver [docs/HARDWARE.md](docs/HARDWARE.md) y la trazabilidad completa con el sistema legacy en [docs/LEGACY.md](docs/LEGACY.md).

## Estructura de la API

Todo bajo `/api/v1` (documentación interactiva en `/docs`): `auth`, `organizations`, `users`, `sites`, `controllers`, `doors`, `departments`, `cardholders` (+credenciales), `schedules`, `holidays`, `access-levels`, `events` (+`/swipe`), `dashboard`, `audit-logs`, y WebSocket `/ws/events?token=...` para monitoreo en vivo.

## CI

GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)): lint + tests del backend, verificación de migraciones y build tipado del frontend en cada push/PR.

## Licencia

MIT — ver [LICENSE](LICENSE).
