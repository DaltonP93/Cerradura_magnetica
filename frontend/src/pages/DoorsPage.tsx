import { useState, type FormEvent } from 'react';
import { controllersApi, doorsApi } from '../api';
import { apiErrorMessage } from '../api/client';
import { DataTable, type Column } from '../components/DataTable';
import {
  Checkbox,
  FormField,
  Select,
  TextInput,
  BTN_PRIMARY,
  BTN_SECONDARY,
  BTN_SMALL,
} from '../components/FormField';
import { PageHeader } from '../components/Layout';
import { Modal } from '../components/Modal';
import { Spinner } from '../components/Spinner';
import { Badge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { DOOR_MODE_LABELS } from '../lib/format';
import { useFetch } from '../lib/useFetch';
import type { Door, DoorMode } from '../types';

const LIMIT = 50;

interface DoorForm {
  name: string;
  mode: DoorMode;
  open_duration_seconds: string;
  held_open_alarm_seconds: string;
  sensor_enabled: boolean;
  anti_passback: boolean;
  first_card_open: boolean;
  multi_card_count: string;
}

export function DoorsPage() {
  const { hasRole } = useAuth();
  const toast = useToast();
  const isAdmin = hasRole('admin');
  const isOperator = hasRole('operator');

  const [controllerFilter, setControllerFilter] = useState<string>('');
  const [offset, setOffset] = useState(0);
  const { data, loading, error, reload } = useFetch(
    () =>
      doorsApi.list({
        controller_id: controllerFilter ? Number(controllerFilter) : undefined,
        limit: LIMIT,
        offset,
      }),
    [controllerFilter, offset],
  );
  const { data: controllersPage } = useFetch(() => controllersApi.list({ limit: 200 }), []);

  const [editing, setEditing] = useState<Door | null>(null);
  const [form, setForm] = useState<DoorForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [openingId, setOpeningId] = useState<number | null>(null);

  const controllerName = (id: number) =>
    controllersPage?.items.find((c) => c.id === id)?.name ?? `Controlador #${id}`;

  const openEdit = (door: Door) => {
    setEditing(door);
    setForm({
      name: door.name,
      mode: door.mode,
      open_duration_seconds: String(door.open_duration_seconds),
      held_open_alarm_seconds: String(door.held_open_alarm_seconds),
      sensor_enabled: door.sensor_enabled,
      anti_passback: door.anti_passback,
      first_card_open: door.first_card_open,
      multi_card_count: String(door.multi_card_count),
    });
    setFormError(null);
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    if (!editing || !form) return;
    setSaving(true);
    setFormError(null);
    try {
      await doorsApi.update(editing.id, {
        name: form.name,
        mode: form.mode,
        open_duration_seconds: Number(form.open_duration_seconds),
        held_open_alarm_seconds: Number(form.held_open_alarm_seconds),
        sensor_enabled: form.sensor_enabled,
        anti_passback: form.anti_passback,
        first_card_open: form.first_card_open,
        multi_card_count: Number(form.multi_card_count),
      });
      toast.success('Puerta actualizada');
      setEditing(null);
      reload();
    } catch (err) {
      setFormError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleOpen = async (door: Door) => {
    setOpeningId(door.id);
    try {
      const result = await doorsApi.open(door.id);
      if (result.success) toast.success(`${door.name}: ${result.message}`);
      else toast.error(`${door.name}: ${result.message}`);
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setOpeningId(null);
    }
  };

  const columns: Column<Door>[] = [
    { header: 'Puerta', render: (d) => <span className="font-medium text-slate-100">{d.name}</span> },
    { header: 'Controlador', render: (d) => controllerName(d.controller_id) },
    { header: 'Nº', render: (d) => d.number },
    {
      header: 'Modo',
      render: (d) => (
        <Badge tone={d.mode === 'controlled' ? 'sky' : d.mode === 'normally_open' ? 'amber' : 'slate'}>
          {DOOR_MODE_LABELS[d.mode]}
        </Badge>
      ),
    },
    { header: 'Apertura (s)', render: (d) => d.open_duration_seconds },
    { header: 'Alarma retención (s)', render: (d) => d.held_open_alarm_seconds },
    {
      header: 'Opciones',
      render: (d) => (
        <div className="flex flex-wrap gap-1.5">
          {d.sensor_enabled && <Badge tone="slate">Sensor</Badge>}
          {d.anti_passback && <Badge tone="slate">Anti-passback</Badge>}
          {d.first_card_open && <Badge tone="slate">1ª tarjeta</Badge>}
          {d.multi_card_count > 1 && <Badge tone="slate">{d.multi_card_count} tarjetas</Badge>}
        </div>
      ),
    },
    {
      header: 'Acciones',
      className: 'whitespace-nowrap',
      render: (d) => (
        <div className="flex flex-wrap gap-1.5">
          {isOperator && (
            <button
              className="inline-flex items-center gap-1 rounded-md bg-emerald-600/90 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-500 disabled:opacity-50"
              disabled={openingId !== null}
              onClick={() => void handleOpen(d)}
            >
              {openingId === d.id ? <Spinner className="h-3 w-3" /> : '🔓'} Abrir puerta
            </button>
          )}
          {isAdmin && (
            <button className={BTN_SMALL} onClick={() => openEdit(d)}>
              ✏️ Editar
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Puertas" subtitle="Configuración y apertura remota de puertas" />

      <div className="mb-4">
        <Select
          value={controllerFilter}
          onChange={(e) => {
            setControllerFilter(e.target.value);
            setOffset(0);
          }}
          className="max-w-sm"
          aria-label="Filtrar por controlador"
        >
          <option value="">Todos los controladores</option>
          {(controllersPage?.items ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
      </div>

      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(d) => d.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="No hay puertas"
        emptyHint="Las puertas se crean automáticamente al registrar un controlador."
        pagination={data ? { total: data.total, limit: LIMIT, offset, onPageChange: setOffset } : undefined}
      />

      <Modal
        open={editing !== null}
        title={editing ? `Editar ${editing.name}` : ''}
        onClose={() => setEditing(null)}
        footer={
          <>
            <button className={BTN_SECONDARY} onClick={() => setEditing(null)} disabled={saving}>
              Cancelar
            </button>
            <button className={BTN_PRIMARY} form="door-form" type="submit" disabled={saving}>
              {saving && <Spinner className="h-4 w-4" />}
              Guardar
            </button>
          </>
        }
      >
        {form && (
          <form id="door-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
            <FormField label="Nombre" required>
              <TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </FormField>
            <FormField label="Modo de funcionamiento">
              <Select
                value={form.mode}
                onChange={(e) => setForm({ ...form, mode: e.target.value as DoorMode })}
              >
                <option value="controlled">Controlada (credencial válida)</option>
                <option value="normally_open">Siempre abierta</option>
                <option value="normally_closed">Siempre cerrada (solo apertura remota)</option>
              </Select>
            </FormField>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Duración de apertura (s)" hint="1–60 segundos">
                <TextInput
                  type="number"
                  min={1}
                  max={60}
                  value={form.open_duration_seconds}
                  onChange={(e) => setForm({ ...form, open_duration_seconds: e.target.value })}
                />
              </FormField>
              <FormField label="Alarma puerta retenida (s)" hint="5–600 segundos">
                <TextInput
                  type="number"
                  min={5}
                  max={600}
                  value={form.held_open_alarm_seconds}
                  onChange={(e) => setForm({ ...form, held_open_alarm_seconds: e.target.value })}
                />
              </FormField>
            </div>
            <div className="flex flex-col gap-2">
              <Checkbox
                label="Sensor de puerta habilitado"
                checked={form.sensor_enabled}
                onChange={(v) => setForm({ ...form, sensor_enabled: v })}
              />
              <Checkbox
                label="Anti-passback"
                checked={form.anti_passback}
                onChange={(v) => setForm({ ...form, anti_passback: v })}
              />
              <Checkbox
                label="Apertura con primera tarjeta"
                checked={form.first_card_open}
                onChange={(v) => setForm({ ...form, first_card_open: v })}
              />
            </div>
            <FormField
              label="Tarjetas simultáneas requeridas"
              hint="1 = deshabilitado; con 2–4 se necesitan varias tarjetas válidas para abrir."
            >
              <Select
                value={form.multi_card_count}
                onChange={(e) => setForm({ ...form, multi_card_count: e.target.value })}
              >
                {[1, 2, 3, 4].map((n) => (
                  <option key={n} value={n}>
                    {n === 1 ? '1 (deshabilitado)' : n}
                  </option>
                ))}
              </Select>
            </FormField>
            {formError && (
              <div className="rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-300">
                {formError}
              </div>
            )}
          </form>
        )}
      </Modal>
    </div>
  );
}
