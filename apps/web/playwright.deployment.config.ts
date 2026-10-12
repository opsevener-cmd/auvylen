import {defineConfig} from "@playwright/test";

const baseURL = process.env.AEVYRA_TEST_URL ?? "https://localhost:8443";
if (new URL(baseURL).hostname !== "localhost") {
  throw new Error("Deployment browser tests are restricted to the local TLS simulation");
}
export default defineConfig({
  testDir: "./deployment-tests", workers: 1, retries: 0,
  use: {
    baseURL, ignoreHTTPSErrors: true, viewport: {width: 390, height: 844},
    channel: process.env.PLAYWRIGHT_CHANNEL, trace: "retain-on-failure",
  },
});
