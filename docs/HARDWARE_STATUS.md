# Estado de hardware — Control de Acceso / Cerradura Magnética

> Tabla única de "qué está implementado en plataforma **vs.** qué está verificado
> contra una placa N3000/L04 real". El detalle técnico vive en `HARDWARE.md`
> (protocolo/codec/Wiegand) y `GATEWAY_BRIDGE.md` (puente); este doc no los
> duplica, los resume y enlaza.
>
> **Resumen en una línea: NADA está verificado contra hardware real.** Todo lo
> físico es simulado o experimental.

## Regla de oro (invariante del proyecto)

No se abre, cierra, configura ni sincroniza una puerta/controladora real sin
**autorización humana explícita**. No se inventan tramas ni se asume
compatibilidad. Un test verde del codec **no** prueba compatibilidad con la placa.

## Tabla de estado

| Capa | Implementado en plataforma | Verificado en hardware real | Estado | Detalle |
|---|:---:|:---:|---|---|
| Motor de decisión de acceso | ✅ | n/a (lógica pura) | `OPEN_PR_VERIFIED` | `access_engine.py`; 15 tests |
| Gateway `simulated` (default) | ✅ | n/a | `OPEN_PR_VERIFIED` | `gateway/simulated.py`; responde siempre |
| Codec de protocolo 64 bytes | ✅ | ❌ | `BLOCKED_SPEC` | `services/protocol/`; vectores **sintéticos**, no capturas reales |
| Tarjeta 64-bit / virtual card number | ✅ | ❌ | `OPEN_PR_VERIFIED` (plataforma) | Basado en datasheets de lectora (`HARDWARE.md`), no en placa |
| Driver `l04_udp` (modo `tcp`) | ✅ (experimental) | ❌ | `BLOCKED_HARDWARE` | Layout público UHPPOTE-compatible; **no** verificado contra N3000 |
| Puente local: outbox/claim/ack | ✅ | ❌ | `OPEN_PR_VERIFIED` (contrato) | `gateway_outbox.py`; el daemon puente real es externo |
| Puente: auth por fingerprint mTLS | ✅ | ❌ | `OPEN_PR_VERIFIED` (contrato) | `gateway_bridge.py`; verificación de cert en el borde |
| Inbox de eventos de placa | ✅ (endpoint) | ❌ | `BLOCKED_HARDWARE` | `gateway_inbox.py`; falta el productor físico real |
| Flags avanzados de puerta | ⚠️ solo persistencia | ❌ | `PARTIAL` | Sin enforcement en el motor |
| Alta por lector USB WG1028 | ❌ | ❌ | `PLANNED` | Requiere hardware en el puesto |
| Apertura remota / consola (Check/Time/Upload) | ✅ sobre `simulated` | ❌ | `SIMULATED_ONLY` | Efecto físico requiere adaptador real |

## Qué haría falta para pasar de "plataforma" a "hardware verificado"

1. **Confirmar el wire protocol real N3000**, por una de dos vías:
   - Envolver las DLLs legacy (`n3k_comm.dll`, 32-bit Windows) en un daemon puente que hable HTTP con esta API, o
   - Capturar tráfico UDP/TCP del software legacy contra una placa real (Wireshark) y documentar las tramas.
2. **Implementar/ajustar el adaptador real** detrás de `ControllerGateway` (los códigos `FUNC_*` en `codec.py` se ajustan cuando se confirme el protocolo; el resto de la plataforma no cambia).
3. **Validar contra una placa** en un entorno autorizado, con pruebas no destructivas primero.

Ver `HARDWARE.md` §"Camino recomendado hacia el hardware real" y `GATEWAY_BRIDGE.md`.
