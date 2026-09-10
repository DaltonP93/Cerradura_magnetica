// Registers jest-dom matchers on Vitest's `expect` (runtime) and augments its
// Assertion types (compile time), so `.test.tsx` files can use e.g.
// `toBeInTheDocument()` and `toBeDisabled()`.
import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// With `globals: false` Testing Library cannot auto-register its afterEach, so
// unmount between tests explicitly to keep the jsdom document isolated.
afterEach(() => cleanup());
import '@testing-library/jest-dom/vitest';
