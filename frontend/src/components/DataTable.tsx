import type { ReactNode } from 'react';
import { EmptyState, ErrorBlock, LoadingBlock } from './Spinner';
import { Pagination } from './Pagination';

export interface Column<T> {
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string | number;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
  emptyTitle: string;
  emptyHint?: string;
  onRowClick?: (row: T) => void;
  pagination?: { total: number; limit: number; offset: number; onPageChange: (offset: number) => void };
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  onRetry,
  emptyTitle,
  emptyHint,
  onRowClick,
  pagination,
}: DataTableProps<T>) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-700/60 bg-slate-900/60">
      {loading && !rows ? (
        <LoadingBlock />
      ) : error ? (
        <div className="p-4">
          <ErrorBlock message={error} onRetry={onRetry} />
        </div>
      ) : !rows || rows.length === 0 ? (
        <EmptyState title={emptyTitle} hint={emptyHint} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-700/60 bg-slate-800/50 text-xs uppercase tracking-wide text-slate-400">
                {columns.map((col) => (
                  <th key={col.header} className={`px-4 py-3 font-medium ${col.className ?? ''}`}>
                    {col.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className={loading ? 'opacity-50 transition-opacity' : ''}>
              {rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={`border-b border-slate-800/80 text-slate-300 last:border-0 ${
                    onRowClick ? 'cursor-pointer transition hover:bg-slate-800/50' : ''
                  }`}
                >
                  {columns.map((col) => (
                    <td key={col.header} className={`px-4 py-3 ${col.className ?? ''}`}>
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pagination && !error && <Pagination {...pagination} />}
    </div>
  );
}
