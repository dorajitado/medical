// Optional integration suite: requires the explicitly downloaded public sample
// and a completed backend.qa_week3 smoke test. It never opens production data.
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/analysis', workers: 1,
  use: { baseURL: 'http://127.0.0.1:8002', channel: 'msedge', headless: true },
  outputDir: 'data/analysis-browser-results', reporter: [['list']],
  webServer: {
    command: '.venv\\Scripts\\python.exe -m uvicorn backend.qa_analysis_server:app --host 127.0.0.1 --port 8002 --no-access-log',
    url: 'http://127.0.0.1:8002/api/health', reuseExistingServer: false, timeout: 30000,
  },
});
