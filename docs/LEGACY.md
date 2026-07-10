# Trazabilidad con el sistema legacy

Este documento mapea el material original del proyecto (carpeta de Drive "Cerradura") contra la plataforma, para saber qué está cubierto, qué es equivalente y qué queda en la hoja de ruta.

## Material de referencia

| Material | Contenido |
|---|---|
| `Access Control Board Manual.doc` | Manual operativo del software N3000 (julio 2015): instalación, login, controladoras, departamentos, usuarios, tarjetas, privilegios, consola, monitoreo, registros, funciones extendidas, asistencia |
| `AccessControl.en software/` | Software legacy (N3000.exe, iCCard3000.mdb, DLLs n3k_*, drivers FTDI) |
| `WGACCESS_NUEVO_ACTUALIZADO/` | Versión actualizada del mismo software |
| `Set up step.png`, `Extended Function.png` | Capturas del software original (login `abc`, funciones extendidas) |
| `prompt_codex_*.md` | Prompts de diseño y revisiones técnicas del proyecto Codex |
| `access-control-platform - codex/` | Monorepo .NET (ASP.NET Core + Next.js + gateway worker) generado por Codex, nivel MVP |

## Cobertura del manual en esta plataforma

| Función del manual | Estado aquí |
|---|---|
| 2.1 Login y operadores | ✅ JWT + RBAC (super_admin/admin/operator/viewer) + auditoría |
| 2.2 Alta de controladora por S/N, IP y puerto 60000 | ✅ `Controllers` (S/N único, IP, puerto, 4 puertas auto-creadas) |
| 2.2.3 Zonas de controladoras | ✅ Equivalente: **Sitios** (con zona horaria) |
| 2.3.1 Departamentos | ✅ CRUD con jerarquía |
| 2.3.2 Usuarios con foto | ✅ Cardholders con `photo_url`, vigencia y notas |
| 2.3.3 Alta de tarjetas | ✅ Manual por número; alta por lector USB WG1028 = roadmap |
| 2.3.5 Tarjeta perdida | ✅ Desactivar credencial (queda en historial) y asignar una nueva |
| 2.4.1 Privilegios por usuario y puerta | ✅ Niveles de acceso (puerta + horario) asignables N-a-N |
| Allow and Upload / Prohibit and Upload | ✅ Botón "Sincronizar permisos" (gateway) |
| 2.5 Consola: Check / Adjust Time / Upload / Monitor / Download | ✅ Ping, Sincronizar hora, Sincronizar permisos, Monitoreo WS; Download de registros = vía puente (ver HARDWARE.md) |
| 2.6 Consulta de registros | ✅ Reportes con filtros + export CSV |
| 2.7.1 Cambio de contraseña | ✅ |
| 2.7.2 Backup de BD | ✅ Nivel infraestructura (Postgres `pg_dump`; documentado) |
| 3.2.3 Time Profiles | ✅ Horarios semanales por intervalos + feriados |
| 3.2.6 Anti-passback | ✅ Flag por puerta (aplicación en placa vía adaptador real) |
| 3.3.1 Remote Open Door | ✅ Con evento y auditoría |
| 5.3 Importación desde Excel (ConsumerNO, Name, CardID, Department) | ✅ `POST /api/v1/cardholders/import` (CSV, cabeceras en inglés o español) |
| Multi-tenant SaaS | ✅ (no existía en el legacy — organizaciones aisladas con planes) |

## Hoja de ruta (funciones extendidas del manual aún no implementadas)

- **Asistencia** (Parte 4): turnos, feriados, permisos/viajes, fichaje manual y reportes de asistencia.
- **Interlock, MultiCard Access, First Card Open, Controller Task List** (3.2.7–3.2.10): flags avanzados de puerta/controladora.
- **Módulos multifunción** (3.4): Meal, Patrol, Meeting, One To More.
- **Importador de `iCCard3000.mdb`**: migración con vista previa desde la base Access legacy.
- **Alta de tarjeta por lector USB WG1028** y por rango.
- **Peripheral control y keypad de acceso** (3.2.4–3.2.5).

## Relación con el proyecto de Codex

El monorepo de Codex (.NET + Next.js) siguió los mismos prompts de diseño y quedó a nivel MVP (según `revision_parcial_siguiente_fase_codex_cerraduras.md`: sin validación de build certificada). Esta plataforma implementa el mismo dominio y las mismas reglas de los prompts —gateway aislado con mock por defecto, sin protocolo inventado, JWT/RBAC, monitoreo en vivo, auditoría— con un stack Python/React más liviano, **con build verificado y 38 tests automatizados en verde**. Los conceptos del proyecto Codex que siguen vigentes como evolución futura están recogidos en la hoja de ruta (outbox/inbox del gateway, importador MDB, doble aprobación de comandos sensibles).
