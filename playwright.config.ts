import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser', workers: 1, fullyParallel: false,
  use: { baseURL: 'http://127.0.0.1:8001', channel: 'msedge', headless: true },
  outputDir: 'data/browser-results', reporter: [['list']],
  webServer: { command: '.venv\\Scripts\\python.exe -m uvicorn backend.qa_server:app --host 127.0.0.1 --port 8001 --no-access-log', url: 'http://127.0.0.1:8001/api/health', reuseExistingServer: false, timeout: 30000 }
});
