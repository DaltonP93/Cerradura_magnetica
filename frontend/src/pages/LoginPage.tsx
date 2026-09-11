import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { apiErrorMessage } from '../api/client';
import { FormField, TextInput, BTN_PRIMARY } from '../components/FormField';
import { Spinner } from '../components/Spinner';
import { useAuth } from '../context/AuthContext';

type Step = 'credentials' | 'mfa';

export function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [step, setStep] = useState<Step>('credentials');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [recoveryCode, setRecoveryCode] = useState('');
  const [useRecovery, setUseRecovery] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) {
    return <Navigate to="/" replace />;
  }

  const goHome = () => {
    const from = (location.state as { from?: string } | null)?.from ?? '/';
    navigate(from, { replace: true });
  };

  const submitCredentials = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      goHome();
    } catch (err) {
      const msg = apiErrorMessage(err);
      // The server asks for a second factor with "MFA code required"; move to
      // the code step instead of showing it as an error.
      if (/mfa/i.test(msg)) {
        setStep('mfa');
      } else {
        setError(msg);
      }
    } finally {
      setBusy(false);
    }
  };

  const submitMfa = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(
        email,
        password,
        useRecovery ? { recoveryCode: recoveryCode.trim() } : { mfaCode: mfaCode.trim() },
      );
      goHome();
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

        {step === 'credentials' ? (
          <form
            onSubmit={(e) => void submitCredentials(e)}
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
        ) : (
          <form
            onSubmit={(e) => void submitMfa(e)}
            className="space-y-4 rounded-xl border border-slate-700/60 bg-slate-900/70 p-6 shadow-xl"
          >
            <p className="text-sm text-slate-300">
              Verificación en dos pasos para <span className="font-medium text-white">{email}</span>.
            </p>

            {!useRecovery ? (
              <FormField label="Código de la app autenticadora" required>
                <TextInput
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  placeholder="123456"
                  required
                  autoFocus
                />
              </FormField>
            ) : (
              <FormField label="Código de recuperación" required>
                <TextInput
                  value={recoveryCode}
                  onChange={(e) => setRecoveryCode(e.target.value)}
                  placeholder="p. ej. 3f9a1c2b7d8e4a5f"
                  autoComplete="off"
                  required
                  autoFocus
                />
              </FormField>
            )}

            {error && (
              <div className="rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-300">
                {error}
              </div>
            )}

            <button type="submit" disabled={busy} className={`${BTN_PRIMARY} w-full justify-center`}>
              {busy && <Spinner className="h-4 w-4" />}
              Verificar
            </button>

            <div className="flex items-center justify-between text-xs">
              <button
                type="button"
                onClick={() => {
                  setUseRecovery((v) => !v);
                  setError(null);
                }}
                className="text-sky-400 hover:text-sky-300"
              >
                {useRecovery ? 'Usar código de la app' : '¿Perdiste tu dispositivo? Usar código de recuperación'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setStep('credentials');
                  setError(null);
                  setMfaCode('');
                  setRecoveryCode('');
                  setUseRecovery(false);
                }}
                className="text-slate-500 hover:text-slate-300"
              >
                Volver
              </button>
            </div>
          </form>
        )}

        <p className="mt-6 text-center text-xs text-slate-600">
          Acceso restringido. Todas las acciones quedan registradas en auditoría.
        </p>
      </div>
    </div>
  );
}
