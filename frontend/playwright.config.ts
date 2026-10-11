import { defineConfig } from "@playwright/test";

/**
 * End to end tests drive a real browser against the dev server and a running API with the demo
 * data loaded (see the README). `E2E_BROWSER=chrome` or `msedge` uses a browser that is already
 * installed, so nothing needs downloading.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    channel: process.env.E2E_BROWSER ?? "msedge",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
