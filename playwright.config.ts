import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir:'./tests/e2e',
  fullyParallel:false,
  workers:1,
  use:{ baseURL:'http://admin.localhost:4201', trace:'retain-on-failure', screenshot:'only-on-failure' },
  projects:[{name:'chromium',use:{...devices['Desktop Chrome']}}],
});
