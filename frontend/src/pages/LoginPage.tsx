import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { apiErrorMessage } from '../api/client';
import { FormField, TextInput, BTN_PRIMARY } from '../components/FormField';
import { Spinner } from '../components/Spinner';
import { useAuth } from '../context/AuthContext';

export function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) {
    return <Navigate to="/" replace />;
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      const from = (location.state as { from?: string } | null)?.from ?? '/';
      navigate(from, { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <span className="text-4xl" aria-hidden="true">🔐</span>
          <h1 className="mt-3 text-2xl font-bold tracking-tight text-white">Cerradura</h1>
          <p className="mt-1 text-sm text-slate-400">Plataforma de control de acceso</p>
        </div>

        <form
          onSubmit={(e) => void handleSubmit(e)}
          className="space-y-4 rounded-xl border border-slate-700/60 bg-slate-900/70 p-6 shadow-xl"
        >
          <FormField label="Correo electrónico" required>
            <TextInput
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="usuario@empresa.com"
              autoComplete="email"
              required
              autoFocus
            />
          </FormField>
          <FormField label="Contraseña" required>
            <TextInput
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
          </FormField>

          {error && (
            <div className="rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-300">
              {error}
            </div>
          )}

          <button type="submit" disabled={busy} className={`${BTN_PRIMARY} w-full justify-center`}>
            {busy && <Spinner className="h-4 w-4" />}
            Iniciar sesión
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-slate-600">
          Acceso restringido. Todas las acciones quedan registradas en auditoría.
        </p>
      </div>
    </div>
  );
}
