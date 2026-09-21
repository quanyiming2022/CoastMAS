import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  outputDir: "../../artifacts/runtime/playwright",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "line",
  use: {
    actionTimeout: 15000,
    navigationTimeout: 15000,
    baseURL: process.env.COASTMAS_E2E_URL,
    browserName: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
