import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Component tests run under jsdom. Kept separate from vite.config.ts so the dev
// server / build config stays untouched.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
});
