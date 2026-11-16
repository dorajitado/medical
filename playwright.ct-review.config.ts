// This server uses isolated known masks and a real queue with a synthetic worker.
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./tests/ct-review',workers:1,fullyParallel:false,timeout:90000,
  use:{baseURL:'http://127.0.0.1:8005',channel:'msedge',headless:true,viewport:{width:1920,height:1080}},
  outputDir:'data/ct-review-browser-results',reporter:[['list']],
  webServer:{command:'.venv\\Scripts\\python.exe -m uvicorn backend.qa_ct_review_server:app --host 127.0.0.1 --port 8005 --no-access-log',url:'http://127.0.0.1:8005/api/health',reuseExistingServer:false,timeout:30000}
});
