import { describe, expect, it } from 'vitest';

import {
  ADVANCED_FLAGS_ENFORCED,
  ADVANCED_FLAGS_NOTICE,
  activeAdvancedFlags,
  flagBadgeLabel,
} from './doorFlags';

describe('advanced door flags advisory', () => {
  it('the platform does not enforce the advanced flags yet', () => {
    // If this ever flips to true, the "no aplicado" labeling must be revisited.
    expect(ADVANCED_FLAGS_ENFORCED).toBe(false);
  });

  it('lists only the flags that are switched on', () => {
    expect(activeAdvancedFlags({ anti_passback: false, first_card_open: false, multi_card_count: 1 })).toEqual([]);
    const all = activeAdvancedFlags({ anti_passback: true, first_card_open: true, multi_card_count: 3 });
    expect(all.map((f) => f.key)).toEqual(['anti_passback', 'first_card_open', 'multi_card']);
    expect(all.find((f) => f.key === 'multi_card')?.label).toBe('3 tarjetas');
  });

  it('multi_card_count of 1 means disabled (no badge)', () => {
    expect(activeAdvancedFlags({ anti_passback: false, first_card_open: false, multi_card_count: 1 })).toEqual([]);
  });

  it('marks badge labels as not applied while enforcement is off', () => {
    expect(flagBadgeLabel('Anti-passback')).toBe('Anti-passback · no aplicado');
  });

  it('the notice names the four advanced controls and warns against relying on them', () => {
    for (const term of ['anti-passback', 'interlock', 'primera tarjeta', 'multi-tarjeta']) {
      expect(ADVANCED_FLAGS_NOTICE.toLowerCase()).toContain(term);
    }
    expect(ADVANCED_FLAGS_NOTICE.toLowerCase()).toContain('todavía no los aplica');
  });
});
