import {defineConfig} from "@playwright/test";

export default defineConfig({
  testDir: "./cloud-tests", workers: 1, retries: 0, timeout: 120000,
  use: {baseURL: "https://localhost:18443", ignoreHTTPSErrors: true,
    viewport: {width: 390, height: 844}, channel: process.env.PLAYWRIGHT_CHANNEL,
    launchOptions: {executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH},
    trace: "off", screenshot: "off", video: "off"},
});
