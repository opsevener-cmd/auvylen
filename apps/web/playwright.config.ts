import {defineConfig} from "@playwright/test";
import path from "node:path";

const root = path.resolve(__dirname, "../..");
const apiPort = process.env.E2E_API_PORT ?? "8000";
const webPort = process.env.E2E_WEB_PORT ?? "3000";
const apiUrl = `http://127.0.0.1:${apiPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
// Synthetic generated-data checkpoint for browser tests only (scripts/create-test-aesthetic-checkpoint.py).
export const aestheticEnv: Record<string, string> = process.env.E2E_AESTHETIC_SHA256 ? {
  AESTHETIC_SCORING_ENABLED: "true", AESTHETIC_MODEL_VERSION: process.env.E2E_AESTHETIC_VERSION ?? "synthetic-e2e-v1",
  AESTHETIC_MANIFEST_SHA256: process.env.E2E_AESTHETIC_SHA256, AESTHETIC_ALLOW_SYNTHETIC_TEST_CHECKPOINT: "true",
} : {};

export default defineConfig({
  testDir: "./e2e", workers: 1, retries: 0,
  use: {baseURL: webUrl, viewport: {width: 390, height: 844}, channel: process.env.PLAYWRIGHT_CHANNEL,
    launchOptions: {executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH}, trace: "retain-on-failure"},
  webServer: [
    {command: `uv run uvicorn aevyra_api.main:app --host 127.0.0.1 --port ${apiPort} --no-access-log`,
      env: {CORS_ORIGINS: JSON.stringify([webUrl]), SHARED_PROXY_RATE_LIMITS: "true", RESEARCH_MODE: process.env.E2E_RESEARCH ?? "false",
        PRIVATE_UPLOAD_ROOT: path.join(root, "private-data/e2e-uploads"),
        PRIVATE_MODEL_ROOT: path.join(root, "private-data/e2e-models"), ...aestheticEnv},
      cwd: root, url: `${apiUrl}/health`, reuseExistingServer: !process.env.CI},
    {command: `npm run start --workspace @auvylen/web -- --port ${webPort}`, cwd: root,
      url: webUrl, env: {API_URL: apiUrl}, reuseExistingServer: !process.env.CI},
  ],
});
