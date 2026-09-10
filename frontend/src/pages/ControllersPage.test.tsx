import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// Interlock is stored but not enforced by the platform, so its control must be
// rendered DISABLED with an advisory in the edit form.
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ hasRole: () => true }) }));
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }));
vi.mock('../api', () => ({
  controllersApi: {
    list: vi.fn(async () => ({
      items: [
        {
          id: 1, name: 'Ctrl 1', serial_number: '123456789', ip_address: '10.0.0.1',
          port: 60000, site_id: null, door_count: 4, interlock_enabled: true,
          status: 'unknown', last_seen_at: null, doors: [],
        },
      ],
      total: 1,
    })),
    update: vi.fn(async () => ({})),
    create: vi.fn(async () => ({})),
    remove: vi.fn(async () => ({})),
    ping: vi.fn(), syncTime: vi.fn(), syncPermissions: vi.fn(),
  },
  sitesApi: { list: vi.fn(async () => ({ items: [], total: 0 })) },
}));

import { ControllersPage } from './ControllersPage';

describe('ControllersPage interlock flag', () => {
  it('renders interlock disabled with an advisory in the edit form', async () => {
    render(<ControllersPage />);
    fireEvent.click(await screen.findByRole('button', { name: /Editar/ }));

    expect(screen.getByText(/Experimental · no aplicado/)).toBeInTheDocument();
    const interlock = screen.getByRole('checkbox', { name: /Interlock/ });
    expect(interlock).toBeDisabled();
    expect(interlock).toBeChecked(); // stored value still shown
  });
});
