import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { doorsApi, eventsApi } from '../api';
import { apiErrorMessage, buildEventsWsUrl } from '../api/client';
import { FormField, Select, TextInput, BTN_PRIMARY } from '../components/FormField';
import { PageHeader } from '../components/Layout';
import { Badge } from '../components/StatusBadge';
import { Spinner } from '../components/Spinner';
import { useAuth } from '../context/AuthContext';
import {
  DENIED_REASON_LABELS,
  EVENT_TYPE_LABELS,
  eventTone,
  formatDateTime,
} from '../lib/format';
import { useFetch } from '../lib/useFetch';
import type { LiveEvent, SwipeResult } from '../types';

const MAX_FEED = 200;

type WsStatus = 'connecting' | 'connected' | 'disconnected';

const TONE_ROW: Record<string, string> = {
  granted: 'border-l-emerald-500 bg-emerald-500/5',
  denied: 'border-l-red-500 bg-red-500/5',
  alarm: 'border-l-amber-500 bg-amber-500/5',
  other: 'border-l-slate-600 bg-slate-800/20',
};

const TONE_BADGE: Record<string, 'green' | 'red' | 'amber' | 'slate'> = {
  granted: 'green',
  denied: 'red',
  alarm: 'amber',
  other: 'slate',
};

function useLiveEvents() {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [status, setStatus] = useState<WsStatus>('connecting');
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const closedRef = useRef(false);

  const connect = useCallback(() => {
    if (closedRef.current) return;
    const url = buildEventsWsUrl();
    if (!url) {
      setStatus('disconnected');
      return;
    }
    setStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      retryRef.current = 0;
      setStatus('connected');
    };
    ws.onmessage = (msg: MessageEvent<string>) => {
      try {
        const data = JSON.parse(msg.data) as LiveEvent;
        if (data && data.kind === 'event') {
          setEvents((prev) => [data, ...prev].slice(0, MAX_FEED));
        }
      } catch {
        // ignore malformed frames
      }
    };
    ws.onclose = () => {
      if (closedRef.current) return;
      setStatus('disconnected');
      const delay = Math.min(30000, 1000 * 2 ** retryRef.current);
      retryRef.current += 1;
      timerRef.current = window.setTimeout(connect, delay);
    };
    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    closedRef.current = false;
    connect();
    return () => {
      closedRef.current = true;
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { events, status };
}

function SwipeTestPanel() {
  const { hasRole } = useAuth();
  const { data: doorsPage } = useFetch(() => doorsApi.list({ limit: 500 }), []);
  const [doorId, setDoorId] = useState<string>('');
  const [cardNumber, setCardNumber] = useState('');
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SwipeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canSwipe = hasRole('operator');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!doorId || !cardNumber) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await eventsApi.swipe({
        door_id: Number(doorId),
        card_number: cardNumber,
        pin: pin || undefined,
      });
      setResult(res);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/60 p-5">
      <h2 className="mb-1 text-sm font-semibold text-slate-200">Probar lectura</h2>
      <p className="mb-4 text-xs text-slate-500">
        Simula la presentación de una credencial en un lector para verificar los permisos configurados.
      </p>
      {!canSwipe ? (
        <p className="rounded-md border border-slate-700 bg-slate-800/50 px-3 py-2 text-xs text-slate-500">
          Tu rol no permite ejecutar pruebas de lectura.
        </p>
      ) : (
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-3">
          <FormField label="Puerta" required>
            <Select value={doorId} onChange={(e) => setDoorId(e.target.value)} required>
              <option value="">Selecciona una puerta…</option>
              {(doorsPage?.items ?? []).map((door) => (
                <option key={door.id} value={door.id}>
                  {door.name}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Número de tarjeta" required>
            <TextInput
              value={cardNumber}
              onChange={(e) => setCardNumber(e.target.value)}
              placeholder="p. ej. 0012345678"
              required
            />
          </FormField>
          <FormField label="PIN (opcional)">
            <TextInput
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="4–8 dígitos"
              inputMode="numeric"
            />
          </FormField>
          <button type="submit" disabled={busy || !doorId || !cardNumber} className={`${BTN_PRIMARY} w-full justify-center`}>
            {busy && <Spinner className="h-4 w-4" />}
            Simular lectura
          </button>
        </form>
      )}

      {error && (
        <div className="mt-4 rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}
      {result && (
        <div
          className={`mt-4 rounded-md border px-4 py-3 text-sm ${
            result.granted
              ? 'border-emerald-500/40 bg-emerald-950/40 text-emerald-200'
              : 'border-red-500/40 bg-red-950/40 text-red-200'
          }`}
        >
          <p className="font-semibold">{result.granted ? '✓ Acceso concedido' : '✕ Acceso denegado'}</p>
          {result.reason && (
            <p className="mt-1 text-xs opacity-80">
              Motivo: {DENIED_REASON_LABELS[result.reason] ?? result.reason}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function MonitoringPage() {
  const { events, status } = useLiveEvents();

  const statusBadge =
    status === 'connected' ? (
      <Badge tone="green">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" /> Conectado
      </Badge>
    ) : status === 'connecting' ? (
      <Badge tone="amber">Conectando…</Badge>
    ) : (
      <Badge tone="red">Desconectado — reintentando</Badge>
    );

  return (
    <div>
      <PageHeader
        title="Monitoreo en vivo"
        subtitle="Flujo de eventos en tiempo real desde los controladores"
        actions={statusBadge}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="overflow-hidden rounded-xl border border-slate-700/60 bg-slate-900/60">
            {events.length === 0 ? (
              <div className="px-6 py-16 text-center text-sm text-slate-500">
                Esperando eventos… Los accesos, alarmas y cambios de estado aparecerán aquí al instante.
              </div>
            ) : (
              <ul className="max-h-[70vh] divide-y divide-slate-800/60 overflow-y-auto">
                {events.map((ev, idx) => {
                  const tone = eventTone(ev.type);
                  return (
                    <li
                      key={`${ev.id}-${idx}`}
                      className={`flex flex-wrap items-center gap-3 border-l-4 px-4 py-3 ${TONE_ROW[tone]}`}
                    >
                      <Badge tone={TONE_BADGE[tone]}>{EVENT_TYPE_LABELS[ev.type] ?? ev.type}</Badge>
                      <span className="min-w-0 flex-1 text-sm text-slate-200">{ev.message}</span>
                      <span className="text-xs text-slate-500">{formatDateTime(ev.occurred_at)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        <SwipeTestPanel />
      </div>
    </div>
  );
}
