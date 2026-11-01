import {defineConfig} from "@playwright/test";
// Production UI contract tests without a database/API.
export default defineConfig({
  testDir: "./e2e", testMatch: "native-preview.spec.ts", workers: 1,
  use: {baseURL: "http://127.0.0.1:3108", viewport: {width: 390, height: 844},
    launchOptions: {executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH}},
  webServer: {command: "npm run start -- --port 3108", url: "http://127.0.0.1:3108", reuseExistingServer: false,
    env: {API_URL: "http://127.0.0.1:1"}},
});
