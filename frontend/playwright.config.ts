import { defineConfig } from '@playwright/test'
const baseURL = `http://127.0.0.1:${process.env.E2E_PORT || '18000'}`
export default defineConfig({
  testDir: './tests',
  workers: 1,
  timeout: 60000,
  use: { baseURL, trace: 'retain-on-failure' },
  webServer: {
    command: process.env.E2E_PYTHON
      ? `"${process.env.E2E_PYTHON}" ../scripts/e2e_server.py`
      : 'python ../scripts/e2e_server.py',
    url: `${baseURL}/health`,
    reuseExistingServer: false,
    timeout: 30000,
  },
})
