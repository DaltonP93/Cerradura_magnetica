import { api } from './client';
import type {
  AccessEvent,
  AccessLevel,
  AccessLevelInput,
  AttendanceReport,
  AuditLog,
  Cardholder,
  CardholderInput,
  CommandResult,
  Controller,
  ControllerCreate,
  ControllerUpdate,
  Credential,
  CredentialCreate,
  DashboardStats,
  Department,
  DepartmentInput,
  Door,
  DoorUpdate,
  EventType,
  Holiday,
  ImportResult,
  Leave,
  LeaveInput,
  ManualSign,
  ManualSignInput,
  Organization,
  OrganizationCreate,
  OrganizationUpdate,
  Page,
  Schedule,
  ScheduleInput,
  Shift,
  ShiftInput,
  Site,
  SiteInput,
  SwipeResult,
  TokenPair,
  User,
  UserCreate,
  UserUpdate,
} from '../types';

// ---- auth ----
// Login/refresh set HttpOnly cookies server-side; the returned token body is
// ignored by the SPA (kept in the type for programmatic clients).
export const authApi = {
  login: (email: string, password: string) =>
    api.post<TokenPair>('/auth/login', { email, password }).then((r) => r.data),
  refresh: () => api.post<TokenPair>('/auth/refresh', {}).then((r) => r.data),
  logout: () => api.post<{ detail: string }>('/auth/logout').then((r) => r.data),
  me: () => api.get<User>('/auth/me').then((r) => r.data),
  changePassword: (current_password: string, new_password: string) =>
    api.post<{ detail: string }>('/auth/change-password', { current_password, new_password }).then((r) => r.data),
};

// ---- dashboard ----
export const dashboardApi = {
  get: () => api.get<DashboardStats>('/dashboard').then((r) => r.data),
};

// ---- organizations ----
export const organizationsApi = {
  list: (params?: { q?: string; limit?: number; offset?: number }) =>
    api.get<Page<Organization>>('/organizations', { params }).then((r) => r.data),
  create: (body: OrganizationCreate) => api.post<Organization>('/organizations', body).then((r) => r.data),
  update: (id: number, body: OrganizationUpdate) =>
    api.patch<Organization>(`/organizations/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete<{ detail: string }>(`/organizations/${id}`).then((r) => r.data),
};

// ---- users ----
export const usersApi = {
  list: (params?: { q?: string; limit?: number; offset?: number }) =>
    api.get<Page<User>>('/users', { params }).then((r) => r.data),
  create: (body: UserCreate) => api.post<User>('/users', body).then((r) => r.data),
  update: (id: number, body: UserUpdate) => api.patch<User>(`/users/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete<{ detail: string }>(`/users/${id}`).then((r) => r.data),
};

// ---- sites ----
export const sitesApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get<Page<Site>>('/sites', { params }).then((r) => r.data),
  create: (body: SiteInput) => api.post<Site>('/sites', body).then((r) => r.data),
  update: (id: number, body: Partial<SiteInput>) => api.patch<Site>(`/sites/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete<{ detail: string }>(`/sites/${id}`).then((r) => r.data),
};

// ---- controllers ----
export const controllersApi = {
  list: (params?: { q?: string; site_id?: number; limit?: number; offset?: number }) =>
    api.get<Page<Controller>>('/controllers', { params }).then((r) => r.data),
  get: (id: number) => api.get<Controller>(`/controllers/${id}`).then((r) => r.data),
  create: (body: ControllerCreate) => api.post<Controller>('/controllers', body).then((r) => r.data),
  update: (id: number, body: ControllerUpdate) =>
    api.patch<Controller>(`/controllers/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete<{ detail: string }>(`/controllers/${id}`).then((r) => r.data),
  ping: (id: number) => api.post<CommandResult>(`/controllers/${id}/ping`).then((r) => r.data),
  syncTime: (id: number) => api.post<CommandResult>(`/controllers/${id}/sync-time`).then((r) => r.data),
  syncPermissions: (id: number) =>
    api.post<CommandResult>(`/controllers/${id}/sync-permissions`).then((r) => r.data),
};

// ---- doors ----
export const doorsApi = {
  list: (params?: { controller_id?: number; limit?: number; offset?: number }) =>
    api.get<Page<Door>>('/doors', { params }).then((r) => r.data),
  update: (id: number, body: DoorUpdate) => api.patch<Door>(`/doors/${id}`, body).then((r) => r.data),
  open: (id: number) => api.post<CommandResult>(`/doors/${id}/open`).then((r) => r.data),
};

// ---- departments ----
export const departmentsApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get<Page<Department>>('/departments', { params }).then((r) => r.data),
  create: (body: DepartmentInput) => api.post<Department>('/departments', body).then((r) => r.data),
  update: (id: number, body: Partial<DepartmentInput>) =>
    api.patch<Department>(`/departments/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete<{ detail: string }>(`/departments/${id}`).then((r) => r.data),
};

// ---- cardholders ----
export const cardholdersApi = {
  list: (params?: {
    q?: string;
    department_id?: number;
    is_active?: boolean;
    limit?: number;
    offset?: number;
  }) => api.get<Page<Cardholder>>('/cardholders', { params }).then((r) => r.data),
  get: (id: number) => api.get<Cardholder>(`/cardholders/${id}`).then((r) => r.data),
  create: (body: CardholderInput) => api.post<Cardholder>('/cardholders', body).then((r) => r.data),
  update: (id: number, body: Partial<CardholderInput>) =>
    api.patch<Cardholder>(`/cardholders/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete<{ detail: string }>(`/cardholders/${id}`).then((r) => r.data),
  addCredential: (cardholderId: number, body: CredentialCreate) =>
    api.post<Credential>(`/cardholders/${cardholderId}/credentials`, body).then((r) => r.data),
  updateCredential: (cardholderId: number, credentialId: number, body: { is_active?: boolean; pin?: string }) =>
    api
      .patch<Credential>(`/cardholders/${cardholderId}/credentials/${credentialId}`, body)
      .then((r) => r.data),
  removeCredential: (cardholderId: number, credentialId: number) =>
    api
      .delete<{ detail: string }>(`/cardholders/${cardholderId}/credentials/${credentialId}`)
      .then((r) => r.data),
  importCsv: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.post<ImportResult>('/cardholders/import', form).then((r) => r.data);
  },
  importMdb: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.post<ImportResult>('/cardholders/import-mdb', form).then((r) => r.data);
  },
};

// ---- attendance ----
export const attendanceApi = {
  listShifts: (params?: { limit?: number; offset?: number }) =>
    api.get<Page<Shift>>('/attendance/shifts', { params }).then((r) => r.data),
  createShift: (body: ShiftInput) => api.post<Shift>('/attendance/shifts', body).then((r) => r.data),
  updateShift: (id: number, body: Partial<ShiftInput>) =>
    api.patch<Shift>(`/attendance/shifts/${id}`, body).then((r) => r.data),
  removeShift: (id: number) => api.delete<{ detail: string }>(`/attendance/shifts/${id}`).then((r) => r.data),

  listLeaves: (params?: { cardholder_id?: number; limit?: number; offset?: number }) =>
    api.get<Page<Leave>>('/attendance/leaves', { params }).then((r) => r.data),
  createLeave: (body: LeaveInput) => api.post<Leave>('/attendance/leaves', body).then((r) => r.data),
  removeLeave: (id: number) => api.delete<{ detail: string }>(`/attendance/leaves/${id}`).then((r) => r.data),

  listManualSigns: (params?: { cardholder_id?: number; limit?: number; offset?: number }) =>
    api.get<Page<ManualSign>>('/attendance/manual-signs', { params }).then((r) => r.data),
  createManualSign: (body: ManualSignInput) =>
    api.post<ManualSign>('/attendance/manual-signs', body).then((r) => r.data),
  removeManualSign: (id: number) =>
    api.delete<{ detail: string }>(`/attendance/manual-signs/${id}`).then((r) => r.data),

  report: (params: { date_from: string; date_to: string; department_id?: number; cardholder_id?: number }) =>
    api.get<AttendanceReport>('/attendance/report', { params }).then((r) => r.data),
};

// ---- schedules & holidays ----
export const schedulesApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get<Page<Schedule>>('/schedules', { params }).then((r) => r.data),
  create: (body: ScheduleInput) => api.post<Schedule>('/schedules', body).then((r) => r.data),
  update: (id: number, body: Partial<ScheduleInput>) =>
    api.patch<Schedule>(`/schedules/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete<{ detail: string }>(`/schedules/${id}`).then((r) => r.data),
};

export const holidaysApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get<Page<Holiday>>('/holidays', { params }).then((r) => r.data),
  create: (body: { name: string; date: string }) => api.post<Holiday>('/holidays', body).then((r) => r.data),
  remove: (id: number) => api.delete<{ detail: string }>(`/holidays/${id}`).then((r) => r.data),
};

// ---- access levels ----
export const accessLevelsApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get<Page<AccessLevel>>('/access-levels', { params }).then((r) => r.data),
  create: (body: AccessLevelInput) => api.post<AccessLevel>('/access-levels', body).then((r) => r.data),
  update: (id: number, body: Partial<AccessLevelInput>) =>
    api.patch<AccessLevel>(`/access-levels/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete<{ detail: string }>(`/access-levels/${id}`).then((r) => r.data),
};

// ---- events ----
export interface EventFilters {
  type?: EventType;
  door_id?: number;
  controller_id?: number;
  cardholder_id?: number;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export const eventsApi = {
  list: (params?: EventFilters) => api.get<Page<AccessEvent>>('/events', { params }).then((r) => r.data),
  swipe: (body: { door_id: number; card_number: string; pin?: string | null }) =>
    api.post<SwipeResult>('/events/swipe', body).then((r) => r.data),
};

// ---- audit logs ----
export const auditApi = {
  list: (params?: {
    user_id?: number;
    action?: string;
    resource_type?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    offset?: number;
  }) => api.get<Page<AuditLog>>('/audit-logs', { params }).then((r) => r.data),
};
