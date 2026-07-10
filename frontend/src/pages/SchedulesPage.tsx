import { useState, type FormEvent } from 'react';
import { holidaysApi, schedulesApi } from '../api';
import { apiErrorMessage } from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';
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
import { EmptyState, ErrorBlock, LoadingBlock, Spinner } from '../components/Spinner';
import { Badge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { DAY_LABELS, formatDate, toHHMM, toHHMMSS } from '../lib/format';
import { useFetch } from '../lib/useFetch';
import type { Schedule } from '../types';

interface IntervalDraft {
  day_of_week: number;
  start: string; // HH:MM
  end: string;
}

// ---- Schedule editor modal ----
function ScheduleModal({
  schedule,
  onClose,
  onSaved,
}: {
  schedule: Schedule | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(schedule?.name ?? '');
  const [description, setDescription] = useState(schedule?.description ?? '');
  const [allowOnHolidays, setAllowOnHolidays] = useState(schedule?.allow_on_holidays ?? false);
  const [intervals, setIntervals] = useState<IntervalDraft[]>(
    (schedule?.intervals ?? []).map((iv) => ({
      day_of_week: iv.day_of_week,
      start: toHHMM(iv.start_time),
      end: toHHMM(iv.end_time),
    })),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addInterval = () => {
    setIntervals((prev) => [...prev, { day_of_week: 0, start: '08:00', end: '18:00' }]);
  };

  const addWeekdays = () => {
    setIntervals((prev) => [
      ...prev,
      ...[0, 1, 2, 3, 4].map((d) => ({ day_of_week: d, start: '08:00', end: '18:00' })),
    ]);
  };

  const updateInterval = (idx: number, patch: Partial<IntervalDraft>) => {
    setIntervals((prev) => prev.map((iv, i) => (i === idx ? { ...iv, ...patch } : iv)));
  };

  const removeInterval = (idx: number) => {
    setIntervals((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    for (const iv of intervals) {
      if (!iv.start || !iv.end || iv.start >= iv.end) {
        setError('Cada intervalo debe tener hora de inicio anterior a la de fin.');
        return;
      }
    }
    setSaving(true);
    setError(null);
    const body = {
      name,
      description: description || null,
      allow_on_holidays: allowOnHolidays,
      intervals: intervals.map((iv) => ({
        day_of_week: iv.day_of_week,
        start_time: toHHMMSS(iv.start),
        end_time: toHHMMSS(iv.end),
      })),
    };
    try {
      if (schedule) {
        await schedulesApi.update(schedule.id, body);
        toast.success('Horario actualizado');
      } else {
        await schedulesApi.create(body);
        toast.success('Horario creado');
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
      title={schedule ? `Editar ${schedule.name}` : 'Nuevo horario'}
      onClose={onClose}
      wide
      footer={
        <>
          <button className={BTN_SECONDARY} onClick={onClose} disabled={saving}>
            Cancelar
          </button>
          <button className={BTN_PRIMARY} form="schedule-form" type="submit" disabled={saving}>
            {saving && <Spinner className="h-4 w-4" />}
            Guardar
          </button>
        </>
      }
    >
      <form id="schedule-form" onSubmit={(e) => void handleSave(e)} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Nombre" required>
            <TextInput value={name} onChange={(e) => setName(e.target.value)} required placeholder="p. ej. Horario oficina" />
          </FormField>
          <FormField label="Descripción">
            <TextInput value={description} onChange={(e) => setDescription(e.target.value)} />
          </FormField>
        </div>

        <Checkbox
          label="Permitir acceso en días festivos"
          checked={allowOnHolidays}
          onChange={setAllowOnHolidays}
        />

        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Intervalos semanales
            </span>
            <div className="flex gap-2">
              <button type="button" className={BTN_SMALL} onClick={addWeekdays}>
                + Lun–Vie 08:00–18:00
              </button>
              <button type="button" className={BTN_SMALL} onClick={addInterval}>
                + Intervalo
              </button>
            </div>
          </div>

          {intervals.length === 0 ? (
            <p className="rounded-md border border-dashed border-slate-700 px-4 py-6 text-center text-xs text-slate-500">
              Sin intervalos: este horario no permite acceso en ningún momento. Agrega al menos un intervalo.
            </p>
          ) : (
            <div className="space-y-2">
              {intervals.map((iv, idx) => (
                <div
                  key={idx}
                  className="flex flex-wrap items-center gap-2 rounded-md border border-slate-700/60 bg-slate-800/40 px-3 py-2"
                >
                  <Select
                    value={iv.day_of_week}
                    onChange={(e) => updateInterval(idx, { day_of_week: Number(e.target.value) })}
                    className="w-36"
                    aria-label="Día de la semana"
                  >
                    {DAY_LABELS.map((label, d) => (
                      <option key={d} value={d}>
                        {label}
                      </option>
                    ))}
                  </Select>
                  <TextInput
                    type="time"
                    value={iv.start}
                    onChange={(e) => updateInterval(idx, { start: e.target.value })}
                    className="w-32"
                    aria-label="Hora de inicio"
                  />
                  <span className="text-slate-500">→</span>
                  <TextInput
                    type="time"
                    value={iv.end}
                    onChange={(e) => updateInterval(idx, { end: e.target.value })}
                    className="w-32"
                    aria-label="Hora de fin"
                  />
                  <button
                    type="button"
                    className={`${BTN_SMALL_DANGER} ml-auto`}
                    onClick={() => removeInterval(idx)}
                  >
                    Quitar
                  </button>
                </div>
              ))}
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

// ---- Holidays section ----
function HolidaysSection({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const { data, loading, error, reload } = useFetch(() => holidaysApi.list({ limit: 500 }), []);
  const [name, setName] = useState('');
  const [date, setDate] = useState('');
  const [busy, setBusy] = useState(false);
  const [toDelete, setToDelete] = useState<{ id: number; name: string } | null>(null);

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await holidaysApi.create({ name, date });
      toast.success('Día festivo agregado');
      setName('');
      setDate('');
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!toDelete) return;
    try {
      await holidaysApi.remove(toDelete.id);
      toast.success('Día festivo eliminado');
      setToDelete(null);
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
      setToDelete(null);
    }
  };

  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/60 p-5">
      <h2 className="mb-1 text-sm font-semibold text-slate-200">Días festivos</h2>
      <p className="mb-4 text-xs text-slate-500">
        En los días festivos solo se permite el acceso con horarios marcados como "permitir en festivos".
      </p>

      {canManage && (
        <form onSubmit={(e) => void handleAdd(e)} className="mb-4 flex flex-wrap gap-2">
          <TextInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nombre (p. ej. Año Nuevo)"
            required
            className="min-w-0 flex-1"
          />
          <TextInput
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
            className="w-40"
          />
          <button type="submit" className={BTN_SECONDARY} disabled={busy || !name || !date}>
            {busy ? <Spinner className="h-4 w-4" /> : '+ Agregar'}
          </button>
        </form>
      )}

      {loading ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorBlock message={error} onRetry={reload} />
      ) : (data?.items.length ?? 0) === 0 ? (
        <p className="py-4 text-center text-xs text-slate-500">Sin días festivos configurados.</p>
      ) : (
        <ul className="divide-y divide-slate-800">
          {(data?.items ?? []).map((h) => (
            <li key={h.id} className="flex items-center gap-3 py-2 text-sm">
              <span className="w-24 text-slate-400">{formatDate(h.date)}</span>
              <span className="flex-1 text-slate-200">{h.name}</span>
              {canManage && (
                <button className={BTN_SMALL_DANGER} onClick={() => setToDelete({ id: h.id, name: h.name })}>
                  Eliminar
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={toDelete !== null}
        title="Eliminar día festivo"
        message={`¿Eliminar "${toDelete?.name ?? ''}"?`}
        onConfirm={handleDelete}
        onClose={() => setToDelete(null)}
      />
    </div>
  );
}

export function SchedulesPage() {
  const { hasRole } = useAuth();
  const toast = useToast();
  const isAdmin = hasRole('admin');

  const { data, loading, error, reload } = useFetch(() => schedulesApi.list({ limit: 500 }), []);
  const [modal, setModal] = useState<{ open: boolean; schedule: Schedule | null }>({
    open: false,
    schedule: null,
  });
  const [toDelete, setToDelete] = useState<Schedule | null>(null);

  const handleDelete = async () => {
    if (!toDelete) return;
    try {
      await schedulesApi.remove(toDelete.id);
      toast.success('Horario eliminado');
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
        title="Horarios"
        subtitle="Perfiles semanales de tiempo que determinan cuándo se permite el acceso"
        actions={
          isAdmin && (
            <button className={BTN_PRIMARY} onClick={() => setModal({ open: true, schedule: null })}>
              + Nuevo horario
            </button>
          )
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {loading ? (
            <LoadingBlock />
          ) : error ? (
            <ErrorBlock message={error} onRetry={reload} />
          ) : (data?.items.length ?? 0) === 0 ? (
            <div className="rounded-xl border border-slate-700/60 bg-slate-900/60">
              <EmptyState
                title="No hay horarios definidos"
                hint={isAdmin ? 'Crea un horario para restringir accesos por franjas de tiempo.' : undefined}
              />
            </div>
          ) : (
            <div className="space-y-4">
              {(data?.items ?? []).map((schedule) => (
                <div
                  key={schedule.id}
                  className="rounded-xl border border-slate-700/60 bg-slate-900/60 p-5"
                >
                  <div className="mb-3 flex flex-wrap items-center gap-3">
                    <h3 className="text-sm font-semibold text-slate-100">{schedule.name}</h3>
                    {schedule.allow_on_holidays && <Badge tone="amber">Permite festivos</Badge>}
                    <div className="ml-auto flex gap-1.5">
                      {isAdmin && (
                        <>
                          <button
                            className={BTN_SMALL}
                            onClick={() => setModal({ open: true, schedule })}
                          >
                            ✏️ Editar
                          </button>
                          <button className={BTN_SMALL_DANGER} onClick={() => setToDelete(schedule)}>
                            🗑️ Eliminar
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  {schedule.description && (
                    <p className="mb-3 text-xs text-slate-500">{schedule.description}</p>
                  )}
                  {schedule.intervals.length === 0 ? (
                    <p className="text-xs text-slate-500">Sin intervalos (no permite acceso).</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {[...schedule.intervals]
                        .sort((a, b) => a.day_of_week - b.day_of_week || a.start_time.localeCompare(b.start_time))
                        .map((iv, i) => (
                          <span
                            key={iv.id ?? i}
                            className="rounded-md bg-slate-800/70 px-2.5 py-1 text-xs text-slate-300"
                          >
                            {DAY_LABELS[iv.day_of_week]} {toHHMM(iv.start_time)}–{toHHMM(iv.end_time)}
                          </span>
                        ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <HolidaysSection canManage={isAdmin} />
      </div>

      {modal.open && (
        <ScheduleModal
          schedule={modal.schedule}
          onClose={() => setModal({ open: false, schedule: null })}
          onSaved={reload}
        />
      )}

      <ConfirmDialog
        open={toDelete !== null}
        title="Eliminar horario"
        message={`¿Eliminar "${toDelete?.name ?? ''}"? Los niveles de acceso que lo usan quedarán sin restricción horaria en esas puertas.`}
        onConfirm={handleDelete}
        onClose={() => setToDelete(null)}
      />
    </div>
  );
}
