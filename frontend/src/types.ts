// ---- API entity types (mirror backend Pydantic schemas) ----

export type UserRole = 'super_admin' | 'admin' | 'operator' | 'viewer';
export type ControllerStatus = 'online' | 'offline' | 'unknown';
export type DoorMode = 'controlled' | 'normally_open' | 'normally_closed';
export type CredentialType = 'card' | 'pin' | 'card_plus_pin';
export type LeaveType = 'leave' | 'business_trip';
export type SignKind = 'in' | 'out';
export type EventType =
  | 'access_granted'
  | 'access_denied'
  | 'door_opened'
  | 'door_closed'
  | 'door_forced'
  | 'door_held_open'
  | 'remote_open'
  | 'controller_online'
  | 'controller_offline'
  | 'alarm';

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface User {
  id: number;
  organization_id: number | null;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface UserCreate {
  email: string;
  full_name: string;
  password: string;
  role: UserRole;
  organization_id?: number | null;
}

export interface UserUpdate {
  full_name?: string;
  password?: string;
  role?: UserRole;
  is_active?: boolean;
}

export interface Organization {
  id: number;
  name: string;
  slug: string;
  contact_email: string | null;
  plan: string;
  is_active: boolean;
  created_at: string;
}

export interface OrganizationCreate {
  name: string;
  slug: string;
  contact_email?: string | null;
  plan?: string;
}

export interface OrganizationUpdate {
  name?: string;
  contact_email?: string | null;
  plan?: string;
  is_active?: boolean;
}

export interface Site {
  id: number;
  name: string;
  address: string | null;
  timezone: string;
  created_at: string;
}

export interface SiteInput {
  name: string;
  address?: string | null;
  timezone?: string;
}

export interface Door {
  id: number;
  controller_id: number;
  number: number;
  name: string;
  mode: DoorMode;
  open_duration_seconds: number;
  held_open_alarm_seconds: number;
  sensor_enabled: boolean;
  anti_passback: boolean;
  first_card_open: boolean;
  multi_card_count: number;
}

export interface DoorUpdate {
  name?: string;
  mode?: DoorMode;
  open_duration_seconds?: number;
  held_open_alarm_seconds?: number;
  sensor_enabled?: boolean;
  anti_passback?: boolean;
  first_card_open?: boolean;
  multi_card_count?: number;
}

export interface Controller {
  id: number;
  site_id: number | null;
  name: string;
  model: string;
  serial_number: string;
  ip_address: string | null;
  port: number;
  door_count: number;
  firmware_version: string | null;
  status: ControllerStatus;
  last_seen_at: string | null;
  interlock_enabled: boolean;
  created_at: string;
  doors: Door[];
}

export interface ControllerCreate {
  name: string;
  serial_number: string;
  model?: string;
  site_id?: number | null;
  ip_address?: string | null;
  port?: number;
  door_count?: number;
}

export interface ControllerUpdate {
  name?: string;
  site_id?: number | null;
  ip_address?: string | null;
  port?: number;
  interlock_enabled?: boolean;
}

export interface CommandResult {
  success: boolean;
  message: string;
}

export interface Department {
  id: number;
  name: string;
  parent_id: number | null;
  created_at: string;
}

export interface DepartmentInput {
  name: string;
  parent_id?: number | null;
}

export interface Credential {
  id: number;
  cardholder_id: number;
  type: CredentialType;
  card_number: string;
  is_active: boolean;
  created_at: string;
}

export interface CredentialCreate {
  type: CredentialType;
  card_number: string;
  pin?: string | null;
}

export interface Cardholder {
  id: number;
  department_id: number | null;
  shift_id: number | null;
  first_name: string;
  last_name: string;
  employee_number: string | null;
  email: string | null;
  phone: string | null;
  photo_url: string | null;
  valid_from: string | null;
  valid_to: string | null;
  is_active: boolean;
  notes: string | null;
  created_at: string;
  credentials: Credential[];
  access_level_ids: number[];
}

export interface CardholderInput {
  first_name: string;
  last_name: string;
  department_id?: number | null;
  shift_id?: number | null;
  employee_number?: string | null;
  email?: string | null;
  phone?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  is_active?: boolean;
  notes?: string | null;
  access_level_ids?: number[];
}

export interface ScheduleInterval {
  id?: number;
  day_of_week: number; // 0=Monday .. 6=Sunday
  start_time: string; // 'HH:MM:SS'
  end_time: string;
}

export interface Schedule {
  id: number;
  name: string;
  description: string | null;
  allow_on_holidays: boolean;
  created_at: string;
  intervals: ScheduleInterval[];
}

export interface ScheduleInput {
  name: string;
  description?: string | null;
  allow_on_holidays?: boolean;
  intervals?: ScheduleInterval[];
}

export interface Holiday {
  id: number;
  name: string;
  date: string; // YYYY-MM-DD
}

export interface AccessLevelDoorRule {
  id?: number;
  door_id: number;
  schedule_id: number | null; // null = 24/7
}

export interface AccessLevel {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  door_rules: AccessLevelDoorRule[];
}

export interface AccessLevelInput {
  name: string;
  description?: string | null;
  door_rules?: { door_id: number; schedule_id: number | null }[];
}

export interface AccessEvent {
  id: number;
  type: EventType;
  controller_id: number | null;
  door_id: number | null;
  cardholder_id: number | null;
  credential_id: number | null;
  message: string;
  details: Record<string, unknown> | null;
  occurred_at: string;
}

export interface SwipeResult {
  granted: boolean;
  reason: string | null;
  cardholder_id: number | null;
  event_id: number;
}

export interface AuditLog {
  id: number;
  organization_id: number | null;
  user_id: number | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface DashboardStats {
  controllers_total: number;
  controllers_online: number;
  doors_total: number;
  cardholders_total: number;
  cardholders_active: number;
  events_today: number;
  access_granted_today: number;
  access_denied_today: number;
  alarms_today: number;
  recent_events: AccessEvent[];
}

// ---- Attendance ----
export interface Shift {
  id: number;
  name: string;
  start_time: string; // 'HH:MM:SS'
  end_time: string;
  late_tolerance_minutes: number;
  early_leave_tolerance_minutes: number;
  days_of_week: number[]; // 0=Monday .. 6=Sunday
  created_at: string;
}

export interface ShiftInput {
  name: string;
  start_time: string; // 'HH:MM:SS'
  end_time: string;
  late_tolerance_minutes?: number;
  early_leave_tolerance_minutes?: number;
  days_of_week?: number[];
}

export interface Leave {
  id: number;
  cardholder_id: number;
  type: LeaveType;
  date_from: string; // YYYY-MM-DD
  date_to: string;
  reason: string | null;
  created_at: string;
}

export interface LeaveInput {
  cardholder_id: number;
  type: LeaveType;
  date_from: string;
  date_to: string;
  reason?: string | null;
}

export interface ManualSign {
  id: number;
  cardholder_id: number;
  kind: SignKind;
  signed_at: string;
  note: string | null;
  created_at: string;
}

export interface ManualSignInput {
  cardholder_id: number;
  kind: SignKind;
  signed_at: string; // ISO datetime
  note?: string | null;
}

export type AttendanceStatus =
  | 'present'
  | 'late'
  | 'early_leave'
  | 'incomplete'
  | 'absent'
  | 'leave'
  | 'business_trip'
  | 'holiday'
  | 'rest_day';

export interface AttendanceRow {
  cardholder_id: number;
  cardholder_name: string;
  department: string | null;
  date: string; // YYYY-MM-DD
  check_in: string | null;
  check_out: string | null;
  statuses: string[];
}

export interface AttendanceSummary {
  days: number;
  present: number;
  late: number;
  early_leave: number;
  absent: number;
  on_leave: number;
  incomplete: number;
}

export interface AttendanceReport {
  date_from: string;
  date_to: string;
  rows: AttendanceRow[];
  summary: AttendanceSummary;
}

// ---- Bulk import ----
export interface ImportResult {
  created: number;
  errors: { row?: number | string; reason?: string; [key: string]: unknown }[];
}

// Live event pushed over the WebSocket
export interface LiveEvent {
  kind: 'event';
  id: number;
  type: EventType;
  message: string;
  occurred_at: string;
  controller_id?: number | null;
  door_id?: number | null;
  cardholder_id?: number | null;
  [key: string]: unknown;
}
