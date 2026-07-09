import { useState } from 'react';
import { auditApi } from '../api';
import { DataTable, type Column } from '../components/DataTable';
import { TextInput } from '../components/FormField';
import { PageHeader } from '../components/Layout';
import { Badge } from '../components/StatusBadge';
import { formatDateTime } from '../lib/format';
import { useDebounced, useFetch } from '../lib/useFetch';
import type { AuditLog } from '../types';

const LIMIT = 50;

const ACTION_TONE: Record<string, 'green' | 'red' | 'amber' | 'sky' | 'slate'> = {
  create: 'green',
  update: 'sky',
  delete: 'red',
  login: 'slate',
};

export function AuditPage() {
  const [actionFilter, setActionFilter] = useState('');
  const [resourceFilter, setResourceFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [offset, setOffset] = useState(0);

  const action = useDebounced(actionFilter);
  const resourceType = useDebounced(resourceFilter);

  const { data, loading, error, reload } = useFetch(
    () =>
      auditApi.list({
        action: action || undefined,
        resource_type: resourceType || undefined,
        date_from: dateFrom ? `${dateFrom}T00:00:00` : undefined,
        date_to: dateTo ? `${dateTo}T23:59:59` : undefined,
        limit: LIMIT,
        offset,
      }),
    [action, resourceType, dateFrom, dateTo, offset],
  );

  const columns: Column<AuditLog>[] = [
    { header: 'Fecha y hora', render: (l) => formatDateTime(l.created_at), className: 'whitespace-nowrap' },
    {
      header: 'Acción',
      render: (l) => (
        <Badge tone={ACTION_TONE[l.action] ?? 'slate'}>
          <span className="font-mono">{l.action}</span>
        </Badge>
      ),
    },
    { header: 'Recurso', render: (l) => <span className="font-mono text-xs">{l.resource_type}</span> },
    { header: 'ID recurso', render: (l) => l.resource_id ?? '—' },
    { header: 'Usuario (ID)', render: (l) => l.user_id ?? '—' },
    { header: 'IP', render: (l) => <span className="font-mono text-xs">{l.ip_address ?? '—'}</span> },
    {
      header: 'Detalles',
      render: (l) =>
        l.details ? (
          <code className="block max-w-xs truncate text-xs text-slate-400" title={JSON.stringify(l.details)}>
            {JSON.stringify(l.details)}
          </code>
        ) : (
          '—'
        ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Auditoría"
        subtitle="Registro de todas las acciones realizadas por los usuarios de la plataforma"
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <TextInput
          value={actionFilter}
          onChange={(e) => {
            setActionFilter(e.target.value);
            setOffset(0);
          }}
          placeholder="Acción (create, update, delete…)"
          aria-label="Filtrar por acción"
        />
        <TextInput
          value={resourceFilter}
          onChange={(e) => {
            setResourceFilter(e.target.value);
            setOffset(0);
          }}
          placeholder="Tipo de recurso (door, cardholder…)"
          aria-label="Filtrar por tipo de recurso"
        />
        <TextInput
          type="date"
          value={dateFrom}
          onChange={(e) => {
            setDateFrom(e.target.value);
            setOffset(0);
          }}
          aria-label="Desde"
        />
        <TextInput
          type="date"
          value={dateTo}
          onChange={(e) => {
            setDateTo(e.target.value);
            setOffset(0);
          }}
          aria-label="Hasta"
        />
      </div>

      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(l) => l.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="No hay registros de auditoría con esos filtros"
        pagination={data ? { total: data.total, limit: LIMIT, offset, onPageChange: setOffset } : undefined}
      />
    </div>
  );
}
