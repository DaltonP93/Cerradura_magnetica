import { useState, type FormEvent } from 'react';
import { departmentsApi } from '../api';
import { apiErrorMessage } from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { DataTable, type Column } from '../components/DataTable';
import {
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
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { formatDate } from '../lib/format';
import { useFetch } from '../lib/useFetch';
import type { Department } from '../types';

export function DepartmentsPage() {
  const { hasRole } = useAuth();
  const toast = useToast();
  const canManage = hasRole('operator');

  const { data, loading, error, reload } = useFetch(() => departmentsApi.list({ limit: 500 }), []);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Department | null>(null);
  const [name, setName] = useState('');
  const [parentId, setParentId] = useState('');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<Department | null>(null);

  const parentName = (id: number | null) =>
    id == null ? '—' : data?.items.find((d) => d.id === id)?.name ?? `#${id}`;

  const openCreate = () => {
    setEditing(null);
    setName('');
    setParentId('');
    setFormError(null);
    setModalOpen(true);
  };

  const openEdit = (d: Department) => {
    setEditing(d);
    setName(d.name);
    setParentId(d.parent_id != null ? String(d.parent_id) : '');
    setFormError(null);
    setModalOpen(true);
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    const body = { name, parent_id: parentId ? Number(parentId) : null };
    try {
      if (editing) {
        await departmentsApi.update(editing.id, body);
        toast.success('Departamento actualizado');
      } else {
        await departmentsApi.create(body);
        toast.success('Departamento creado');
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
      await departmentsApi.remove(toDelete.id);
      toast.success('Departamento eliminado');
      setToDelete(null);
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
      setToDelete(null);
    }
  };

  const columns: Column<Department>[] = [
    { header: 'Nombre', render: (d) => <span className="font-medium text-slate-100">{d.name}</span> },
    { header: 'Departamento padre', render: (d) => parentName(d.parent_id) },
    { header: 'Creado', render: (d) => formatDate(d.created_at) },
    {
      header: 'Acciones',
      className: 'whitespace-nowrap',
      render: (d) =>
        canManage ? (
          <div className="flex gap-1.5">
            <button className={BTN_SMALL} onClick={() => openEdit(d)}>
              ✏️ Editar
            </button>
            <button className={BTN_SMALL_DANGER} onClick={() => setToDelete(d)}>
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
        title="Departamentos"
        subtitle="Estructura organizativa del personal"
        actions={
          canManage && (
            <button className={BTN_PRIMARY} onClick={openCreate}>
              + Nuevo departamento
            </button>
          )
        }
      />

      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(d) => d.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="No hay departamentos"
        emptyHint={canManage ? 'Crea departamentos para organizar al personal.' : undefined}
      />

      <Modal
        open={modalOpen}
        title={editing ? `Editar ${editing.name}` : 'Nuevo departamento'}
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button className={BTN_SECONDARY} onClick={() => setModalOpen(false)} disabled={saving}>
              Cancelar
            </button>
            <button className={BTN_PRIMARY} form="dept-form" type="submit" disabled={saving}>
              {saving && <Spinner className="h-4 w-4" />}
              Guardar
            </button>
          </>
        }
      >
        <form id="dept-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
          <FormField label="Nombre" required>
            <TextInput value={name} onChange={(e) => setName(e.target.value)} required />
          </FormField>
          <FormField label="Departamento padre">
            <Select value={parentId} onChange={(e) => setParentId(e.target.value)}>
              <option value="">Ninguno (nivel superior)</option>
              {(data?.items ?? [])
                .filter((d) => d.id !== editing?.id)
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
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
      </Modal>

      <ConfirmDialog
        open={toDelete !== null}
        title="Eliminar departamento"
        message={`¿Eliminar "${toDelete?.name ?? ''}"? No se puede eliminar si tiene personal asignado.`}
        onConfirm={handleDelete}
        onClose={() => setToDelete(null)}
      />
    </div>
  );
}
