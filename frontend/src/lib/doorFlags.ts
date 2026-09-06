// Advisory helpers for the advanced door flags.
//
// IMPORTANT: anti-passback, interlock, first-card-open and multi-card are STORED
// as configuration but the platform's access engine does NOT enforce them yet
// (see backend/app/services/access_engine.py — the flags are not referenced).
// Enforcement requires the real hardware adapter and live per-door state; on the
// simulated gateway they have no physical effect. The UI must therefore never
// present them as active protections. Flip ADVANCED_FLAGS_ENFORCED to true only
// when the access engine actually applies them.
export const ADVANCED_FLAGS_ENFORCED = false;

export interface DoorAdvancedFlags {
  anti_passback: boolean;
  first_card_open: boolean;
  multi_card_count: number;
}

export interface FlagBadge {
  key: string;
  label: string;
}

/** The advanced flags that are switched on for a door (before advisory labeling). */
export function activeAdvancedFlags(d: DoorAdvancedFlags): FlagBadge[] {
  const out: FlagBadge[] = [];
  if (d.anti_passback) out.push({ key: 'anti_passback', label: 'Anti-passback' });
  if (d.first_card_open) out.push({ key: 'first_card_open', label: '1ª tarjeta' });
  if (d.multi_card_count > 1) out.push({ key: 'multi_card', label: `${d.multi_card_count} tarjetas` });
  return out;
}

/** Appends a "no aplicado" marker while enforcement is not implemented. */
export function flagBadgeLabel(label: string): string {
  return ADVANCED_FLAGS_ENFORCED ? label : `${label} · no aplicado`;
}

/** Human-readable advisory shown next to the advanced-flag controls. */
export const ADVANCED_FLAGS_NOTICE =
  'Los controles avanzados (anti-passback, interlock, apertura con primera tarjeta y ' +
  'multi-tarjeta) se guardan como configuración pero la plataforma todavía NO los aplica: ' +
  'requieren el adaptador de hardware real, estado en tiempo real y una placa compatible. ' +
  'En modo simulado no tienen efecto físico — no dependas de ellos como control de seguridad.';
