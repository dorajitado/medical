// Deterministic positive fixtures are isolated from real model smoke tests and
// from the user's data. Browser code and endpoints remain the production ones.
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/findings', workers: 1,
  use: { baseURL: 'http://127.0.0.1:8003', channel: 'msedge', headless: true },
  outputDir: 'data/findings-browser-results', reporter: [['list']],
  webServer: {
    command: '.venv\\Scripts\\python.exe -m uvicorn backend.qa_findings_server:app --host 127.0.0.1 --port 8003 --no-access-log',
    url: 'http://127.0.0.1:8003/api/health', reuseExistingServer: false, timeout: 30000,
  },
});
