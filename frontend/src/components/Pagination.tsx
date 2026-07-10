interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (offset: number) => void;
}

export function Pagination({ total, limit, offset, onPageChange }: PaginationProps) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  const from = offset + 1;
  const to = Math.min(offset + limit, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-700/60 px-4 py-3 text-sm text-slate-400">
      <span>
        Mostrando <span className="text-slate-200">{from}–{to}</span> de{' '}
        <span className="text-slate-200">{total}</span>
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(Math.max(0, offset - limit))}
          disabled={page <= 1}
          className="rounded-md border border-slate-600 px-3 py-1.5 text-xs transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          ← Anterior
        </button>
        <span className="text-xs">
          Página {page} / {pages}
        </span>
        <button
          onClick={() => onPageChange(offset + limit)}
          disabled={page >= pages}
          className="rounded-md border border-slate-600 px-3 py-1.5 text-xs transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Siguiente →
        </button>
      </div>
    </div>
  );
}
