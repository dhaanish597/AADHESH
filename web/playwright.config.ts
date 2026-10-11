import { defineConfig } from "@playwright/test";

/**
 * Browser-level end-to-end configuration.
 *
 * The point of this suite is to drive the REAL application: the deterministic resolver, the
 * acknowledgement token service, the Cedar authorizer and the consent store, all through the
 * local HTTP API the Next.js app proxies to. Nothing here is a mock.
 *
 * `channel: "chrome"` uses the Chrome already installed on the machine, so the suite does not
 * need to download a bundled browser. Run it with `npm run e2e` from `web/`.
 */
const WEB_PORT = process.env.AADESH_E2E_WEB_PORT ?? "3100";
const API_PORT = process.env.AADESH_API_PORT ?? "8787";
const API_URL = `http://127.0.0.1:${API_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts$/,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    channel: "chrome",
    headless: true,
    trace: "off",
  },
  webServer: [
    {
      command: "node e2e/api-server.mjs",
      url: `${API_URL}/api/health`,
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      // Production build served by `next start`, proxying /api/* to the local API.
      command: `npx next start -p ${WEB_PORT}`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: true,
      timeout: 120_000,
      env: { AADESH_API_URL: API_URL },
    },
  ],
});
