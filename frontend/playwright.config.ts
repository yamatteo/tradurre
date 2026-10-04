import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from '@playwright/test'

// E2E runs on its own servers: a backend on :8001 with a throwaway database (never the user's
// ~/.tradurre/tradurre.db) and Vite on :5174 proxying /api to it.
const E2E_DB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '.e2e.db')

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:5174',
    headless: true,
    // The full Chromium in headless mode: the separate headless-shell build is not needed.
    channel: 'chromium',
  },
  // The timing tests (e2e/scale.spec.ts) run last, alone: after every other test, so nothing shares the backend.
  projects: [
    { name: 'e2e', testIgnore: /scale\.spec\.ts/ },
    { name: 'scale', testMatch: /scale\.spec\.ts/, dependencies: ['e2e'] },
  ],
  webServer: [
    {
      command: 'rm -f ../.e2e.db ../.e2e.db-wal ../.e2e.db-shm && uv run uvicorn tradurre.app:app --port 8001',
      env: { TRADURRE_DB: E2E_DB },
      url: 'http://127.0.0.1:8001/api/v2/books',
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: 'npx vite --port 5174 --strictPort',
      env: { TRADURRE_API: 'http://127.0.0.1:8001' },
      url: 'http://localhost:5174',
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
})
