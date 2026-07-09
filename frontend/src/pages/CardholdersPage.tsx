import { useState, type FormEvent } from 'react';
import { accessLevelsApi, cardholdersApi, departmentsApi } from '../api';
import { apiErrorMessage } from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { DataTable, type Column } from '../components/DataTable';
import {
  Checkbox,
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
import { ActiveBadge, Badge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { CREDENTIAL_TYPE_LABELS, formatDate } from '../lib/format';
import { useDebounced, useFetch } from '../lib/useFetch';
import type { Cardholder, CredentialType } from '../types';

const LIMIT = 25;

interface HolderForm {
  first_name: string;
  last_name: string;
  employee_number: string;
  email: string;
  phone: string;
  department_id: string;
  valid_from: string;
  valid_to: string;
  is_active: boolean;
  notes: string;
  access_level_ids: number[];
}

const EMPTY_FORM: HolderForm = {
  first_name: '',
  last_name: '',
  employee_number: '',
  email: '',
  phone: '',
  department_id: '',
  valid_from: '',
  valid_to: '',
  is_active: true,
  notes: '',
  access_level_ids: [],
};

function toDateInput(iso: string | null): string {
  return iso ? iso.slice(0, 10) : '';
}

function fromDateInput(value: string, endOfDay = false): string | null {
  if (!value) return null;
  return endOfDay ? `${value}T23:59:59` : `${value}T00:00:00`;
}

// ---- Credentials manager (inside edit modal) ----
function CredentialsSection({
  holder,
  onChanged,
}: {
  holder: Cardholder;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [cardNumber, setCardNumber] = useState('');
  const [type, setType] = useState<CredentialType>('card');
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [rowBusy, setRowBusy] = useState<number | null>(null);

  const needsPin = type === 'pin' || type === 'card_plus_pin';

  const handleAdd = async () => {
    if (!cardNumber) return;
    setBusy(true);
    try {
      await cardholdersApi.addCredential(holder.id, {
        type,
        card_number: cardNumber,
        pin: needsPin && pin ? pin : undefined,
      });
      toast.success('Credencial agregada');
      setCardNumber('');
      setPin('');
      onChanged();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const handleToggle = async (credentialId: number, isActive: boolean) => {
    setRowBusy(credentialId);
    try {
      await cardholdersApi.updateCredential(holder.id, credentialId, { is_active: !isActive });
      onChanged();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setRowBusy(null);
    }
  };

  const handleRemove = async (credentialId: number) => {
    setRowBusy(credentialId);
    try {
      await cardholdersApi.removeCredential(holder.id, credentialId);
      toast.success('Credencial eliminada');
      onChanged();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setRowBusy(null);
    }
  };

  return (
    <div className="rounded-lg border border-slate-700/60 bg-slate-800/30 p-4">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Credenciales ({holder.credentials.length})
      </h3>

      {holder.credentials.length === 0 ? (
        <p className="mb-3 text-xs text-slate-500">Sin credenciales asignadas todavía.</p>
      ) : (
        <ul className="mb-4 space-y-2">
          {holder.credentials.map((cred) => (
            <li
              key={cred.id}
              className="flex flex-wrap items-center gap-2 rounded-md border border-slate-700/60 bg-slate-900/60 px-3 py-2 text-sm"
            >
              <span className="font-mono text-xs text-slate-200">{cred.card_number}</span>
              <Badge tone="slate">{CREDENTIAL_TYPE_LABELS[cred.type]}</Badge>
              <ActiveBadge active={cred.is_active} />
              <span className="ml-auto flex gap-1.5">
                <button
                  className={BTN_SMALL}
                  disabled={rowBusy !== null}
                  onClick={() => void handleToggle(cred.id, cred.is_active)}
                >
                  {rowBusy === cred.id ? <Spinner className="h-3 w-3" /> : cred.is_active ? 'Desactivar' : 'Activar'}
                </button>
                <button
                  className={BTN_SMALL_DANGER}
                  disabled={rowBusy !== null}
                  onClick={() => void handleRemove(cred.id)}
                >
                  Eliminar
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto_auto]">
        <TextInput
          value={cardNumber}
          onChange={(e) => setCardNumber(e.target.value)}
          placeholder="Número de tarjeta"
        />
        <Select value={type} onChange={(e) => setType(e.target.value as CredentialType)}>
          <option value="card">Tarjeta</option>
          <option value="pin">PIN</option>
          <option value="card_plus_pin">Tarjeta + PIN</option>
        </Select>
        <TextInput
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          placeholder="PIN"
          disabled={!needsPin}
          inputMode="numeric"
          className="w-24"
        />
        <button
          type="button"
          className={BTN_SECONDARY}
          disabled={busy || !cardNumber || (needsPin && pin.length < 4)}
          onClick={() => void handleAdd()}
        >
          {busy ? <Spinner className="h-4 w-4" /> : '+ Agregar'}
        </button>
      </div>
    </div>
  );
}

export function CardholdersPage() {
  const { hasRole } = useAuth();
  const toast = useToast();
  const canManage = hasRole('operator');

  const [search, setSearch] = useState('');
  const q = useDebounced(search);
  const [departmentFilter, setDepartmentFilter] = useState('');
  const [activeFilter, setActiveFilter] = useState('');
  const [offset, setOffset] = useState(0);

  const { data, loading, error, reload } = useFetch(
    () =>
      cardholdersApi.list({
        q: q || undefined,
        department_id: departmentFilter ? Number(departmentFilter) : undefined,
        is_active: activeFilter === '' ? undefined : activeFilter === 'true',
        limit: LIMIT,
        offset,
      }),
    [q, departmentFilter, activeFilter, offset],
  );
  const { data: deptsPage } = useFetch(() => departmentsApi.list({ limit: 500 }), []);
  const { data: levelsPage } = useFetch(() => accessLevelsApi.list({ limit: 500 }), []);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Cardholder | null>(null);
  const [form, setForm] = useState<HolderForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<Cardholder | null>(null);

  const deptName = (id: number | null) =>
    id == null ? '—' : deptsPage?.items.find((d) => d.id === id)?.name ?? `#${id}`;

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setModalOpen(true);
  };

  const openEdit = (h: Cardholder) => {
    setEditing(h);
    setForm({
      first_name: h.first_name,
      last_name: h.last_name,
      employee_number: h.employee_number ?? '',
      email: h.email ?? '',
      phone: h.phone ?? '',
      department_id: h.department_id != null ? String(h.department_id) : '',
      valid_from: toDateInput(h.valid_from),
      valid_to: toDateInput(h.valid_to),
      is_active: h.is_active,
      notes: h.notes ?? '',
      access_level_ids: h.access_level_ids,
    });
    setFormError(null);
    setModalOpen(true);
  };

  const refreshEditing = async () => {
    if (!editing) return;
    try {
      const fresh = await cardholdersApi.get(editing.id);
      setEditing(fresh);
    } catch {
      // ignore; list reload will catch up
    }
    reload();
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    const body = {
      first_name: form.first_name,
      last_name: form.last_name,
      employee_number: form.employee_number || null,
      email: form.email || null,
      phone: form.phone || null,
      department_id: form.department_id ? Number(form.department_id) : null,
      valid_from: fromDateInput(form.valid_from),
      valid_to: fromDateInput(form.valid_to, true),
      is_active: form.is_active,
      notes: form.notes || null,
      access_level_ids: form.access_level_ids,
    };
    try {
      if (editing) {
        await cardholdersApi.update(editing.id, body);
        toast.success('Persona actualizada');
        setModalOpen(false);
      } else {
        const created = await cardholdersApi.create(body);
        toast.success('Persona creada. Ahora puedes asignarle credenciales.');
        setEditing(created);
        openEdit(created);
      }
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
      await cardholdersApi.remove(toDelete.id);
      toast.success('Persona eliminada');
      setToDelete(null);
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  };

  const toggleLevel = (id: number) => {
    setForm((f) => ({
      ...f,
      access_level_ids: f.access_level_ids.includes(id)
        ? f.access_level_ids.filter((x) => x !== id)
        : [...f.access_level_ids, id],
    }));
  };

  const columns: Column<Cardholder>[] = [
    {
      header: 'Nombre',
      render: (h) => (
        <span className="font-medium text-slate-100">
          {h.last_name}, {h.first_name}
        </span>
      ),
    },
    { header: 'Nº empleado', render: (h) => h.employee_number ?? '—' },
    { header: 'Departamento', render: (h) => deptName(h.department_id) },
    {
      header: 'Credenciales',
      render: (h) =>
        h.credentials.length === 0 ? (
          <span className="text-slate-500">Ninguna</span>
        ) : (
          <span>{h.credentials.length}</span>
        ),
    },
    {
      header: 'Vigencia',
      render: (h) =>
        h.valid_from || h.valid_to ? `${formatDate(h.valid_from)} → ${formatDate(h.valid_to)}` : 'Sin límite',
    },
    { header: 'Estado', render: (h) => <ActiveBadge active={h.is_active} /> },
    {
      header: 'Acciones',
      className: 'whitespace-nowrap',
      render: (h) =>
        canManage ? (
          <div className="flex gap-1.5">
            <button className={BTN_SMALL} onClick={() => openEdit(h)}>
              ✏️ Editar
            </button>
            <button className={BTN_SMALL_DANGER} onClick={() => setToDelete(h)}>
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
      <PageHeader
        title="Personal"
        subtitle="Personas con acceso a las instalaciones y sus credenciales"
        actions={
          canManage && (
            <button className={BTN_PRIMARY} onClick={openCreate}>
              + Nueva persona
            </button>
          )
        }
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <TextInput
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
          placeholder="Buscar por nombre o nº de empleado…"
          className="max-w-xs"
        />
        <Select
          value={departmentFilter}
          onChange={(e) => {
            setDepartmentFilter(e.target.value);
            setOffset(0);
          }}
          className="max-w-[200px]"
          aria-label="Filtrar por departamento"
        >
          <option value="">Todos los departamentos</option>
          {(deptsPage?.items ?? []).map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </Select>
        <Select
          value={activeFilter}
          onChange={(e) => {
            setActiveFilter(e.target.value);
            setOffset(0);
          }}
          className="max-w-[160px]"
          aria-label="Filtrar por estado"
        >
          <option value="">Todos</option>
          <option value="true">Solo activos</option>
          <option value="false">Solo inactivos</option>
        </Select>
      </div>

      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(h) => h.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="No hay personal registrado"
        emptyHint={canManage ? 'Agrega la primera persona con el botón "Nueva persona".' : undefined}
        pagination={data ? { total: data.total, limit: LIMIT, offset, onPageChange: setOffset } : undefined}
      />

      <Modal
        open={modalOpen}
        title={editing ? `Editar ${editing.first_name} ${editing.last_name}` : 'Nueva persona'}
        onClose={() => setModalOpen(false)}
        wide
        footer={
          <>
            <button className={BTN_SECONDARY} onClick={() => setModalOpen(false)} disabled={saving}>
              {editing ? 'Cerrar' : 'Cancelar'}
            </button>
            <button className={BTN_PRIMARY} form="holder-form" type="submit" disabled={saving}>
              {saving && <Spinner className="h-4 w-4" />}
              Guardar
            </button>
          </>
        }
      >
        <form id="holder-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Nombre" required>
              <TextInput
                value={form.first_name}
                onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                required
              />
            </FormField>
            <FormField label="Apellidos" required>
              <TextInput
                value={form.last_name}
                onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                required
              />
            </FormField>
            <FormField label="Nº de empleado">
              <TextInput
                value={form.employee_number}
                onChange={(e) => setForm({ ...form, employee_number: e.target.value })}
              />
            </FormField>
            <FormField label="Departamento">
              <Select
                value={form.department_id}
                onChange={(e) => setForm({ ...form, department_id: e.target.value })}
              >
                <option value="">Sin departamento</option>
                {(deptsPage?.items ?? []).map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="Correo electrónico">
              <TextInput
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </FormField>
            <FormField label="Teléfono">
              <TextInput value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </FormField>
            <FormField label="Válido desde">
              <TextInput
                type="date"
                value={form.valid_from}
                onChange={(e) => setForm({ ...form, valid_from: e.target.value })}
              />
            </FormField>
            <FormField label="Válido hasta">
              <TextInput
                type="date"
                value={form.valid_to}
                onChange={(e) => setForm({ ...form, valid_to: e.target.value })}
              />
            </FormField>
          </div>

          <FormField label="Niveles de acceso">
            {(levelsPage?.items ?? []).length === 0 ? (
              <p className="text-xs text-slate-500">
                No hay niveles de acceso definidos. Créalos en la página "Niveles de acceso".
              </p>
            ) : (
              <div className="flex flex-wrap gap-2 rounded-md border border-slate-700 bg-slate-800/40 p-3">
                {(levelsPage?.items ?? []).map((level) => (
                  <button
                    type="button"
                    key={level.id}
                    onClick={() => toggleLevel(level.id)}
                    className={`rounded-full px-3 py-1 text-xs transition ${
                      form.access_level_ids.includes(level.id)
                        ? 'bg-sky-600 text-white'
                        : 'border border-slate-600 text-slate-400 hover:border-sky-500 hover:text-sky-300'
                    }`}
                  >
                    {level.name}
                  </button>
                ))}
              </div>
            )}
          </FormField>

          <FormField label="Notas">
            <TextArea
              rows={2}
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </FormField>

          <Checkbox
            label="Persona activa"
            checked={form.is_active}
            onChange={(v) => setForm({ ...form, is_active: v })}
          />

          {formError && (
            <div className="rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-300">
              {formError}
            </div>
          )}
        </form>

        {editing && (
          <div className="mt-5">
            <CredentialsSection holder={editing} onChanged={() => void refreshEditing()} />
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={toDelete !== null}
        title="Eliminar persona"
        message={`¿Eliminar a "${toDelete ? `${toDelete.first_name} ${toDelete.last_name}` : ''}"? Se eliminarán también sus credenciales.`}
        onConfirm={handleDelete}
        onClose={() => setToDelete(null)}
      />
    </div>
  );
}
