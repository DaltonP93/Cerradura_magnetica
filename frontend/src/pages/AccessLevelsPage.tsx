import { useState, type FormEvent } from 'react';
import { accessLevelsApi, controllersApi, doorsApi, schedulesApi } from '../api';
import { apiErrorMessage } from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';
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
import { EmptyState, ErrorBlock, LoadingBlock, Spinner } from '../components/Spinner';
import { Badge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { useFetch } from '../lib/useFetch';
import type { AccessLevel, Door, Schedule } from '../types';

// door_id -> selection: 'off' (no access) | '' (24/7) | schedule id as string
type RuleMap = Record<number, string>;

function LevelModal({
  level,
  doors,
  schedules,
  controllerNames,
  onClose,
  onSaved,
}: {
  level: AccessLevel | null;
  doors: Door[];
  schedules: Schedule[];
  controllerNames: Record<number, string>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(level?.name ?? '');
  const [description, setDescription] = useState(level?.description ?? '');
  const [rules, setRules] = useState<RuleMap>(() => {
    const map: RuleMap = {};
    for (const door of doors) map[door.id] = 'off';
    for (const rule of level?.door_rules ?? []) {
      map[rule.door_id] = rule.schedule_id == null ? '' : String(rule.schedule_id);
    }
    return map;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const door_rules = Object.entries(rules)
      .filter(([, v]) => v !== 'off')
      .map(([doorId, v]) => ({ door_id: Number(doorId), schedule_id: v === '' ? null : Number(v) }));
    try {
      if (level) {
        await accessLevelsApi.update(level.id, { name, description: description || null, door_rules });
        toast.success('Nivel de acceso actualizado');
      } else {
        await accessLevelsApi.create({ name, description: description || null, door_rules });
        toast.success('Nivel de acceso creado');
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
      title={level ? `Editar ${level.name}` : 'Nuevo nivel de acceso'}
      onClose={onClose}
      wide
      footer={
        <>
          <button className={BTN_SECONDARY} onClick={onClose} disabled={saving}>
            Cancelar
          </button>
          <button className={BTN_PRIMARY} form="level-form" type="submit" disabled={saving}>
            {saving && <Spinner className="h-4 w-4" />}
            Guardar
          </button>
        </>
      }
    >
      <form id="level-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Nombre" required>
            <TextInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="p. ej. Acceso general"
            />
          </FormField>
          <FormField label="Descripción">
            <TextInput value={description} onChange={(e) => setDescription(e.target.value)} />
          </FormField>
        </div>

        <div>
          <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">
            Puertas y horarios
          </span>
          {doors.length === 0 ? (
            <p className="rounded-md border border-dashed border-slate-700 px-4 py-6 text-center text-xs text-slate-500">
              No hay puertas registradas. Crea primero un controlador.
            </p>
          ) : (
            <div className="overflow-hidden rounded-lg border border-slate-700/60">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="bg-slate-800/50 text-xs uppercase text-slate-400">
                    <th className="px-3 py-2">Puerta</th>
                    <th className="px-3 py-2">Controlador</th>
                    <th className="px-3 py-2 w-64">Horario permitido</th>
                  </tr>
                </thead>
                <tbody>
                  {doors.map((door) => (
                    <tr key={door.id} className="border-t border-slate-800 text-slate-300">
                      <td className="px-3 py-2">{door.name}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">
                        {controllerNames[door.controller_id] ?? `#${door.controller_id}`}
                      </td>
                      <td className="px-3 py-2">
                        <Select
                          value={rules[door.id] ?? 'off'}
                          onChange={(e) => setRules({ ...rules, [door.id]: e.target.value })}
                          aria-label={`Horario para ${door.name}`}
                        >
                          <option value="off">Sin acceso</option>
                          <option value="">24/7 (siempre)</option>
                          {schedules.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.name}
                            </option>
                          ))}
                        </Select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {error && (
          <div className="rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}

export function AccessLevelsPage() {
  const { hasRole } = useAuth();
  const toast = useToast();
  const isAdmin = hasRole('admin');

  const { data, loading, error, reload } = useFetch(() => accessLevelsApi.list({ limit: 500 }), []);
  const { data: doorsPage } = useFetch(() => doorsApi.list({ limit: 500 }), []);
  const { data: schedulesPage } = useFetch(() => schedulesApi.list({ limit: 500 }), []);
  const { data: controllersPage } = useFetch(() => controllersApi.list({ limit: 200 }), []);

  const [modal, setModal] = useState<{ open: boolean; level: AccessLevel | null }>({
    open: false,
    level: null,
  });
  const [toDelete, setToDelete] = useState<AccessLevel | null>(null);

  const doors = doorsPage?.items ?? [];
  const schedules = schedulesPage?.items ?? [];
  const controllerNames: Record<number, string> = Object.fromEntries(
    (controllersPage?.items ?? []).map((c) => [c.id, c.name]),
  );
  const doorName = (id: number) => doors.find((d) => d.id === id)?.name ?? `Puerta #${id}`;
  const scheduleName = (id: number | null) =>
    id == null ? '24/7' : schedules.find((s) => s.id === id)?.name ?? `Horario #${id}`;

  const handleDelete = async () => {
    if (!toDelete) return;
    try {
      await accessLevelsApi.remove(toDelete.id);
      toast.success('Nivel de acceso eliminado');
      setToDelete(null);
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
      setToDelete(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Niveles de acceso"
        subtitle="Conjuntos de puertas y horarios asignables al personal"
        actions={
          isAdmin && (
            <button className={BTN_PRIMARY} onClick={() => setModal({ open: true, level: null })}>
              + Nuevo nivel
            </button>
          )
        }
      />

      {loading ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorBlock message={error} onRetry={reload} />
      ) : (data?.items.length ?? 0) === 0 ? (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/60">
          <EmptyState
            title="No hay niveles de acceso"
            hint={
              isAdmin
                ? 'Crea un nivel de acceso para definir a qué puertas y en qué horarios puede acceder el personal.'
                : undefined
            }
          />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {(data?.items ?? []).map((level) => (
            <div key={level.id} className="rounded-xl border border-slate-700/60 bg-slate-900/60 p-5">
              <div className="mb-2 flex items-center gap-3">
                <h3 className="text-sm font-semibold text-slate-100">{level.name}</h3>
                <div className="ml-auto flex gap-1.5">
                  {isAdmin && (
                    <>
                      <button className={BTN_SMALL} onClick={() => setModal({ open: true, level })}>
                        ✏️ Editar
                      </button>
                      <button className={BTN_SMALL_DANGER} onClick={() => setToDelete(level)}>
                        🗑️
                      </button>
                    </>
                  )}
                </div>
              </div>
              {level.description && <p className="mb-3 text-xs text-slate-500">{level.description}</p>}
              {level.door_rules.length === 0 ? (
                <p className="text-xs text-slate-500">No otorga acceso a ninguna puerta.</p>
              ) : (
                <ul className="space-y-1.5">
                  {level.door_rules.map((rule, i) => (
                    <li key={rule.id ?? i} className="flex items-center gap-2 text-sm text-slate-300">
                      <span className="flex-1 truncate">🚪 {doorName(rule.door_id)}</span>
                      <Badge tone={rule.schedule_id == null ? 'green' : 'sky'}>
                        {scheduleName(rule.schedule_id)}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}

      {modal.open && (
        <LevelModal
          level={modal.level}
          doors={doors}
          schedules={schedules}
          controllerNames={controllerNames}
          onClose={() => setModal({ open: false, level: null })}
          onSaved={reload}
        />
      )}

      <ConfirmDialog
        open={toDelete !== null}
        title="Eliminar nivel de acceso"
        message={`¿Eliminar "${toDelete?.name ?? ''}"? Las personas que lo tengan asignado perderán esos permisos.`}
        onConfirm={handleDelete}
        onClose={() => setToDelete(null)}
      />
    </div>
  );
}
