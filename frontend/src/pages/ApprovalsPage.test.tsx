import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Door, DoorOpenRequest } from '../types';

// The page pulls the current user and role from AuthContext and toasts from
// ToastContext; mock both so the component renders in isolation.
const currentUser = { id: 7 };
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: currentUser, hasRole: () => true }),
}));
vi.mock('../context/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));
vi.mock('../api', () => ({
  doorsApi: {
    listOpenRequests: vi.fn(),
    list: vi.fn(),
    requestOpen: vi.fn(),
    approveOpenRequest: vi.fn(),
    rejectOpenRequest: vi.fn(),
  },
}));

import { doorsApi } from '../api';
import { ApprovalsPage } from './ApprovalsPage';

function door(id: number, name: string, critical: boolean): Door {
  return {
    id,
    controller_id: 1,
    number: id,
    name,
    mode: 'controlled',
    open_duration_seconds: 5,
    held_open_alarm_seconds: 30,
    sensor_enabled: false,
    anti_passback: false,
    first_card_open: false,
    multi_card_count: 1,
    requires_dual_approval: critical,
  };
}

function req(id: number, requestedBy: number): DoorOpenRequest {
  return {
    id,
    door_id: 1,
    controller_id: 1,
    requested_by_id: requestedBy,
    approved_by_id: null,
    status: 'pending',
    reason: 'visita',
    created_at: '2026-09-07T12:00:00Z',
    expires_at: '2026-09-07T12:05:00Z',
    resolved_at: null,
  };
}

beforeEach(() => {
  vi.mocked(doorsApi.list).mockResolvedValue({
    items: [door(1, 'Bóveda', true), door(2, 'Recepción', false)],
    total: 2,
    limit: 200,
    offset: 0,
  });
  // request 100 was made by another operator (id 9); request 101 by me (id 7).
  vi.mocked(doorsApi.listOpenRequests).mockResolvedValue({
    items: [req(100, 9), req(101, 7)],
    total: 2,
    limit: 100,
    offset: 0,
  });
  vi.mocked(doorsApi.approveOpenRequest).mockResolvedValue({ ...req(100, 9), status: 'executed' });
  vi.mocked(doorsApi.rejectOpenRequest).mockResolvedValue({ ...req(100, 9), status: 'rejected' });
  vi.mocked(doorsApi.requestOpen).mockResolvedValue(req(102, 7));
});

describe('ApprovalsPage', () => {
  it('lists pending requests with their door and status', async () => {
    render(<ApprovalsPage />);
    // Two rows reference "Bóveda"; both render once the fetch resolves.
    await waitFor(() => expect(screen.getAllByText('Bóveda').length).toBeGreaterThanOrEqual(2));
    expect(screen.getAllByText('Pendiente').length).toBe(2);
  });

  it("disables Approve on the operator's own request (two-person rule)", async () => {
    render(<ApprovalsPage />);
    const approveButtons = await screen.findAllByRole('button', { name: /Aprobar/ });
    expect(approveButtons).toHaveLength(2);
    // Row order matches the fetch: [#100 by other → enabled, #101 by me → disabled].
    expect(approveButtons[0]).toBeEnabled();
    expect(approveButtons[1]).toBeDisabled();
  });

  it("approves another operator's request via the API", async () => {
    render(<ApprovalsPage />);
    const approveButtons = await screen.findAllByRole('button', { name: /Aprobar/ });
    await userEvent.click(approveButtons[0]);
    await waitFor(() => expect(doorsApi.approveOpenRequest).toHaveBeenCalledWith(100));
  });

  // The door <select> is located by the critical-door option it contains,
  // avoiding accessible-name ambiguity from the wrapping FormField label.
  async function findDoorSelect(): Promise<HTMLSelectElement> {
    return (await waitFor(() => {
      const select = screen
        .getAllByRole('combobox')
        .find((el) => within(el).queryByRole('option', { name: 'Bóveda' }));
      if (!select) throw new Error('door select not rendered yet');
      return select as HTMLSelectElement;
    })) as HTMLSelectElement;
  }

  it('creates a dual-approval request for a critical door', async () => {
    render(<ApprovalsPage />);
    const select = await findDoorSelect();
    await userEvent.selectOptions(select, '1');
    await userEvent.click(screen.getByRole('button', { name: /Solicitar apertura/ }));
    await waitFor(() => expect(doorsApi.requestOpen).toHaveBeenCalledWith(1, null));
  });

  it('offers only critical doors in the request selector', async () => {
    render(<ApprovalsPage />);
    const select = await findDoorSelect();
    const optionLabels = Array.from(select.options).map((o) => o.textContent);
    expect(optionLabels).toContain('Bóveda');
    expect(optionLabels).not.toContain('Recepción');
  });
});
