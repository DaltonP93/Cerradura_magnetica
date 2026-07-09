import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';

export type ToastKind = 'success' | 'error' | 'info';

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastContextValue {
  toast: (kind: ToastKind, message: string) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const KIND_STYLES: Record<ToastKind, string> = {
  success: 'border-emerald-500/40 bg-emerald-950/95 text-emerald-100',
  error: 'border-red-500/40 bg-red-950/95 text-red-100',
  info: 'border-sky-500/40 bg-sky-950/95 text-sky-100',
};

const KIND_ICONS: Record<ToastKind, string> = {
  success: '✓',
  error: '✕',
  info: 'ℹ',
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (kind: ToastKind, message: string) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev.slice(-4), { id, kind, message }]);
      window.setTimeout(() => dismiss(id), 5000);
    },
    [dismiss],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      toast,
      success: (m: string) => toast('success', m),
      error: (m: string) => toast('error', m),
      info: (m: string) => toast('info', m),
    }),
    [toast],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-start gap-3 rounded-lg border px-4 py-3 text-sm shadow-xl backdrop-blur ${KIND_STYLES[t.kind]}`}
            role="status"
          >
            <span className="mt-0.5 font-bold">{KIND_ICONS[t.kind]}</span>
            <span className="flex-1 break-words">{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              className="text-current opacity-60 transition hover:opacity-100"
              aria-label="Cerrar"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}
