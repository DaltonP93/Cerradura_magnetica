import type { CredentialType, DoorMode, EventType, UserRole } from '../types';

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export const EVENT_TYPE_LABELS: Record<EventType, string> = {
  access_granted: 'Acceso concedido',
  access_denied: 'Acceso denegado',
  door_opened: 'Puerta abierta',
  door_closed: 'Puerta cerrada',
  door_forced: 'Puerta forzada',
  door_held_open: 'Puerta retenida abierta',
  remote_open: 'Apertura remota',
  controller_online: 'Controlador en línea',
  controller_offline: 'Controlador fuera de línea',
  alarm: 'Alarma',
};

export const EVENT_TYPES: EventType[] = Object.keys(EVENT_TYPE_LABELS) as EventType[];

export type EventTone = 'granted' | 'denied' | 'alarm' | 'other';

export function eventTone(type: EventType): EventTone {
  switch (type) {
    case 'access_granted':
    case 'remote_open':
      return 'granted';
    case 'access_denied':
      return 'denied';
    case 'alarm':
    case 'door_forced':
    case 'door_held_open':
      return 'alarm';
    default:
      return 'other';
  }
}

export const ROLE_LABELS: Record<UserRole, string> = {
  super_admin: 'Súper administrador',
  admin: 'Administrador',
  operator: 'Operador',
  viewer: 'Visualizador',
};

export const DOOR_MODE_LABELS: Record<DoorMode, string> = {
  controlled: 'Controlada',
  normally_open: 'Siempre abierta',
  normally_closed: 'Siempre cerrada',
};

export const CREDENTIAL_TYPE_LABELS: Record<CredentialType, string> = {
  card: 'Tarjeta',
  pin: 'PIN',
  card_plus_pin: 'Tarjeta + PIN',
};

export const DENIED_REASON_LABELS: Record<string, string> = {
  unknown_credential: 'Credencial desconocida',
  credential_inactive: 'Credencial inactiva',
  cardholder_inactive: 'Persona inactiva',
  out_of_validity: 'Fuera del período de validez',
  no_access_level: 'Sin nivel de acceso',
  out_of_schedule: 'Fuera de horario',
  holiday: 'Día festivo',
  wrong_pin: 'PIN incorrecto',
  door_locked: 'Puerta bloqueada',
};

export const DAY_LABELS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

/** 'HH:MM:SS' -> 'HH:MM' for display / time inputs. */
export function toHHMM(t: string): string {
  return t.slice(0, 5);
}

/** 'HH:MM' -> 'HH:MM:SS' for the API. */
export function toHHMMSS(t: string): string {
  return t.length === 5 ? `${t}:00` : t;
}

/** Export rows to a CSV file (client-side download). */
export function exportCsv(filename: string, headers: string[], rows: (string | number | null | undefined)[][]): void {
  const escape = (v: string | number | null | undefined): string => {
    const s = v == null ? '' : String(v);
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const content = [headers, ...rows].map((row) => row.map(escape).join(',')).join('\n');
  const blob = new Blob([`﻿${content}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
