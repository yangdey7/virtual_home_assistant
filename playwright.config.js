import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  timeout: 30000,
  use: {
    baseURL: 'http://127.0.0.1:5035',
    browserName: 'chromium',
    viewport: { width: 1440, height: 1100 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'python -m tests.browser_server',
    url: 'http://127.0.0.1:5035/api/health',
    reuseExistingServer: false,
    timeout: 20000,
  },
});
