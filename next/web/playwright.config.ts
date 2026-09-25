import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  outputDir: "../artifacts/browser",
  workers: 1,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: process.env.COASTMAS_NEXT_TEST_URL ?? "http://127.0.0.1:58012",
    // The installed headless-shell exits by itself after ~30s on this host.
    // Full Chromium passed the independent lifetime probe; retain all assertions.
    channel: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 15000,
  },
});
