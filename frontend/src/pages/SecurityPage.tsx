import { useState, type FormEvent } from 'react';
import { authApi } from '../api';
import { apiErrorMessage } from '../api/client';
import { BTN_PRIMARY, BTN_SECONDARY, BTN_SMALL, FormField, TextInput } from '../components/FormField';
import { PageHeader } from '../components/Layout';
import { Spinner } from '../components/Spinner';
import { Badge } from '../components/StatusBadge';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';

/** Panel shown once after enabling/regenerating: the plaintext recovery codes. */
function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const toast = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(codes.join('\n'));
      toast.success('Códigos copiados al portapapeles');
    } catch {
      toast.error('No se pudo copiar; cópialos manualmente');
    }
  };
  return (
    <div className="space-y-3 rounded-lg border border-amber-500/40 bg-amber-950/30 p-4">
      <p className="text-sm text-amber-200">
        Guarda estos <strong>códigos de recuperación</strong> en un lugar seguro. Se muestran
        <strong> una sola vez</strong> y cada uno sirve para iniciar sesión una única vez si pierdes tu
        dispositivo.
      </p>
      <ul className="grid grid-cols-2 gap-2 font-mono text-sm text-amber-100">
        {codes.map((c) => (
          <li key={c} className="rounded bg-slate-900/70 px-2 py-1 text-center tracking-wider">
            {c}
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <button type="button" onClick={() => void copy()} className={BTN_SMALL}>
          Copiar todos
        </button>
        <button type="button" onClick={onDone} className={BTN_SMALL}>
          Ya los guardé
        </button>
      </div>
    </div>
  );
}

export function SecurityPage() {
  const { user, refreshUser } = useAuth();
  const toast = useToast();
  const enabled = !!user?.mfa_enabled;

  // Setup wizard state (disabled → setup → enabled).
  const [setup, setSetup] = useState<{ secret: string; uri: string } | null>(null);
  const [enableCode, setEnableCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);

  // Disable / regenerate share a password + current-code challenge.
  const [challengePassword, setChallengePassword] = useState('');
  const [challengeCode, setChallengeCode] = useState('');

  const startSetup = async () => {
    setBusy(true);
    try {
      const res = await authApi.mfaSetup();
      setSetup({ secret: res.secret, uri: res.provisioning_uri });
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const confirmEnable = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await authApi.mfaEnable(enableCode.trim());
      setRecoveryCodes(res.recovery_codes);
      setSetup(null);
      setEnableCode('');
      await refreshUser();
      toast.success('MFA activado');
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const disableMfa = async () => {
    setBusy(true);
    try {
      await authApi.mfaDisable(challengePassword, challengeCode.trim());
      setChallengePassword('');
      setChallengeCode('');
      await refreshUser();
      toast.success('MFA desactivado');
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await authApi.mfaRegenerateRecoveryCodes(challengePassword, challengeCode.trim());
      setRecoveryCodes(res.recovery_codes);
      setChallengePassword('');
      setChallengeCode('');
      toast.success('Nuevos códigos de recuperación generados');
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Seguridad de la cuenta"
        subtitle="Verificación en dos pasos (MFA) y contraseña"
      />

      <section className="mb-8 max-w-2xl space-y-4 rounded-xl border border-slate-700/60 bg-slate-900/50 p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Autenticación en dos pasos (TOTP)</h2>
          {enabled ? (
            <Badge tone="green">Activada</Badge>
          ) : (
            <Badge tone="slate">Desactivada</Badge>
          )}
        </div>

        {recoveryCodes && (
          <RecoveryCodes codes={recoveryCodes} onDone={() => setRecoveryCodes(null)} />
        )}

        {!enabled && !setup && !recoveryCodes && (
          <div className="space-y-3">
            <p className="text-sm text-slate-400">
              Añade una segunda capa de seguridad con una app autenticadora (Google Authenticator,
              Authy, 1Password…).
            </p>
            <button type="button" onClick={() => void startSetup()} disabled={busy} className={BTN_PRIMARY}>
              {busy && <Spinner className="h-4 w-4" />}
              Activar MFA
            </button>
          </div>
        )}

        {setup && (
          <form onSubmit={(e) => void confirmEnable(e)} className="space-y-3">
            <p className="text-sm text-slate-400">
              1. Agrega esta clave a tu app autenticadora (o escanea el enlace <code>otpauth://</code>):
            </p>
            <div className="rounded-md border border-slate-700 bg-slate-950/60 p-3">
              <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Clave secreta</p>
              <code className="block break-all font-mono text-sm text-sky-300">{setup.secret}</code>
              <p className="mt-2 mb-1 text-xs uppercase tracking-wide text-slate-500">Enlace otpauth</p>
              <code className="block break-all font-mono text-xs text-slate-400">{setup.uri}</code>
            </div>
            <FormField label="2. Ingresa el código de 6 dígitos que muestra la app" required>
              <TextInput
                inputMode="numeric"
                autoComplete="one-time-code"
                value={enableCode}
                onChange={(e) => setEnableCode(e.target.value)}
                placeholder="123456"
                required
                autoFocus
              />
            </FormField>
            <div className="flex gap-2">
              <button type="submit" disabled={busy} className={BTN_PRIMARY}>
                {busy && <Spinner className="h-4 w-4" />}
                Confirmar y activar
              </button>
              <button type="button" onClick={() => setSetup(null)} className={BTN_SECONDARY}>
                Cancelar
              </button>
            </div>
          </form>
        )}

        {enabled && (
          <div className="space-y-5">
            <p className="text-sm text-slate-400">
              Tu cuenta está protegida con MFA. Puedes regenerar tus códigos de recuperación o
              desactivar el segundo factor. Ambas acciones piden tu contraseña y un código actual.
            </p>
            <form onSubmit={(e) => void regenerate(e)} className="grid gap-3 sm:grid-cols-2">
              <FormField label="Contraseña" required>
                <TextInput
                  type="password"
                  autoComplete="current-password"
                  value={challengePassword}
                  onChange={(e) => setChallengePassword(e.target.value)}
                  required
                />
              </FormField>
              <FormField label="Código actual (TOTP)" required>
                <TextInput
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={challengeCode}
                  onChange={(e) => setChallengeCode(e.target.value)}
                  placeholder="123456"
                  required
                />
              </FormField>
              <div className="flex flex-wrap gap-2 sm:col-span-2">
                <button type="submit" disabled={busy} className={BTN_SECONDARY}>
                  {busy && <Spinner className="h-4 w-4" />}
                  Regenerar códigos de recuperación
                </button>
                <button
                  type="button"
                  onClick={() => void disableMfa()}
                  disabled={busy}
                  className="inline-flex items-center gap-2 rounded-md border border-red-500/40 px-4 py-2 text-sm text-red-300 transition hover:bg-red-500/10 disabled:opacity-50"
                >
                  Desactivar MFA
                </button>
              </div>
            </form>
          </div>
        )}
      </section>

      <ChangePasswordCard />
    </div>
  );
}

function ChangePasswordCard() {
  const toast = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== confirm) {
      toast.error('La nueva contraseña y su confirmación no coinciden');
      return;
    }
    setBusy(true);
    try {
      await authApi.changePassword(current, next);
      setCurrent('');
      setNext('');
      setConfirm('');
      toast.success('Contraseña actualizada. Vuelve a iniciar sesión.');
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="max-w-2xl space-y-4 rounded-xl border border-slate-700/60 bg-slate-900/50 p-5">
      <h2 className="text-sm font-semibold text-white">Cambiar contraseña</h2>
      <form onSubmit={(e) => void submit(e)} className="grid gap-3 sm:grid-cols-2">
        <FormField label="Contraseña actual" required>
          <TextInput
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </FormField>
        <div className="hidden sm:block" aria-hidden="true" />
        <FormField label="Nueva contraseña" required hint="Mínimo 8 caracteres">
          <TextInput
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            minLength={8}
            required
          />
        </FormField>
        <FormField label="Confirmar nueva contraseña" required>
          <TextInput
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            minLength={8}
            required
          />
        </FormField>
        <div className="sm:col-span-2">
          <button type="submit" disabled={busy} className={BTN_PRIMARY}>
            {busy && <Spinner className="h-4 w-4" />}
            Actualizar contraseña
          </button>
        </div>
      </form>
    </section>
  );
}
