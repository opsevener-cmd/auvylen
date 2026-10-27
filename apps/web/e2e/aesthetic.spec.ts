import {test, expect, type Page} from "@playwright/test";
import {execFileSync, spawn} from "node:child_process";
import path from "node:path";
import {aestheticEnv} from "../playwright.config";

test.use({trace: "off", screenshot: "off", video: "off"});
const root = path.resolve(__dirname, "../../..");

async function captureReview(page: Page, filename: string) {
  if (!process.env.AUVYLEN_VISUAL_OUTPUT_DIR) return;
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.querySelectorAll<HTMLImageElement>(".editorial-portrait img")].map(image => image.decode()));
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    window.scrollTo({top: 0, behavior: "instant"});
  });
  await page.screenshot({path: path.join(process.env.AUVYLEN_VISUAL_OUTPUT_DIR, filename), fullPage: true,
    style: ".site-header {position: static !important;}"});
}

async function researchAccount(page: Page, name: string) {
  await page.goto("/register");
  await page.getByLabel("Username or email-like identifier").fill(`${name}-${Date.now()}`);
  await page.getByLabel("Password", {exact: true}).fill("test-only-aesthetic-browser-password");
  await page.getByRole("button", {name: "Create account", exact: true}).click();
  await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
  const account = await page.request.get("/api/v1/auth/me").then(r => r.json());
  execFileSync("uv", ["run", "python", "-m", "aevyra_api.research.operator", "grant", account.user.public_user_id, "--reason", "Aesthetic browser test"], {cwd: root, stdio: "pipe"});
}

test("aesthetic analysis stays unavailable without a validated model", async ({page}) => {
  test.skip(process.env.E2E_RESEARCH !== "true", "Requires explicit private research test mode");
  test.skip(!!process.env.E2E_AESTHETIC_SHA256, "Server configured with the synthetic test checkpoint");
  await researchAccount(page, "aesthetic-unavailable");
  await page.goto("/research/aesthetic");
  await expect(page.getByText("Aesthetic scoring is not available yet", {exact: true})).toBeVisible();
  await expect(page.getByRole("button", {name: "Analyze photograph"})).toHaveCount(0);
  await expect(page.getByText("/ 10")).toHaveCount(0);
  await page.getByRole("button", {name: "中文", exact: true}).click();
  await expect(page.getByText("审美评分暂不可用", {exact: true})).toBeVisible();
});

test("synthetic test checkpoint: upload, score, distribution, bilingual display and deletion", async ({page}) => {
  test.skip(process.env.E2E_RESEARCH !== "true" || !process.env.E2E_AESTHETIC_SHA256, "Requires research mode and the synthetic test checkpoint");
  test.setTimeout(90000);
  await researchAccount(page, "aesthetic-browser");
  const encoded = execFileSync("uv", ["run", "python", "-c", "import base64,numpy as n; from PIL import Image; from io import BytesIO; b=BytesIO(); Image.fromarray(n.linspace(0,255,320*400*3).reshape(400,320,3).astype('uint8')).save(b,'PNG'); print(base64.b64encode(b.getvalue()).decode())"], {cwd: root, encoding: "utf8"}).trim();
  await page.goto("/research/aesthetic");
  await expect(page.getByText("This installed model was trained on generated test data", {exact: false})).toBeVisible();
  await expect(page.getByText("No photograph selected", {exact: true})).toBeVisible();
  await page.getByLabel("Photograph of one adult").focus();
  await expect(page.getByLabel("Photograph of one adult")).toBeFocused();
  await expect(page.locator(".analysis-file-picker-row .button-secondary")).toHaveCSS("outline-style", "solid");
  await page.getByLabel("Photograph of one adult").setInputFiles({name: "fixture.png", mimeType: "image/png", buffer: Buffer.from(encoded, "base64")});
  await expect(page.getByText("fixture.png", {exact: true})).toBeVisible();
  await page.getByLabel("The photograph shows exactly one person", {exact: false}).check();
  await page.getByLabel("I have the person's permission", {exact: false}).check();
  await page.getByLabel("I understand the score reflects", {exact: false}).check();
  await page.getByRole("button", {name: "Analyze photograph", exact: true}).click();
  await expect(page.getByText("Queued for analysis.", {exact: true})).toBeVisible();
  const worker = spawn(path.join(root, ".venv/bin/python"), ["-m", "aevyra_api.research.worker"], {cwd: root,
    env: {...process.env, ...aestheticEnv, RESEARCH_MODE: "true", PRIVATE_UPLOAD_ROOT: path.join(root, "private-data/e2e-uploads"), PRIVATE_MODEL_ROOT: path.join(root, "private-data/e2e-models"), OPENBLAS_NUM_THREADS: "1"}, stdio: "ignore"});
  try {
    await expect(page.getByText("/ 10", {exact: true})).toBeVisible({timeout: 30000});
    await expect(page.getByText("Synthetic test model: this number comes from a model trained on generated data", {exact: false})).toBeVisible();
    await expect(page.getByText("Predicted rating distribution (annotator scale 1–5)", {exact: true})).toBeVisible();
    await expect(page.locator(".distribution-row")).toHaveCount(5);
    await expect(page.getByText("synthetic-e2e-v1+split-conformal-90", {exact: true})).toBeVisible();
    await page.getByRole("button", {name: "中文", exact: true}).click();
    await expect(page.getByText("选择照片", {exact: true})).toBeVisible();
    await expect(page.getByText("fixture.png", {exact: true})).toBeVisible();
    await expect(page.getByText("预测评分分布（标注者 1–5 分量表）", {exact: true})).toBeVisible();
    await expect(page.getByText("由您的声明确认；系统不进行年龄估计，也不进行自动人脸检测。", {exact: true})).toBeVisible();
    await captureReview(page, "result-mobile-zh.png");
    await page.getByRole("button", {name: "English", exact: true}).click();
    if (process.env.AUVYLEN_VISUAL_OUTPUT_DIR) {
      await page.setViewportSize({width: 1440, height: 1000});
      await captureReview(page, "result-desktop-en.png");
    }
    page.once("dialog", dialog => void dialog.accept());
    await page.getByRole("button", {name: "Delete analysis", exact: true}).click();
    await expect(page.getByRole("button", {name: "Delete analysis", exact: true})).toHaveCount(0);
    await page.reload();
    await expect(page.getByText("/ 10", {exact: true})).toHaveCount(0);
  } finally {worker.kill("SIGTERM");}
});
