import { useState, type FormEvent } from 'react';
import { sitesApi } from '../api';
import { apiErrorMessage } from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { DataTable, type Column } from '../components/DataTable';
import {
  FormField,
  TextInput,
  BTN_PRIMARY,
  BTN_SECONDARY,
  BTN_SMALL,
  BTN_SMALL_DANGER,
} from '../components/FormField';
import { PageHeader } from '../components/Layout';
import { Modal } from '../components/Modal';
import { Spinner } from '../components/Spinner';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { formatDate } from '../lib/format';
import { useFetch } from '../lib/useFetch';
import type { Site } from '../types';

interface SiteForm {
  name: string;
  address: string;
  timezone: string;
}

const EMPTY_FORM: SiteForm = { name: '', address: '', timezone: 'UTC' };

export function SitesPage() {
  const { hasRole } = useAuth();
  const toast = useToast();
  const isAdmin = hasRole('admin');

  const { data, loading, error, reload } = useFetch(() => sitesApi.list({ limit: 500 }), []);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Site | null>(null);
  const [form, setForm] = useState<SiteForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<Site | null>(null);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setModalOpen(true);
  };

  const openEdit = (s: Site) => {
    setEditing(s);
    setForm({ name: s.name, address: s.address ?? '', timezone: s.timezone });
    setFormError(null);
    setModalOpen(true);
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    const body = { name: form.name, address: form.address || null, timezone: form.timezone };
    try {
      if (editing) {
        await sitesApi.update(editing.id, body);
        toast.success('Sitio actualizado');
      } else {
        await sitesApi.create(body);
        toast.success('Sitio creado');
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
      await sitesApi.remove(toDelete.id);
      toast.success('Sitio eliminado');
      setToDelete(null);
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
      setToDelete(null);
    }
  };

  const columns: Column<Site>[] = [
    { header: 'Nombre', render: (s) => <span className="font-medium text-slate-100">{s.name}</span> },
    { header: 'Dirección', render: (s) => s.address ?? '—' },
    { header: 'Zona horaria', render: (s) => <span className="font-mono text-xs">{s.timezone}</span> },
    { header: 'Creado', render: (s) => formatDate(s.created_at) },
    {
      header: 'Acciones',
      className: 'whitespace-nowrap',
      render: (s) =>
        isAdmin ? (
          <div className="flex gap-1.5">
            <button className={BTN_SMALL} onClick={() => openEdit(s)}>
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
      <PageHeader
        title="Sitios"
        subtitle="Ubicaciones físicas donde se instalan los controladores"
        actions={
          isAdmin && (
            <button className={BTN_PRIMARY} onClick={openCreate}>
              + Nuevo sitio
            </button>
          )
        }
      />

      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(s) => s.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="No hay sitios registrados"
        emptyHint={isAdmin ? 'Crea un sitio para agrupar controladores por ubicación.' : undefined}
      />

      <Modal
        open={modalOpen}
        title={editing ? `Editar ${editing.name}` : 'Nuevo sitio'}
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button className={BTN_SECONDARY} onClick={() => setModalOpen(false)} disabled={saving}>
              Cancelar
            </button>
            <button className={BTN_PRIMARY} form="site-form" type="submit" disabled={saving}>
              {saving && <Spinner className="h-4 w-4" />}
              Guardar
            </button>
          </>
        }
      >
        <form id="site-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
          <FormField label="Nombre" required>
            <TextInput
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              placeholder="p. ej. Oficina central"
            />
          </FormField>
          <FormField label="Dirección">
            <TextInput value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          </FormField>
          <FormField label="Zona horaria" hint="Identificador IANA, p. ej. America/Mexico_City">
            <TextInput
              value={form.timezone}
              onChange={(e) => setForm({ ...form, timezone: e.target.value })}
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
        title="Eliminar sitio"
        message={`¿Eliminar "${toDelete?.name ?? ''}"? Los controladores asignados quedarán sin sitio.`}
        onConfirm={handleDelete}
        onClose={() => setToDelete(null)}
      />
    </div>
  );
}
