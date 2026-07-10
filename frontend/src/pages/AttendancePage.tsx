import { useState, type FormEvent } from 'react';
import { attendanceApi, cardholdersApi, departmentsApi } from '../api';
import { apiErrorMessage } from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { DataTable, type Column } from '../components/DataTable';
import {
  FormField,
  Select,
  TextArea,
  TextInput,
  BTN_PRIMARY,
  BTN_SECONDARY,
  BTN_SMALL,
  BTN_SMALL_DANGER,
} from '../components/FormField';
import { PageHeader } from '../components/Layout';
import { Modal } from '../components/Modal';
import { Spinner } from '../components/Spinner';
import { Badge, type Tone } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { exportCsv, formatDate, formatDateTime, toHHMM, toHHMMSS } from '../lib/format';
import { useDebounced, useFetch } from '../lib/useFetch';
import type {
  AttendanceRow,
  Cardholder,
  Leave,
  LeaveType,
  ManualSign,
  Shift,
  SignKind,
} from '../types';

// ---- Shared helpers ----

const STATUS_LABELS: Record<string, string> = {
  present: 'Presente',
  late: 'Tarde',
  early_leave: 'Salida temprana',
  absent: 'Ausente',
  leave: 'Licencia',
  business_trip: 'Viaje de trabajo',
  holiday: 'Feriado',
  rest_day: 'Descanso',
  incomplete: 'Incompleto',
};

const STATUS_TONES: Record<string, Tone> = {
  present: 'green',
  late: 'amber',
  early_leave: 'amber',
  absent: 'red',
  leave: 'sky',
  business_trip: 'sky',
  holiday: 'slate',
  rest_day: 'slate',
  incomplete: 'orange',
};

const LEAVE_TYPE_LABELS: Record<LeaveType, string> = {
  leave: 'Licencia',
  business_trip: 'Viaje de trabajo',
};

const SIGN_KIND_LABELS: Record<SignKind, string> = {
  in: 'Entrada',
  out: 'Salida',
};

const DAY_SHORT = ['L', 'M', 'X', 'J', 'V', 'S', 'D']; // 0=lunes .. 6=domingo

function isoDate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
}

function holderLabel(holders: Cardholder[] | undefined, id: number): string {
  const h = holders?.find((x) => x.id === id);
  return h ? `${h.last_name}, ${h.first_name}` : `#${id}`;
}

function StatusChips({ statuses }: { statuses: string[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {statuses.map((s) => (
        <Badge key={s} tone={STATUS_TONES[s] ?? 'slate'}>
          {STATUS_LABELS[s] ?? s}
        </Badge>
      ))}
    </div>
  );
}

// ---- Reporte tab ----

function ReportTab() {
  const today = new Date();
  const weekAgo = new Date(today.getTime() - 6 * 24 * 60 * 60 * 1000);

  const [dateFrom, setDateFrom] = useState(isoDate(weekAgo));
  const [dateTo, setDateTo] = useState(isoDate(today));
  const [departmentId, setDepartmentId] = useState('');
  const [holderSearch, setHolderSearch] = useState('');
  const holderQ = useDebounced(holderSearch);
  const [holderId, setHolderId] = useState('');

  const { data: deptsPage } = useFetch(() => departmentsApi.list({ limit: 500 }), []);
  const { data: holdersPage } = useFetch(
    () => cardholdersApi.list({ q: holderQ || undefined, limit: 100 }),
    [holderQ],
  );

  const { data: report, loading, error, reload } = useFetch(
    () =>
      dateFrom && dateTo
        ? attendanceApi.report({
            date_from: dateFrom,
            date_to: dateTo,
            department_id: departmentId ? Number(departmentId) : undefined,
            cardholder_id: holderId ? Number(holderId) : undefined,
          })
        : Promise.resolve(null),
    [dateFrom, dateTo, departmentId, holderId],
  );

  const handleExport = () => {
    if (!report || report.rows.length === 0) return;
    exportCsv(
      `asistencia_${report.date_from}_${report.date_to}.csv`,
      ['Persona', 'Departamento', 'Fecha', 'Entrada', 'Salida', 'Estados'],
      report.rows.map((r) => [
        r.cardholder_name,
        r.department ?? '',
        r.date,
        r.check_in ? formatDateTime(r.check_in) : '',
        r.check_out ? formatDateTime(r.check_out) : '',
        r.statuses.map((s) => STATUS_LABELS[s] ?? s).join(' + '),
      ]),
    );
  };

  const summaryItems: { label: string; value: number }[] = report
    ? [
        { label: 'Días', value: report.summary.days },
        { label: 'Presentes', value: report.summary.present },
        { label: 'Tardanzas', value: report.summary.late },
        { label: 'Salidas tempranas', value: report.summary.early_leave },
        { label: 'Ausencias', value: report.summary.absent },
        { label: 'Licencias', value: report.summary.on_leave },
        { label: 'Incompletos', value: report.summary.incomplete },
      ]
    : [];

  const columns: Column<AttendanceRow>[] = [
    {
      header: 'Persona',
      render: (r) => <span className="font-medium text-slate-100">{r.cardholder_name}</span>,
    },
    { header: 'Departamento', render: (r) => r.department ?? '—' },
    { header: 'Fecha', render: (r) => formatDate(r.date), className: 'whitespace-nowrap' },
    { header: 'Entrada', render: (r) => formatTime(r.check_in) },
    { header: 'Salida', render: (r) => formatTime(r.check_out) },
    { header: 'Estados', render: (r) => <StatusChips statuses={r.statuses} /> },
  ];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <FormField label="Desde">
          <TextInput
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="w-40"
          />
        </FormField>
        <FormField label="Hasta">
          <TextInput
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="w-40"
          />
        </FormField>
        <FormField label="Departamento">
          <Select
            value={departmentId}
            onChange={(e) => setDepartmentId(e.target.value)}
            className="w-48"
          >
            <option value="">Todos</option>
            {(deptsPage?.items ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Buscar persona">
          <TextInput
            value={holderSearch}
            onChange={(e) => setHolderSearch(e.target.value)}
            placeholder="Nombre o nº de empleado…"
            className="w-52"
          />
        </FormField>
        <FormField label="Persona">
          <Select value={holderId} onChange={(e) => setHolderId(e.target.value)} className="w-52">
            <option value="">Todas</option>
            {(holdersPage?.items ?? []).map((h) => (
              <option key={h.id} value={h.id}>
                {h.last_name}, {h.first_name}
              </option>
            ))}
          </Select>
        </FormField>
        <button
          className={`${BTN_SECONDARY} ml-auto`}
          onClick={handleExport}
          disabled={!report || report.rows.length === 0}
        >
          ⬇️ Exportar CSV
        </button>
      </div>

      {report && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {summaryItems.map((item) => (
            <div
              key={item.label}
              className="rounded-xl border border-slate-700/60 bg-slate-900/60 px-4 py-3"
            >
              <p className="text-lg font-semibold text-white">{item.value}</p>
              <p className="text-xs text-slate-500">{item.label}</p>
            </div>
          ))}
        </div>
      )}

      <DataTable
        columns={columns}
        rows={report?.rows}
        rowKey={(r) => `${r.cardholder_id}-${r.date}`}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="Sin datos de asistencia en el período"
        emptyHint="Ajusta las fechas o los filtros. Las personas deben tener un turno asignado para aparecer en el reporte."
      />
    </div>
  );
}

// ---- Turnos tab ----

interface ShiftForm {
  name: string;
  start: string; // HH:MM
  end: string;
  late_tolerance: string;
  early_leave_tolerance: string;
  days_of_week: number[];
}

function ShiftModal({
  shift,
  onClose,
  onSaved,
}: {
  shift: Shift | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<ShiftForm>({
    name: shift?.name ?? '',
    start: shift ? toHHMM(shift.start_time) : '08:00',
    end: shift ? toHHMM(shift.end_time) : '17:00',
    late_tolerance: String(shift?.late_tolerance_minutes ?? 10),
    early_leave_tolerance: String(shift?.early_leave_tolerance_minutes ?? 10),
    days_of_week: shift?.days_of_week ?? [0, 1, 2, 3, 4],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleDay = (d: number) => {
    setForm((f) => ({
      ...f,
      days_of_week: f.days_of_week.includes(d)
        ? f.days_of_week.filter((x) => x !== d)
        : [...f.days_of_week, d].sort((a, b) => a - b),
    }));
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.start || !form.end || form.start >= form.end) {
      setError('La hora de inicio debe ser anterior a la de fin.');
      return;
    }
    if (form.days_of_week.length === 0) {
      setError('Selecciona al menos un día de la semana.');
      return;
    }
    setSaving(true);
    setError(null);
    const body = {
      name: form.name,
      start_time: toHHMMSS(form.start),
      end_time: toHHMMSS(form.end),
      late_tolerance_minutes: Number(form.late_tolerance),
      early_leave_tolerance_minutes: Number(form.early_leave_tolerance),
      days_of_week: form.days_of_week,
    };
    try {
      if (shift) {
        await attendanceApi.updateShift(shift.id, body);
        toast.success('Turno actualizado');
      } else {
        await attendanceApi.createShift(body);
        toast.success('Turno creado');
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      title={shift ? `Editar ${shift.name}` : 'Nuevo turno'}
      onClose={onClose}
      footer={
        <>
          <button className={BTN_SECONDARY} onClick={onClose} disabled={saving}>
            Cancelar
          </button>
          <button className={BTN_PRIMARY} form="shift-form" type="submit" disabled={saving}>
            {saving && <Spinner className="h-4 w-4" />}
            Guardar
          </button>
        </>
      }
    >
      <form id="shift-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
        <FormField label="Nombre" required>
          <TextInput
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
            placeholder="p. ej. Turno mañana"
          />
        </FormField>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Hora de entrada" required>
            <TextInput
              type="time"
              value={form.start}
              onChange={(e) => setForm({ ...form, start: e.target.value })}
              required
            />
          </FormField>
          <FormField label="Hora de salida" required>
            <TextInput
              type="time"
              value={form.end}
              onChange={(e) => setForm({ ...form, end: e.target.value })}
              required
            />
          </FormField>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Tolerancia de tardanza (min)" hint="0–240 minutos">
            <TextInput
              type="number"
              min={0}
              max={240}
              value={form.late_tolerance}
              onChange={(e) => setForm({ ...form, late_tolerance: e.target.value })}
            />
          </FormField>
          <FormField label="Tolerancia salida temprana (min)" hint="0–240 minutos">
            <TextInput
              type="number"
              min={0}
              max={240}
              value={form.early_leave_tolerance}
              onChange={(e) => setForm({ ...form, early_leave_tolerance: e.target.value })}
            />
          </FormField>
        </div>
        <FormField label="Días de la semana" hint="L = lunes … D = domingo">
          <div className="flex gap-1.5">
            {DAY_SHORT.map((label, d) => (
              <button
                type="button"
                key={d}
                onClick={() => toggleDay(d)}
                aria-pressed={form.days_of_week.includes(d)}
                className={`h-9 w-9 rounded-md text-sm font-medium transition ${
                  form.days_of_week.includes(d)
                    ? 'bg-sky-600 text-white'
                    : 'border border-slate-600 text-slate-400 hover:border-sky-500 hover:text-sky-300'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </FormField>
        {error && (
          <div className="rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}

function ShiftsTab() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole('admin');
  const toast = useToast();

  const { data, loading, error, reload } = useFetch(() => attendanceApi.listShifts({ limit: 500 }), []);
  const [modal, setModal] = useState<{ open: boolean; shift: Shift | null }>({ open: false, shift: null });
  const [toDelete, setToDelete] = useState<Shift | null>(null);

  const handleDelete = async () => {
    if (!toDelete) return;
    try {
      await attendanceApi.removeShift(toDelete.id);
      toast.success('Turno eliminado');
      setToDelete(null);
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
      setToDelete(null);
    }
  };

  const columns: Column<Shift>[] = [
    { header: 'Nombre', render: (s) => <span className="font-medium text-slate-100">{s.name}</span> },
    {
      header: 'Horario',
      render: (s) => `${toHHMM(s.start_time)} – ${toHHMM(s.end_time)}`,
      className: 'whitespace-nowrap',
    },
    { header: 'Tolerancia tardanza', render: (s) => `${s.late_tolerance_minutes} min` },
    { header: 'Tolerancia salida', render: (s) => `${s.early_leave_tolerance_minutes} min` },
    {
      header: 'Días',
      render: (s) => (
        <div className="flex gap-1">
          {DAY_SHORT.map((label, d) => (
            <span
              key={d}
              className={`flex h-6 w-6 items-center justify-center rounded text-[11px] font-medium ${
                s.days_of_week.includes(d)
                  ? 'bg-sky-500/20 text-sky-300'
                  : 'bg-slate-800/70 text-slate-600'
              }`}
            >
              {label}
            </span>
          ))}
        </div>
      ),
    },
    {
      header: 'Acciones',
      className: 'whitespace-nowrap',
      render: (s) =>
        isAdmin ? (
          <div className="flex gap-1.5">
            <button className={BTN_SMALL} onClick={() => setModal({ open: true, shift: s })}>
              ✏️ Editar
            </button>
            <button className={BTN_SMALL_DANGER} onClick={() => setToDelete(s)}>
              🗑️ Eliminar
            </button>
          </div>
        ) : (
          <span className="text-xs text-slate-600">Solo lectura</span>
        ),
    },
  ];

  return (
    <div>
      {isAdmin && (
        <div className="mb-4 flex justify-end">
          <button className={BTN_PRIMARY} onClick={() => setModal({ open: true, shift: null })}>
            + Nuevo turno
          </button>
        </div>
      )}

      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(s) => s.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="No hay turnos definidos"
        emptyHint={
          isAdmin
            ? 'Crea un turno y asígnalo al personal desde la página "Personal" para generar el reporte de asistencia.'
            : undefined
        }
      />

      {modal.open && (
        <ShiftModal
          shift={modal.shift}
          onClose={() => setModal({ open: false, shift: null })}
          onSaved={reload}
        />
      )}

      <ConfirmDialog
        open={toDelete !== null}
        title="Eliminar turno"
        message={`¿Eliminar el turno "${toDelete?.name ?? ''}"? Las personas asignadas quedarán sin turno.`}
        onConfirm={handleDelete}
        onClose={() => setToDelete(null)}
      />
    </div>
  );
}

// ---- Licencias tab ----

const LEAVES_LIMIT = 25;

interface LeaveForm {
  cardholder_id: string;
  type: LeaveType;
  date_from: string;
  date_to: string;
  reason: string;
}

function LeavesTab() {
  const { hasRole } = useAuth();
  const canManage = hasRole('operator');
  const toast = useToast();

  const [offset, setOffset] = useState(0);
  const { data, loading, error, reload } = useFetch(
    () => attendanceApi.listLeaves({ limit: LEAVES_LIMIT, offset }),
    [offset],
  );
  const { data: holdersPage } = useFetch(() => cardholdersApi.list({ limit: 500 }), []);

  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState<LeaveForm>({
    cardholder_id: '',
    type: 'leave',
    date_from: '',
    date_to: '',
    reason: '',
  });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<Leave | null>(null);

  const openCreate = () => {
    setForm({ cardholder_id: '', type: 'leave', date_from: '', date_to: '', reason: '' });
    setFormError(null);
    setModalOpen(true);
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await attendanceApi.createLeave({
        cardholder_id: Number(form.cardholder_id),
        type: form.type,
        date_from: form.date_from,
        date_to: form.date_to,
        reason: form.reason || null,
      });
      toast.success('Licencia registrada');
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!toDelete) return;
    try {
      await attendanceApi.removeLeave(toDelete.id);
      toast.success('Licencia eliminada');
      setToDelete(null);
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
      setToDelete(null);
    }
  };

  const columns: Column<Leave>[] = [
    {
      header: 'Persona',
      render: (l) => (
        <span className="font-medium text-slate-100">{holderLabel(holdersPage?.items, l.cardholder_id)}</span>
      ),
    },
    {
      header: 'Tipo',
      render: (l) => <Badge tone="sky">{LEAVE_TYPE_LABELS[l.type]}</Badge>,
    },
    { header: 'Desde', render: (l) => formatDate(l.date_from), className: 'whitespace-nowrap' },
    { header: 'Hasta', render: (l) => formatDate(l.date_to), className: 'whitespace-nowrap' },
    { header: 'Motivo', render: (l) => l.reason ?? '—' },
    {
      header: 'Acciones',
      className: 'whitespace-nowrap',
      render: (l) =>
        canManage ? (
          <button className={BTN_SMALL_DANGER} onClick={() => setToDelete(l)}>
            🗑️ Eliminar
          </button>
        ) : (
          <span className="text-xs text-slate-600">Solo lectura</span>
        ),
    },
  ];

  return (
    <div>
      {canManage && (
        <div className="mb-4 flex justify-end">
          <button className={BTN_PRIMARY} onClick={openCreate}>
            + Nueva licencia
          </button>
        </div>
      )}

      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(l) => l.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="No hay licencias registradas"
        emptyHint={canManage ? 'Registra licencias o viajes de trabajo para excluirlos del cálculo de ausencias.' : undefined}
        pagination={data ? { total: data.total, limit: LEAVES_LIMIT, offset, onPageChange: setOffset } : undefined}
      />

      <Modal
        open={modalOpen}
        title="Nueva licencia"
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button className={BTN_SECONDARY} onClick={() => setModalOpen(false)} disabled={saving}>
              Cancelar
            </button>
            <button className={BTN_PRIMARY} form="leave-form" type="submit" disabled={saving}>
              {saving && <Spinner className="h-4 w-4" />}
              Guardar
            </button>
          </>
        }
      >
        <form id="leave-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
          <FormField label="Persona" required>
            <Select
              value={form.cardholder_id}
              onChange={(e) => setForm({ ...form, cardholder_id: e.target.value })}
              required
            >
              <option value="">Selecciona una persona…</option>
              {(holdersPage?.items ?? []).map((h) => (
                <option key={h.id} value={h.id}>
                  {h.last_name}, {h.first_name}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Tipo">
            <Select
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value as LeaveType })}
            >
              <option value="leave">Licencia</option>
              <option value="business_trip">Viaje de trabajo</option>
            </Select>
          </FormField>
          <div className="grid grid-cols-2 gap-4">
            <FormField label="Desde" required>
              <TextInput
                type="date"
                value={form.date_from}
                onChange={(e) => setForm({ ...form, date_from: e.target.value })}
                required
              />
            </FormField>
            <FormField label="Hasta" required>
              <TextInput
                type="date"
                value={form.date_to}
                onChange={(e) => setForm({ ...form, date_to: e.target.value })}
                required
              />
            </FormField>
          </div>
          <FormField label="Motivo">
            <TextArea
              rows={2}
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
            />
          </FormField>
          {formError && (
            <div className="rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-300">
              {formError}
            </div>
          )}
        </form>
      </Modal>

      <ConfirmDialog
        open={toDelete !== null}
        title="Eliminar licencia"
        message={`¿Eliminar la licencia de "${toDelete ? holderLabel(holdersPage?.items, toDelete.cardholder_id) : ''}"?`}
        onConfirm={handleDelete}
        onClose={() => setToDelete(null)}
      />
    </div>
  );
}

// ---- Fichaje manual tab ----

const SIGNS_LIMIT = 25;

interface SignForm {
  cardholder_id: string;
  kind: SignKind;
  signed_at: string; // datetime-local: YYYY-MM-DDTHH:MM
  note: string;
}

function nowLocalInput(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function ManualSignsTab() {
  const { hasRole } = useAuth();
  const canManage = hasRole('operator');
  const toast = useToast();

  const [offset, setOffset] = useState(0);
  const { data, loading, error, reload } = useFetch(
    () => attendanceApi.listManualSigns({ limit: SIGNS_LIMIT, offset }),
    [offset],
  );
  const { data: holdersPage } = useFetch(() => cardholdersApi.list({ limit: 500 }), []);

  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState<SignForm>({
    cardholder_id: '',
    kind: 'in',
    signed_at: '',
    note: '',
  });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<ManualSign | null>(null);

  const openCreate = () => {
    setForm({ cardholder_id: '', kind: 'in', signed_at: nowLocalInput(), note: '' });
    setFormError(null);
    setModalOpen(true);
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await attendanceApi.createManualSign({
        cardholder_id: Number(form.cardholder_id),
        kind: form.kind,
        signed_at: form.signed_at.length === 16 ? `${form.signed_at}:00` : form.signed_at,
        note: form.note || null,
      });
      toast.success('Fichaje manual registrado');
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!toDelete) return;
    try {
      await attendanceApi.removeManualSign(toDelete.id);
      toast.success('Fichaje eliminado');
      setToDelete(null);
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
      setToDelete(null);
    }
  };

  const columns: Column<ManualSign>[] = [
    {
      header: 'Persona',
      render: (s) => (
        <span className="font-medium text-slate-100">{holderLabel(holdersPage?.items, s.cardholder_id)}</span>
      ),
    },
    {
      header: 'Tipo',
      render: (s) => <Badge tone={s.kind === 'in' ? 'green' : 'amber'}>{SIGN_KIND_LABELS[s.kind]}</Badge>,
    },
    { header: 'Fecha y hora', render: (s) => formatDateTime(s.signed_at), className: 'whitespace-nowrap' },
    { header: 'Nota', render: (s) => s.note ?? '—' },
    {
      header: 'Acciones',
      className: 'whitespace-nowrap',
      render: (s) =>
        canManage ? (
          <button className={BTN_SMALL_DANGER} onClick={() => setToDelete(s)}>
            🗑️ Eliminar
          </button>
        ) : (
          <span className="text-xs text-slate-600">Solo lectura</span>
        ),
    },
  ];

  return (
    <div>
      {canManage && (
        <div className="mb-4 flex justify-end">
          <button className={BTN_PRIMARY} onClick={openCreate}>
            + Nuevo fichaje
          </button>
        </div>
      )}

      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(s) => s.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="No hay fichajes manuales"
        emptyHint={
          canManage
            ? 'Registra un fichaje manual cuando una persona olvidó marcar su entrada o salida.'
            : undefined
        }
        pagination={data ? { total: data.total, limit: SIGNS_LIMIT, offset, onPageChange: setOffset } : undefined}
      />

      <Modal
        open={modalOpen}
        title="Nuevo fichaje manual"
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button className={BTN_SECONDARY} onClick={() => setModalOpen(false)} disabled={saving}>
              Cancelar
            </button>
            <button className={BTN_PRIMARY} form="sign-form" type="submit" disabled={saving}>
              {saving && <Spinner className="h-4 w-4" />}
              Guardar
            </button>
          </>
        }
      >
        <form id="sign-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
          <FormField label="Persona" required>
            <Select
              value={form.cardholder_id}
              onChange={(e) => setForm({ ...form, cardholder_id: e.target.value })}
              required
            >
              <option value="">Selecciona una persona…</option>
              {(holdersPage?.items ?? []).map((h) => (
                <option key={h.id} value={h.id}>
                  {h.last_name}, {h.first_name}
                </option>
              ))}
            </Select>
          </FormField>
          <div className="grid grid-cols-2 gap-4">
            <FormField label="Tipo">
              <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as SignKind })}>
                <option value="in">Entrada</option>
                <option value="out">Salida</option>
              </Select>
            </FormField>
            <FormField label="Fecha y hora" required>
              <TextInput
                type="datetime-local"
                value={form.signed_at}
                onChange={(e) => setForm({ ...form, signed_at: e.target.value })}
                required
              />
            </FormField>
          </div>
          <FormField label="Nota">
            <TextArea rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          </FormField>
          {formError && (
            <div className="rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-300">
              {formError}
            </div>
          )}
        </form>
      </Modal>

      <ConfirmDialog
        open={toDelete !== null}
        title="Eliminar fichaje"
        message={`¿Eliminar el fichaje de "${toDelete ? holderLabel(holdersPage?.items, toDelete.cardholder_id) : ''}"?`}
        onConfirm={handleDelete}
        onClose={() => setToDelete(null)}
      />
    </div>
  );
}

// ---- Page ----

const TABS = [
  { key: 'report', label: 'Reporte' },
  { key: 'shifts', label: 'Turnos' },
  { key: 'leaves', label: 'Licencias' },
  { key: 'signs', label: 'Fichaje manual' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

export function AttendancePage() {
  const [tab, setTab] = useState<TabKey>('report');

  return (
    <div>
      <PageHeader
        title="Asistencia"
        subtitle="Reporte de asistencia, turnos de trabajo, licencias y fichajes manuales"
      />

      <div className="mb-5 inline-flex flex-wrap gap-1 rounded-lg border border-slate-700/60 bg-slate-900/60 p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-md px-4 py-2 text-sm transition ${
              tab === t.key
                ? 'bg-sky-500/15 font-medium text-sky-300'
                : 'text-slate-400 hover:bg-slate-800/70 hover:text-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'report' && <ReportTab />}
      {tab === 'shifts' && <ShiftsTab />}
      {tab === 'leaves' && <LeavesTab />}
      {tab === 'signs' && <ManualSignsTab />}
    </div>
  );
}
