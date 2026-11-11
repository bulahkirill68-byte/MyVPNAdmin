import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests',
  workers: 1,
  timeout: 60000,
  use: { baseURL: 'http://127.0.0.1:8000', trace: 'retain-on-failure' },
  webServer: {
    command: process.env.E2E_PYTHON
      ? `"${process.env.E2E_PYTHON}" ../scripts/e2e_server.py`
      : 'python ../scripts/e2e_server.py',
    url: 'http://127.0.0.1:8000/health',
    reuseExistingServer: false,
    timeout: 30000,
  },
})
