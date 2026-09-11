import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../types';

const state: { user: User; refreshUser: () => Promise<void> } = {
  user: {
    id: 1,
    organization_id: 1,
    email: 'admin@test.com',
    full_name: 'Admin',
    role: 'admin',
    is_active: true,
    mfa_enabled: false,
    last_login_at: null,
    created_at: '2026-01-01T00:00:00Z',
  },
  refreshUser: vi.fn().mockResolvedValue(undefined),
};

const toast = { success: vi.fn(), error: vi.fn(), info: vi.fn() };

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: state.user, refreshUser: state.refreshUser }),
}));
vi.mock('../context/ToastContext', () => ({ useToast: () => toast }));
vi.mock('../api', () => ({
  authApi: {
    mfaSetup: vi.fn(),
    mfaEnable: vi.fn(),
    mfaDisable: vi.fn(),
    mfaRegenerateRecoveryCodes: vi.fn(),
    changePassword: vi.fn(),
  },
}));

import { authApi } from '../api';
import { SecurityPage } from './SecurityPage';

beforeEach(() => {
  vi.clearAllMocks();
  state.user = { ...state.user, mfa_enabled: false };
  vi.mocked(authApi.mfaSetup).mockResolvedValue({
    secret: 'JBSWY3DPEHPK3PXP',
    provisioning_uri: 'otpauth://totp/ACP:admin@test.com?secret=JBSWY3DPEHPK3PXP&issuer=ACP',
  });
  vi.mocked(authApi.mfaEnable).mockResolvedValue({
    detail: 'MFA enabled',
    recovery_codes: ['aaaa1111bbbb2222', 'cccc3333dddd4444'],
  });
  vi.mocked(authApi.mfaDisable).mockResolvedValue({ detail: 'MFA disabled' });
  vi.mocked(authApi.changePassword).mockResolvedValue({ detail: 'ok' });
});

describe('SecurityPage — MFA disabled', () => {
  it('runs the setup wizard: setup → shows secret → enable → shows recovery codes', async () => {
    render(<SecurityPage />);
    expect(screen.getByText('Desactivada')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /Activar MFA/ }));
    // The secret from mfaSetup is displayed for manual entry.
    await waitFor(() => expect(screen.getByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument());
    expect(authApi.mfaSetup).toHaveBeenCalledOnce();

    await userEvent.type(screen.getByPlaceholderText('123456'), '654321');
    await userEvent.click(screen.getByRole('button', { name: /Confirmar y activar/ }));

    await waitFor(() => expect(authApi.mfaEnable).toHaveBeenCalledWith('654321'));
    // The one-time recovery codes are shown after enabling.
    expect(await screen.findByText('aaaa1111bbbb2222')).toBeInTheDocument();
    expect(screen.getByText('cccc3333dddd4444')).toBeInTheDocument();
    expect(state.refreshUser).toHaveBeenCalled();
  });
});

describe('SecurityPage — MFA enabled', () => {
  beforeEach(() => {
    state.user = { ...state.user, mfa_enabled: true };
  });

  it('shows the enabled badge and disables MFA with password + code', async () => {
    render(<SecurityPage />);
    expect(screen.getByText('Activada')).toBeInTheDocument();

    const passwords = screen.getAllByLabelText(/Contraseña/i);
    await userEvent.type(passwords[0], 'secret-pass');
    await userEvent.type(screen.getByPlaceholderText('123456'), '111222');
    await userEvent.click(screen.getByRole('button', { name: /Desactivar MFA/ }));

    await waitFor(() => expect(authApi.mfaDisable).toHaveBeenCalledWith('secret-pass', '111222'));
  });
});

describe('SecurityPage — change password', () => {
  it('rejects a mismatched confirmation without calling the API', async () => {
    render(<SecurityPage />);
    await userEvent.type(screen.getByLabelText(/Contraseña actual/), 'old-pass');
    await userEvent.type(screen.getByLabelText(/Nueva contraseña/), 'new-pass-1');
    await userEvent.type(screen.getByLabelText(/Confirmar nueva contraseña/), 'different-2');
    await userEvent.click(screen.getByRole('button', { name: /Actualizar contraseña/ }));

    expect(toast.error).toHaveBeenCalled();
    expect(authApi.changePassword).not.toHaveBeenCalled();
  });
});
