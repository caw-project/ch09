/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  // Tailwind v4 is a Vite plugin rather than a PostCSS pipeline — no
  // tailwind.config.js and no postcss.config.js; the theme lives in index.css.
  plugins: [react(), tailwindcss()],
  server: {
    // host: true so the dev server is reachable from outside a container.
    host: true,
    port: 5173,
  },
  // Vitest shares this config, so Tailwind and the React plugin behave in tests
  // exactly as they do in the app. See src/test/setup.ts for what every test
  // file gets before it runs.
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
    restoreMocks: true,
    coverage: {
      // Without an include, a source file no test imports is missing from the
      // totals instead of counting as 0% — so the least-tested code is the code
      // the figure never sees.
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/test/**',
        'src/types/**',
        'src/main.tsx',
        'src/**/*.d.ts',
      ],
    },
  },
})
