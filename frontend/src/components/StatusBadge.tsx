export type Tone = 'green' | 'red' | 'amber' | 'orange' | 'slate' | 'sky';

const TONE_CLASSES: Record<Tone, string> = {
  green: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30',
  red: 'bg-red-500/15 text-red-300 ring-red-500/30',
  amber: 'bg-amber-500/15 text-amber-300 ring-amber-500/30',
  orange: 'bg-orange-500/15 text-orange-300 ring-orange-500/30',
  slate: 'bg-slate-500/15 text-slate-300 ring-slate-500/30',
  sky: 'bg-sky-500/15 text-sky-300 ring-sky-500/30',
};

export function Badge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: 'online' | 'offline' | 'unknown' }) {
  const map = {
    online: { tone: 'green' as Tone, label: 'En línea' },
    offline: { tone: 'red' as Tone, label: 'Fuera de línea' },
    unknown: { tone: 'slate' as Tone, label: 'Desconocido' },
  };
  const { tone, label } = map[status];
  return (
    <Badge tone={tone}>
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          status === 'online' ? 'bg-emerald-400' : status === 'offline' ? 'bg-red-400' : 'bg-slate-400'
        }`}
      />
      {label}
    </Badge>
  );
}

export function ActiveBadge({ active }: { active: boolean }) {
  return <Badge tone={active ? 'green' : 'slate'}>{active ? 'Activo' : 'Inactivo'}</Badge>;
}
