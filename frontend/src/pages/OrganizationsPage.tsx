import { useState, type FormEvent } from 'react';
import { organizationsApi } from '../api';
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
import { ActiveBadge, Badge } from '../components/StatusBadge';
import { useToast } from '../context/ToastContext';
import { formatDate } from '../lib/format';
import { useDebounced, useFetch } from '../lib/useFetch';
import type { Organization } from '../types';

const LIMIT = 25;
const PLANS = ['free', 'basic', 'pro', 'enterprise'];

interface OrgForm {
  name: string;
  slug: string;
  contact_email: string;
  plan: string;
  is_active: boolean;
}

const EMPTY_FORM: OrgForm = { name: '', slug: '', contact_email: '', plan: 'free', is_active: true };

export function OrganizationsPage() {
  const toast = useToast();
  const [search, setSearch] = useState('');
  const q = useDebounced(search);
  const [offset, setOffset] = useState(0);
  const { data, loading, error, reload } = useFetch(
    () => organizationsApi.list({ q: q || undefined, limit: LIMIT, offset }),
    [q, offset],
  );

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Organization | null>(null);
  const [form, setForm] = useState<OrgForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setModalOpen(true);
  };

  const openEdit = (org: Organization) => {
    setEditing(org);
    setForm({
      name: org.name,
      slug: org.slug,
      contact_email: org.contact_email ?? '',
      plan: org.plan,
      is_active: org.is_active,
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
        await organizationsApi.update(editing.id, {
          name: form.name,
          contact_email: form.contact_email || null,
          plan: form.plan,
          is_active: form.is_active,
        });
        toast.success('Organización actualizada');
      } else {
        await organizationsApi.create({
          name: form.name,
          slug: form.slug,
          contact_email: form.contact_email || null,
          plan: form.plan,
        });
        toast.success('Organización creada');
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const columns: Column<Organization>[] = [
    { header: 'Nombre', render: (o) => <span className="font-medium text-slate-100">{o.name}</span> },
    { header: 'Slug', render: (o) => <span className="font-mono text-xs">{o.slug}</span> },
    { header: 'Contacto', render: (o) => o.contact_email ?? '—' },
    { header: 'Plan', render: (o) => <Badge tone="sky">{o.plan}</Badge> },
    { header: 'Estado', render: (o) => <ActiveBadge active={o.is_active} /> },
    { header: 'Creada', render: (o) => formatDate(o.created_at) },
    {
      header: 'Acciones',
      className: 'whitespace-nowrap',
      render: (o) => (
        <button className={BTN_SMALL} onClick={() => openEdit(o)}>
          ✏️ Editar
        </button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Organizaciones"
        subtitle="Inquilinos (tenants) de la plataforma — solo súper administradores"
        actions={
          <button className={BTN_PRIMARY} onClick={openCreate}>
            + Nueva organización
          </button>
        }
      />

      <div className="mb-4">
        <TextInput
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
          placeholder="Buscar por nombre…"
          className="max-w-sm"
        />
      </div>

      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(o) => o.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="No hay organizaciones"
        emptyHint="Crea la primera organización de la plataforma."
        pagination={data ? { total: data.total, limit: LIMIT, offset, onPageChange: setOffset } : undefined}
      />

      <Modal
        open={modalOpen}
        title={editing ? `Editar ${editing.name}` : 'Nueva organización'}
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button className={BTN_SECONDARY} onClick={() => setModalOpen(false)} disabled={saving}>
              Cancelar
            </button>
            <button className={BTN_PRIMARY} form="org-form" type="submit" disabled={saving}>
              {saving && <Spinner className="h-4 w-4" />}
              Guardar
            </button>
          </>
        }
      >
        <form id="org-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
          <FormField label="Nombre" required>
            <TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </FormField>
          <FormField
            label="Slug"
            required={!editing}
            hint={editing ? 'El slug no se puede modificar.' : 'Minúsculas, números y guiones (p. ej. mi-empresa).'}
          >
            <TextInput
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
              required={!editing}
              disabled={!!editing}
              pattern="[a-z0-9][a-z0-9-]*"
            />
          </FormField>
          <FormField label="Correo de contacto">
            <TextInput
              type="email"
              value={form.contact_email}
              onChange={(e) => setForm({ ...form, contact_email: e.target.value })}
            />
          </FormField>
          <FormField label="Plan">
            <Select value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value })}>
              {PLANS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </FormField>
          {editing && (
            <Checkbox
              label="Organización activa"
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
    </div>
  );
}
