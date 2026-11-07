import {defineConfig} from "@playwright/test";
import path from "node:path";
// This server creates only temporary SQLite and generated test accounts, never a configured DB.
process.env.E2E_STUDY_FIXTURES = "true";
const root = path.resolve(__dirname, "../..");
export default defineConfig({
  testDir: "./e2e", testMatch: "studies.spec.ts", workers: 1, retries: 0,
  use: {baseURL: "http://127.0.0.1:3148", viewport: {width: 390, height: 844},
    reducedMotion: "reduce", launchOptions: {executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH}, trace: "off", screenshot: "off", video: "off"},
  webServer: [
    {command: "uv run python scripts/serve-study-fixtures.py", cwd: root, url: "http://127.0.0.1:8148/health", reuseExistingServer: false,
      env: {APP_ENV: "test", AUVYLEN_TEST_FIXTURES: "ISOLATED_SQLITE_ONLY", OPENBLAS_NUM_THREADS: "1", OMP_NUM_THREADS: "1"}},
    {command: "npm run start -- --port 3148", url: "http://127.0.0.1:3148", reuseExistingServer: false,
      env: {APP_ENV: "development", API_URL: "http://127.0.0.1:8148"}},
  ],
});
