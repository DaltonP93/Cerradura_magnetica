import { useState, type FormEvent } from 'react';
import { authApi, usersApi } from '../api';
import { apiErrorMessage } from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { DataTable, type Column } from '../components/DataTable';
import {
  Checkbox,
  FormField,
  Select,
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
import { ROLE_LABELS, formatDateTime } from '../lib/format';
import { useDebounced, useFetch } from '../lib/useFetch';
import type { User, UserRole } from '../types';

const LIMIT = 25;

interface UserForm {
  email: string;
  full_name: string;
  password: string;
  role: UserRole;
  is_active: boolean;
}

const EMPTY_FORM: UserForm = {
  email: '',
  full_name: '',
  password: '',
  role: 'viewer',
  is_active: true,
};

function ChangePasswordCard() {
  const toast = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== confirm) {
      toast.error('La nueva contraseña y su confirmación no coinciden');
      return;
    }
    setBusy(true);
    try {
      await authApi.changePassword(current, next);
      toast.success('Contraseña actualizada correctamente');
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/60 p-5">
      <h2 className="mb-1 text-sm font-semibold text-slate-200">Cambiar mi contraseña</h2>
      <p className="mb-4 text-xs text-slate-500">Mínimo 8 caracteres.</p>
      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-3">
        <FormField label="Contraseña actual" required>
          <TextInput
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
            autoComplete="current-password"
          />
        </FormField>
        <FormField label="Nueva contraseña" required>
          <TextInput
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
        </FormField>
        <FormField label="Confirmar nueva contraseña" required>
          <TextInput
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
        </FormField>
        <button type="submit" disabled={busy} className={`${BTN_PRIMARY} w-full justify-center`}>
          {busy && <Spinner className="h-4 w-4" />}
          Actualizar contraseña
        </button>
      </form>
    </div>
  );
}

export function UsersPage() {
  const { user: me } = useAuth();
  const toast = useToast();
  const isSuperAdmin = me?.role === 'super_admin';

  const [search, setSearch] = useState('');
  const q = useDebounced(search);
  const [offset, setOffset] = useState(0);
  const { data, loading, error, reload } = useFetch(
    () => usersApi.list({ q: q || undefined, limit: LIMIT, offset }),
    [q, offset],
  );

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [form, setForm] = useState<UserForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<User | null>(null);

  const roleOptions: UserRole[] = isSuperAdmin
    ? ['viewer', 'operator', 'admin', 'super_admin']
    : ['viewer', 'operator', 'admin'];

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setModalOpen(true);
  };

  const openEdit = (u: User) => {
    setEditing(u);
    setForm({
      email: u.email,
      full_name: u.full_name,
      password: '',
      role: u.role,
      is_active: u.is_active,
    });
    setFormError(null);
    setModalOpen(true);
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      if (editing) {
        await usersApi.update(editing.id, {
          full_name: form.full_name,
          role: form.role,
          is_active: form.is_active,
          ...(form.password ? { password: form.password } : {}),
        });
        toast.success('Usuario actualizado');
      } else {
        await usersApi.create({
          email: form.email,
          full_name: form.full_name,
          password: form.password,
          role: form.role,
        });
        toast.success('Usuario creado');
      }
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
      await usersApi.remove(toDelete.id);
      toast.success('Usuario eliminado');
      setToDelete(null);
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
      setToDelete(null);
    }
  };

  const columns: Column<User>[] = [
    { header: 'Nombre', render: (u) => <span className="font-medium text-slate-100">{u.full_name}</span> },
    { header: 'Correo', render: (u) => u.email },
    { header: 'Rol', render: (u) => <Badge tone={u.role === 'admin' || u.role === 'super_admin' ? 'sky' : 'slate'}>{ROLE_LABELS[u.role]}</Badge> },
    { header: 'Estado', render: (u) => <ActiveBadge active={u.is_active} /> },
    { header: 'Último acceso', render: (u) => formatDateTime(u.last_login_at) },
    {
      header: 'Acciones',
      className: 'whitespace-nowrap',
      render: (u) => (
        <div className="flex gap-1.5">
          <button className={BTN_SMALL} onClick={() => openEdit(u)}>
            ✏️ Editar
          </button>
          {u.id !== me?.id && (
            <button className={BTN_SMALL_DANGER} onClick={() => setToDelete(u)}>
              🗑️ Eliminar
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Usuarios"
        subtitle="Cuentas con acceso a esta plataforma de administración"
        actions={
          <button className={BTN_PRIMARY} onClick={openCreate}>
            + Nuevo usuario
          </button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="mb-4">
            <TextInput
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
              placeholder="Buscar por nombre o correo…"
              className="max-w-sm"
            />
          </div>

          <DataTable
            columns={columns}
            rows={data?.items}
            rowKey={(u) => u.id}
            loading={loading}
            error={error}
            onRetry={reload}
            emptyTitle="No hay usuarios"
            pagination={data ? { total: data.total, limit: LIMIT, offset, onPageChange: setOffset } : undefined}
          />
        </div>

        <ChangePasswordCard />
      </div>

      <Modal
        open={modalOpen}
        title={editing ? `Editar ${editing.full_name}` : 'Nuevo usuario'}
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button className={BTN_SECONDARY} onClick={() => setModalOpen(false)} disabled={saving}>
              Cancelar
            </button>
            <button className={BTN_PRIMARY} form="user-form" type="submit" disabled={saving}>
              {saving && <Spinner className="h-4 w-4" />}
              Guardar
            </button>
          </>
        }
      >
        <form id="user-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
          <FormField label="Correo electrónico" required>
            <TextInput
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
              disabled={!!editing}
            />
          </FormField>
          <FormField label="Nombre completo" required>
            <TextInput
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              required
            />
          </FormField>
          <FormField
            label={editing ? 'Nueva contraseña (dejar vacío para no cambiar)' : 'Contraseña'}
            required={!editing}
            hint="Mínimo 8 caracteres."
          >
            <TextInput
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required={!editing}
              minLength={8}
              autoComplete="new-password"
            />
          </FormField>
          <FormField label="Rol">
            <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}>
              {roleOptions.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABELS[r]}
                </option>
              ))}
            </Select>
          </FormField>
          {editing && (
            <Checkbox
              label="Cuenta activa"
              checked={form.is_active}
              onChange={(v) => setForm({ ...form, is_active: v })}
            />
          )}
          {formError && (
            <div className="rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-300">
              {formError}
            </div>
          )}
        </form>
      </Modal>

      <ConfirmDialog
        open={toDelete !== null}
        title="Eliminar usuario"
        message={`¿Eliminar la cuenta de "${toDelete?.full_name ?? ''}" (${toDelete?.email ?? ''})?`}
        onConfirm={handleDelete}
        onClose={() => setToDelete(null)}
      />
    </div>
  );
}
