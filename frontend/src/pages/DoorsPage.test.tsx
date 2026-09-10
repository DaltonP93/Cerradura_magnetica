import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// Advanced door flags are not enforced by the backend, so the UI must render
// their controls DISABLED and carry a visible advisory (no false security).
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ hasRole: () => true }) }));
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }));
vi.mock('../api', () => ({
  doorsApi: {
    list: vi.fn(async () => ({
      items: [
        {
          id: 1, name: 'Puerta 1', number: 1, controller_id: 1, mode: 'controlled',
          open_duration_seconds: 5, held_open_alarm_seconds: 30, sensor_enabled: true,
          anti_passback: true, first_card_open: false, multi_card_count: 1,
        },
      ],
      total: 1,
    })),
    update: vi.fn(async () => ({})),
  },
  controllersApi: { list: vi.fn(async () => ({ items: [{ id: 1, name: 'Ctrl 1' }], total: 1 })) },
}));

import { DoorsPage } from './DoorsPage';

describe('DoorsPage advanced flags', () => {
  it('renders the advanced flag controls disabled with an advisory in the edit form', async () => {
    render(<DoorsPage />);
    fireEvent.click(await screen.findByRole('button', { name: /Editar/ }));

    // Advisory is visible.
    expect(screen.getByText(/Experimental · no aplicado/)).toBeInTheDocument();

    // The advanced-flag controls are disabled (cannot be toggled as if active).
    expect(screen.getByRole('checkbox', { name: /Anti-passback/ })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: /primera tarjeta/i })).toBeDisabled();
    expect(screen.getByLabelText(/Tarjetas simultáneas/)).toBeDisabled();

    // The stored value is still shown (checked reflects the saved config).
    expect(screen.getByRole('checkbox', { name: /Anti-passback/ })).toBeChecked();
  });
});
