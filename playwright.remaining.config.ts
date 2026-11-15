// Synthetic workflow server is isolated from both production and real-model QA.
import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests/remaining',workers:1,fullyParallel:false,timeout:60000,
  use:{baseURL:'http://127.0.0.1:8004',channel:'msedge',headless:true,viewport:{width:1920,height:1080}},
  outputDir:'data/remaining-browser-results',reporter:[['list']],
  webServer:{command:'.venv\\Scripts\\python.exe -m uvicorn backend.qa_remaining_server:app --host 127.0.0.1 --port 8004 --no-access-log',url:'http://127.0.0.1:8004/api/health',reuseExistingServer:false,timeout:30000}});
