import { useState, type FormEvent } from 'react';
import { controllersApi, sitesApi } from '../api';
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
import { Badge, StatusBadge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { DOOR_MODE_LABELS, formatDateTime } from '../lib/format';
import { useDebounced, useFetch } from '../lib/useFetch';
import type { Controller } from '../types';

const LIMIT = 25;

interface ControllerForm {
  name: string;
  serial_number: string;
  ip_address: string;
  port: string;
  site_id: string;
  door_count: string;
}

const EMPTY_FORM: ControllerForm = {
  name: '',
  serial_number: '',
  ip_address: '',
  port: '60000',
  site_id: '',
  door_count: '4',
};

export function ControllersPage() {
  const { hasRole } = useAuth();
  const toast = useToast();
  const isAdmin = hasRole('admin');
  const isOperator = hasRole('operator');

  const [search, setSearch] = useState('');
  const q = useDebounced(search);
  const [offset, setOffset] = useState(0);
  const { data, loading, error, reload } = useFetch(
    () => controllersApi.list({ q: q || undefined, limit: LIMIT, offset }),
    [q, offset],
  );
  const { data: sitesPage } = useFetch(() => sitesApi.list({ limit: 500 }), []);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Controller | null>(null);
  const [form, setForm] = useState<ControllerForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<Controller | null>(null);
  const [detail, setDetail] = useState<Controller | null>(null);
  const [commandBusy, setCommandBusy] = useState<string | null>(null);

  const siteName = (siteId: number | null) =>
    sitesPage?.items.find((s) => s.id === siteId)?.name ?? (siteId == null ? '—' : `#${siteId}`);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setModalOpen(true);
  };

  const openEdit = (c: Controller) => {
    setEditing(c);
    setForm({
      name: c.name,
      serial_number: c.serial_number,
      ip_address: c.ip_address ?? '',
      port: String(c.port),
      site_id: c.site_id != null ? String(c.site_id) : '',
      door_count: String(c.door_count),
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
        await controllersApi.update(editing.id, {
          name: form.name,
          ip_address: form.ip_address || null,
          port: Number(form.port),
          site_id: form.site_id ? Number(form.site_id) : null,
        });
        toast.success('Controlador actualizado');
      } else {
        await controllersApi.create({
          name: form.name,
          serial_number: form.serial_number,
          ip_address: form.ip_address || null,
          port: Number(form.port),
          site_id: form.site_id ? Number(form.site_id) : null,
          door_count: Number(form.door_count),
        });
        toast.success('Controlador creado con sus puertas');
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
      await controllersApi.remove(toDelete.id);
      toast.success('Controlador eliminado');
      setToDelete(null);
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  };

  const runCommand = async (c: Controller, cmd: 'ping' | 'sync-time' | 'sync-permissions') => {
    const key = `${c.id}:${cmd}`;
    setCommandBusy(key);
    try {
      const fn =
        cmd === 'ping'
          ? controllersApi.ping
          : cmd === 'sync-time'
            ? controllersApi.syncTime
            : controllersApi.syncPermissions;
      const result = await fn(c.id);
      if (result.success) toast.success(result.message);
      else toast.error(result.message);
      if (cmd === 'ping') reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setCommandBusy(null);
    }
  };

  const columns: Column<Controller>[] = [
    {
      header: 'Nombre',
      render: (c) => (
        <button onClick={() => setDetail(c)} className="font-medium text-sky-400 hover:text-sky-300">
          {c.name}
        </button>
      ),
    },
    { header: 'Serie', render: (c) => <span className="font-mono text-xs">{c.serial_number}</span> },
    { header: 'Dirección', render: (c) => (c.ip_address ? `${c.ip_address}:${c.port}` : '—') },
    { header: 'Sitio', render: (c) => siteName(c.site_id) },
    { header: 'Puertas', render: (c) => c.doors.length },
    { header: 'Estado', render: (c) => <StatusBadge status={c.status} /> },
    { header: 'Última conexión', render: (c) => formatDateTime(c.last_seen_at) },
    {
      header: 'Acciones',
      className: 'whitespace-nowrap',
      render: (c) => (
        <div className="flex flex-wrap gap-1.5">
          {isOperator && (
            <>
              <button
                className={BTN_SMALL}
                disabled={commandBusy !== null}
                onClick={() => void runCommand(c, 'ping')}
                title="Verificar conectividad"
              >
                {commandBusy === `${c.id}:ping` ? <Spinner className="h-3 w-3" /> : '📶'} Ping
              </button>
              <button
                className={BTN_SMALL}
                disabled={commandBusy !== null}
                onClick={() => void runCommand(c, 'sync-time')}
                title="Sincronizar reloj del controlador"
              >
                {commandBusy === `${c.id}:sync-time` ? <Spinner className="h-3 w-3" /> : '🕒'} Hora
              </button>
              <button
                className={BTN_SMALL}
                disabled={commandBusy !== null}
                onClick={() => void runCommand(c, 'sync-permissions')}
                title="Enviar permisos de tarjetas al controlador"
              >
                {commandBusy === `${c.id}:sync-permissions` ? <Spinner className="h-3 w-3" /> : '🔑'} Permisos
              </button>
            </>
          )}
          {isAdmin && (
            <>
              <button className={BTN_SMALL} onClick={() => openEdit(c)}>
                ✏️ Editar
              </button>
              <button className={BTN_SMALL_DANGER} onClick={() => setToDelete(c)}>
                🗑️ Eliminar
              </button>
            </>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Controladores"
        subtitle="Placas L04 de 4 puertas registradas en la organización"
        actions={
          isAdmin && (
            <button className={BTN_PRIMARY} onClick={openCreate}>
              + Nuevo controlador
            </button>
          )
        }
      />

      <div className="mb-4">
        <TextInput
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
          placeholder="Buscar por nombre o número de serie…"
          className="max-w-sm"
        />
      </div>

      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(c) => c.id}
        loading={loading}
        error={error}
        onRetry={reload}
        emptyTitle="No hay controladores registrados"
        emptyHint={
          isAdmin
            ? 'Crea el primer controlador con el botón "Nuevo controlador". Sus puertas se generan automáticamente.'
            : 'Aún no se han registrado controladores en esta organización.'
        }
        pagination={
          data ? { total: data.total, limit: LIMIT, offset, onPageChange: setOffset } : undefined
        }
      />

      {/* Create/edit modal */}
      <Modal
        open={modalOpen}
        title={editing ? `Editar ${editing.name}` : 'Nuevo controlador'}
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button className={BTN_SECONDARY} onClick={() => setModalOpen(false)} disabled={saving}>
              Cancelar
            </button>
            <button className={BTN_PRIMARY} form="controller-form" type="submit" disabled={saving}>
              {saving && <Spinner className="h-4 w-4" />}
              Guardar
            </button>
          </>
        }
      >
        <form id="controller-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
          <FormField label="Nombre" required>
            <TextInput
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              placeholder="p. ej. Controlador entrada principal"
            />
          </FormField>
          <FormField label="Número de serie" required hint={editing ? 'El número de serie no se puede modificar.' : undefined}>
            <TextInput
              value={form.serial_number}
              onChange={(e) => setForm({ ...form, serial_number: e.target.value })}
              required
              disabled={!!editing}
              placeholder="p. ej. L04-000123"
            />
          </FormField>
          <div className="grid grid-cols-2 gap-4">
            <FormField label="Dirección IP">
              <TextInput
                value={form.ip_address}
                onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
                placeholder="192.168.1.100"
              />
            </FormField>
            <FormField label="Puerto">
              <TextInput
                type="number"
                min={1}
                max={65535}
                value={form.port}
                onChange={(e) => setForm({ ...form, port: e.target.value })}
              />
            </FormField>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <FormField label="Sitio">
              <Select value={form.site_id} onChange={(e) => setForm({ ...form, site_id: e.target.value })}>
                <option value="">Sin sitio</option>
                {(sitesPage?.items ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="Nº de puertas" hint={editing ? 'Fijado al crear.' : 'La placa L04 admite hasta 4.'}>
              <Select
                value={form.door_count}
                onChange={(e) => setForm({ ...form, door_count: e.target.value })}
                disabled={!!editing}
              >
                {[1, 2, 3, 4].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            </FormField>
          </div>
          {formError && (
            <div className="rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-300">
              {formError}
            </div>
          )}
        </form>
      </Modal>

      {/* Detail modal: the controller's doors */}
      <Modal
        open={detail !== null}
        title={detail ? `${detail.name} — detalle` : ''}
        onClose={() => setDetail(null)}
        wide
      >
        {detail && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div>
                <p className="text-xs text-slate-500">Modelo</p>
                <p className="text-slate-200">{detail.model}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Serie</p>
                <p className="font-mono text-xs text-slate-200">{detail.serial_number}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Firmware</p>
                <p className="text-slate-200">{detail.firmware_version ?? '—'}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Estado</p>
                <StatusBadge status={detail.status} />
              </div>
            </div>
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Puertas ({detail.doors.length})
              </h3>
              <div className="overflow-hidden rounded-lg border border-slate-700/60">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="bg-slate-800/50 text-xs uppercase text-slate-400">
                      <th className="px-3 py-2">Nº</th>
                      <th className="px-3 py-2">Nombre</th>
                      <th className="px-3 py-2">Modo</th>
                      <th className="px-3 py-2">Apertura (s)</th>
                      <th className="px-3 py-2">Sensor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.doors.map((door) => (
                      <tr key={door.id} className="border-t border-slate-800 text-slate-300">
                        <td className="px-3 py-2">{door.number}</td>
                        <td className="px-3 py-2">{door.name}</td>
                        <td className="px-3 py-2">
                          <Badge tone={door.mode === 'controlled' ? 'sky' : 'slate'}>
                            {DOOR_MODE_LABELS[door.mode]}
                          </Badge>
                        </td>
                        <td className="px-3 py-2">{door.open_duration_seconds}</td>
                        <td className="px-3 py-2">{door.sensor_enabled ? 'Sí' : 'No'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Configura cada puerta desde la página <span className="text-slate-300">Puertas</span>.
              </p>
            </div>
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={toDelete !== null}
        title="Eliminar controlador"
        message={`¿Eliminar "${toDelete?.name ?? ''}"? Se eliminarán también sus puertas y la configuración asociada. Esta acción no se puede deshacer.`}
        onConfirm={handleDelete}
        onClose={() => setToDelete(null)}
      />
    </div>
  );
}
