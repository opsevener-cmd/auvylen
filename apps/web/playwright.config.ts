import {defineConfig} from "@playwright/test";
import path from "node:path";

const root = path.resolve(__dirname, "../..");
const apiPort = process.env.E2E_API_PORT ?? "8000";
const webPort = process.env.E2E_WEB_PORT ?? "3000";
const apiUrl = `http://127.0.0.1:${apiPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: "./e2e", workers: 1, retries: 0,
  use: {baseURL: webUrl, viewport: {width: 390, height: 844}, channel: process.env.PLAYWRIGHT_CHANNEL,
    launchOptions: {executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH}, trace: "retain-on-failure"},
  webServer: [
    {command: `uv run uvicorn aevyra_api.main:app --host 127.0.0.1 --port ${apiPort} --no-access-log`,
      env: {CORS_ORIGINS: JSON.stringify([webUrl]), RESEARCH_MODE: process.env.E2E_RESEARCH ?? "false",
        PRIVATE_UPLOAD_ROOT: path.join(root, "private-data/e2e-uploads")},
      cwd: root, url: `${apiUrl}/health`, reuseExistingServer: !process.env.CI},
    {command: `npm run start --workspace @auvylen/web -- --port ${webPort}`, cwd: root,
      url: webUrl, env: {API_URL: apiUrl}, reuseExistingServer: !process.env.CI},
  ],
});
