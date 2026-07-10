import { useState } from 'react';
import { cardholdersApi, doorsApi, eventsApi } from '../api';
import { DataTable, type Column } from '../components/DataTable';
import { Select, TextInput, BTN_SECONDARY } from '../components/FormField';
import { PageHeader } from '../components/Layout';
import { Badge } from '../components/StatusBadge';
import {
  EVENT_TYPES,
  EVENT_TYPE_LABELS,
  eventTone,
  exportCsv,
  formatDateTime,
} from '../lib/format';
import { useFetch } from '../lib/useFetch';
import type { AccessEvent, EventType } from '../types';

const LIMIT = 50;

const TONE_BADGE: Record<string, 'green' | 'red' | 'amber' | 'slate'> = {
  granted: 'green',
  denied: 'red',
  alarm: 'amber',
  other: 'slate',
};

export function ReportsPage() {
  const [type, setType] = useState<string>('');
  const [doorId, setDoorId] = useState<string>('');
  const [cardholderId, setCardholderId] = useState<string>('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [offset, setOffset] = useState(0);

  const { data, loading, error, reload } = useFetch(
    () =>
      eventsApi.list({
        type: (type || undefined) as EventType | undefined,
        door_id: doorId ? Number(doorId) : undefined,
        cardholder_id: cardholderId ? Number(cardholderId) : undefined,
        date_from: dateFrom ? `${dateFrom}T00:00:00` : undefined,
        date_to: dateTo ? `${dateTo}T23:59:59` : undefined,
        limit: LIMIT,
        offset,
      }),
    [type, doorId, cardholderId, dateFrom, dateTo, offset],
  );
  const { data: doorsPage } = useFetch(() => doorsApi.list({ limit: 500 }), []);
  const { data: holdersPage } = useFetch(() => cardholdersApi.list({ limit: 200 }), []);

  const doorName = (id: number | null) =>
    id == null ? '—' : doorsPage?.items.find((d) => d.id === id)?.name ?? `#${id}`;
  const holderName = (id: number | null) => {
    if (id == null) return '—';
    const h = holdersPage?.items.find((x) => x.id === id);
    return h ? `${h.first_name} ${h.last_name}` : `#${id}`;
  };

  const handleExport = () => {
    if (!data || data.items.length === 0) return;
    exportCsv(
      `eventos_${new Date().toISOString().slice(0, 10)}.csv`,
      ['ID', 'Fecha y hora', 'Tipo', 'Mensaje', 'Puerta', 'Persona'],
      data.items.map((ev) => [
        ev.id,
        formatDateTime(ev.occurred_at),
        EVENT_TYPE_LABELS[ev.type] ?? ev.type,
        ev.message,
        doorName(ev.door_id),
        holderName(ev.cardholder_id),
      ]),
    );
  };

  const resetOffset = () => setOffset(0);

  const columns: Column<AccessEvent>[] = [
    { header: 'Fecha y hora', render: (ev) => formatDateTime(ev.occurred_at), className: 'whitespace-nowrap' },
    {
      header: 'Tipo',
      render: (ev) => <Badge tone={TONE_BADGE[eventTone(ev.type)]}>{EVENT_TYPE_LABELS[ev.type] ?? ev.type}</Badge>,
    },
    { header: 'Mensaje', render: (ev) => ev.message },
    { header: 'Puerta', render: (ev) => doorName(ev.door_id) },
    { header: 'Persona', render: (ev) => holderName(ev.cardholder_id) },
  ];

  return (
    <div>
      <PageHeader
        title="Reportes de eventos"
        subtitle="Historial completo de accesos, alarmas y estados"
        actions={
          <button className={BTN_SECONDARY} onClick={handleExport} disabled={!data || data.items.length === 0}>
            ⬇️ Exportar CSV
          </button>
        }
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Select
          value={type}
          onChange={(e) => {
            setType(e.target.value);
            resetOffset();
          }}
          aria-label="Filtrar por tipo de evento"
        >
          <option value="">Todos los tipos</option>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {EVENT_TYPE_LABELS[t]}
            </option>
          ))}
        </Select>
        <Select
          value={doorId}
          onChange={(e) => {
            setDoorId(e.target.value);
            resetOffset();
          }}
          aria-label="Filtrar por puerta"
        >
          <option value="">Todas las puertas</option>
          {(doorsPage?.items ?? []).map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </Select>
        <Select
          value={cardholderId}
          onChange={(e) => {
            setCardholderId(e.target.value);
            resetOffset();
          }}
          aria-label="Filtrar por persona"
        >
          <option value="">Todas las personas</option>
          {(holdersPage?.items ?? []).map((h) => (
            <option key={h.id} value={h.id}>
              {h.last_name}, {h.first_name}
            </option>
          ))}
        </Select>
        <TextInput
          type="date"
          value={dateFrom}
          onChange={(e) => {
            setDateFrom(e.target.value);
            resetOffset();
          }}
          aria-label="Desde"
        />
        <TextInput
          type="date"
          value={dateTo}
          onChange={(e) => {
            setDateTo(e.target.value);
            resetOffset();
          }}
          aria-label="Hasta"
        />
      </div>

      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(ev) => ev.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="No hay eventos con esos filtros"
        emptyHint="Ajusta los filtros o amplía el rango de fechas."
        pagination={data ? { total: data.total, limit: LIMIT, offset, onPageChange: setOffset } : undefined}
      />
    </div>
  );
}
