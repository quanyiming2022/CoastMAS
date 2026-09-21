import { defineConfig } from "@playwright/test";
import base from "./playwright.config";
// Explicit live maintenance acceptance; ordinary E2E must not archive user workspaces.
export default defineConfig({
  ...base,
  testDir: "./acceptance",
  retries: 0,
  use: { ...base.use, baseURL: "http://127.0.0.1:58000" },
});
