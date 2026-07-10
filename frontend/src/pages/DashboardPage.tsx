import { Link } from 'react-router-dom';
import { dashboardApi } from '../api';
import { PageHeader } from '../components/Layout';
import { Badge } from '../components/StatusBadge';
import { ErrorBlock, LoadingBlock } from '../components/Spinner';
import { EVENT_TYPE_LABELS, eventTone, formatDateTime } from '../lib/format';
import { useFetch } from '../lib/useFetch';
import type { EventType } from '../types';

function StatCard({
  label,
  value,
  sub,
  accent = 'text-white',
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/60 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${accent}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

const TONE_BADGE: Record<string, 'green' | 'red' | 'amber' | 'slate'> = {
  granted: 'green',
  denied: 'red',
  alarm: 'amber',
  other: 'slate',
};

export function DashboardPage() {
  const { data, loading, error, reload } = useFetch(() => dashboardApi.get(), []);

  return (
    <div>
      <PageHeader title="Panel de control" subtitle="Resumen operativo de la organización" />

      {loading ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorBlock message={error} onRetry={reload} />
      ) : data ? (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
            <StatCard
              label="Controladores"
              value={`${data.controllers_online}/${data.controllers_total}`}
              sub="en línea / total"
              accent={data.controllers_online === data.controllers_total ? 'text-emerald-400' : 'text-amber-400'}
            />
            <StatCard label="Puertas" value={data.doors_total} />
            <StatCard
              label="Personal"
              value={`${data.cardholders_active}/${data.cardholders_total}`}
              sub="activos / total"
            />
            <StatCard label="Eventos hoy" value={data.events_today} />
            <StatCard
              label="Accesos hoy"
              value={`${data.access_granted_today} / ${data.access_denied_today}`}
              sub="concedidos / denegados"
              accent="text-sky-400"
            />
            <StatCard
              label="Alarmas hoy"
              value={data.alarms_today}
              accent={data.alarms_today > 0 ? 'text-amber-400' : 'text-emerald-400'}
            />
          </div>

          <div className="mt-8">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                Eventos recientes
              </h2>
              <Link to="/reportes" className="text-xs text-sky-400 hover:text-sky-300">
                Ver todos →
              </Link>
            </div>
            <div className="overflow-hidden rounded-xl border border-slate-700/60 bg-slate-900/60">
              {data.recent_events.length === 0 ? (
                <p className="px-4 py-10 text-center text-sm text-slate-500">
                  Sin eventos registrados todavía.
                </p>
              ) : (
                <ul className="divide-y divide-slate-800">
                  {data.recent_events.map((ev) => (
                    <li key={ev.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                      <Badge tone={TONE_BADGE[eventTone(ev.type as EventType)]}>
                        {EVENT_TYPE_LABELS[ev.type as EventType] ?? ev.type}
                      </Badge>
                      <span className="min-w-0 flex-1 truncate text-sm text-slate-300">{ev.message}</span>
                      <span className="text-xs text-slate-500">{formatDateTime(ev.occurred_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
