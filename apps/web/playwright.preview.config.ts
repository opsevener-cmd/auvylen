import {defineConfig} from "@playwright/test";
export default defineConfig({
  testDir: "./preview-tests", workers: 1, retries: 0,
  use: {baseURL: "https://localhost:19443", ignoreHTTPSErrors: true,
    launchOptions: {executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH},
    trace: "off", screenshot: "off", video: "off"},
});
