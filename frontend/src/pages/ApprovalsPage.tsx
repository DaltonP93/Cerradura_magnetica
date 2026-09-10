import { useState, type FormEvent } from 'react';
import { doorsApi } from '../api';
import { apiErrorMessage } from '../api/client';
import { DataTable, type Column } from '../components/DataTable';
import { BTN_PRIMARY, BTN_SMALL, BTN_SMALL_DANGER, FormField, Select, TextArea } from '../components/FormField';
import { PageHeader } from '../components/Layout';
import { Spinner } from '../components/Spinner';
import { Badge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { DOOR_OPEN_REQUEST_STATUS_LABELS, doorRequestTone, formatDateTime } from '../lib/format';
import { useFetch } from '../lib/useFetch';
import type { DoorOpenRequest, DoorOpenRequestStatus } from '../types';

const LIMIT = 100;

type StatusFilter = '' | DoorOpenRequestStatus;

export function ApprovalsPage() {
  const { user, hasRole } = useAuth();
  const toast = useToast();
  const isOperator = hasRole('operator');

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('pending');
  const [offset, setOffset] = useState(0);
  const {
    data: requests,
    loading,
    error,
    reload,
  } = useFetch(
    () =>
      doorsApi.listOpenRequests({
        status: statusFilter || undefined,
        limit: LIMIT,
        offset,
      }),
    [statusFilter, offset],
  );
  // Critical doors are the only ones that accept a dual-approval request.
  const { data: doorsPage } = useFetch(() => doorsApi.list({ limit: 200 }), []);
  const criticalDoors = (doorsPage?.items ?? []).filter((d) => d.requires_dual_approval);
  const doorName = (id: number) => doorsPage?.items.find((d) => d.id === id)?.name ?? `Puerta #${id}`;

  const [selectedDoor, setSelectedDoor] = useState<string>('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [actioningId, setActioningId] = useState<number | null>(null);

  const whoisId = (id: number | null) => {
    if (id == null) return '—';
    return user && id === user.id ? `Tú (#${id})` : `Operador #${id}`;
  };

  const handleRequest = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedDoor) return;
    setSubmitting(true);
    try {
      await doorsApi.requestOpen(Number(selectedDoor), reason.trim() || null);
      toast.success('Solicitud creada; requiere la aprobación de un segundo operador.');
      setReason('');
      setSelectedDoor('');
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleApprove = async (req: DoorOpenRequest) => {
    setActioningId(req.id);
    try {
      const updated = await doorsApi.approveOpenRequest(req.id);
      toast.success(
        updated.status === 'dispatched'
          ? 'Aprobada; apertura enviada al puente local.'
          : 'Aprobada; puerta abierta.',
      );
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setActioningId(null);
    }
  };

  const handleReject = async (req: DoorOpenRequest) => {
    setActioningId(req.id);
    try {
      await doorsApi.rejectOpenRequest(req.id);
      toast.success('Solicitud rechazada.');
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setActioningId(null);
    }
  };

  const columns: Column<DoorOpenRequest>[] = [
    { header: 'Puerta', render: (r) => <span className="font-medium text-slate-100">{doorName(r.door_id)}</span> },
    { header: 'Solicitante', render: (r) => whoisId(r.requested_by_id) },
    { header: 'Aprobador', render: (r) => whoisId(r.approved_by_id) },
    { header: 'Motivo', render: (r) => r.reason ?? '—' },
    { header: 'Creada', render: (r) => formatDateTime(r.created_at) },
    { header: 'Expira', render: (r) => formatDateTime(r.expires_at) },
    {
      header: 'Estado',
      render: (r) => <Badge tone={doorRequestTone(r.status)}>{DOOR_OPEN_REQUEST_STATUS_LABELS[r.status]}</Badge>,
    },
    {
      header: 'Acciones',
      className: 'whitespace-nowrap',
      render: (r) => {
        if (r.status !== 'pending' || !isOperator) return <span className="text-slate-600">—</span>;
        const ownRequest = user != null && r.requested_by_id === user.id;
        return (
          <div className="flex flex-wrap gap-1.5">
            <button
              className={BTN_SMALL}
              disabled={actioningId !== null || ownRequest}
              title={ownRequest ? 'No podés aprobar tu propia solicitud (regla de dos personas)' : undefined}
              onClick={() => void handleApprove(r)}
            >
              {actioningId === r.id ? <Spinner className="h-3 w-3" /> : '✅'} Aprobar
            </button>
            <button
              className={BTN_SMALL_DANGER}
              disabled={actioningId !== null}
              onClick={() => void handleReject(r)}
            >
              ✕ Rechazar
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <div>
      <PageHeader
        title="Aprobaciones"
        subtitle="Regla de dos personas: una apertura en puerta crítica requiere que un segundo operador la apruebe."
      />

      {isOperator && (
        <form
          onSubmit={(e) => void handleRequest(e)}
          className="mb-6 rounded-lg border border-slate-800 bg-slate-900/50 p-4"
        >
          <p className="mb-3 text-sm font-medium text-slate-200">Solicitar apertura de puerta crítica</p>
          {criticalDoors.length === 0 ? (
            <p className="text-sm text-slate-400">
              No hay puertas marcadas como “Requiere doble aprobación”. Activá esa opción en una puerta para
              usarla aquí.
            </p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto] sm:items-end">
              <FormField label="Puerta">
                <Select
                  value={selectedDoor}
                  onChange={(e) => setSelectedDoor(e.target.value)}
                  aria-label="Puerta crítica"
                >
                  <option value="">Elegí una puerta…</option>
                  {criticalDoors.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField label="Motivo (opcional)">
                <TextArea
                  rows={1}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={500}
                  placeholder="Ej.: visita de mantenimiento"
                />
              </FormField>
              <button className={BTN_PRIMARY} type="submit" disabled={submitting || !selectedDoor}>
                {submitting && <Spinner className="h-4 w-4" />}
                Solicitar apertura
              </button>
            </div>
          )}
        </form>
      )}

      <div className="mb-4">
        <Select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as StatusFilter);
            setOffset(0);
          }}
          className="max-w-xs"
          aria-label="Filtrar por estado"
        >
          <option value="pending">Pendientes</option>
          <option value="">Todas</option>
          <option value="dispatched">Enviadas al puente</option>
          <option value="executed">Ejecutadas</option>
          <option value="rejected">Rechazadas</option>
          <option value="expired">Expiradas</option>
          <option value="failed">Fallidas</option>
        </Select>
      </div>

      <DataTable
        columns={columns}
        rows={requests?.items}
        rowKey={(r) => r.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="Sin solicitudes"
        emptyHint="Las solicitudes de apertura con doble aprobación aparecerán aquí."
        pagination={
          requests ? { total: requests.total, limit: LIMIT, offset, onPageChange: setOffset } : undefined
        }
      />
    </div>
  );
}
