import {test, expect} from "@playwright/test";
import {execFileSync, spawn} from "node:child_process";
import path from "node:path";

test.use({trace: "off", screenshot: "off", video: "off"});
for (const extractor of process.env.E2E_PRETRAINED === "true" ? ["rgb-grid-texture-v1", "mobilenetv3-small-imagenet-onnx-v1"] : ["rgb-grid-texture-v1"]) {
test(`train ratings, predict unseen upload and retrain a persisted model version (${extractor})`, async ({page}) => {
  test.skip(process.env.E2E_RESEARCH !== "true", "Requires explicit private research test mode");
  test.setTimeout(90000);
  const root = path.resolve(__dirname, "../../..");
  const worker = spawn(path.join(root, ".venv/bin/python"), ["-m", "aevyra_api.research.worker"], {cwd: root,
    env: {...process.env, RESEARCH_MODE: "true", PRIVATE_UPLOAD_ROOT: path.join(root, "private-data/e2e-uploads"), PRIVATE_MODEL_ROOT: path.join(root, "private-data/e2e-models"), OPENBLAS_NUM_THREADS: "1"}, stdio: "ignore"});
  try {
    await page.goto("/register");
    await page.getByLabel("Username or email-like identifier").fill(`training-browser-${Date.now()}`);
    await page.getByLabel("Password", {exact: true}).fill("test-only-training-browser-password");
    await page.getByRole("button", {name: "Create account", exact: true}).click();
    await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
    const account = await page.request.get("/api/v1/auth/me").then(r => r.json());
    execFileSync("uv", ["run", "python", "-m", "aevyra_api.research.operator", "grant", account.user.public_user_id, "--reason", "Synthetic training browser test"], {cwd: root, stdio: "pipe"});
    await page.goto("/research/preferences");
    await page.getByLabel("Project name", {exact: true}).fill("Personal training");
    await page.getByRole("button", {name: "Create project", exact: true}).click();
    await page.getByLabel("Dataset name", {exact: true}).fill("Training fixture");
    await page.getByLabel("Source", {exact: true}).fill("Synthetic colors");
    await page.getByLabel("License and restrictions").fill("Generated test fixture");
    await page.getByLabel("I confirm every subject").check();
    await page.getByRole("button", {name: "Save dataset"}).click();
    await expect(page.getByRole("heading", {name: "Upload photographs", level: 2})).toBeVisible();
    const encoded: string[] = JSON.parse(execFileSync("uv", ["run", "python", "-c", "import base64,json; from PIL import Image; from io import BytesIO; result=[]\nfor value in list(range(20,220,20))+[125,230]:\n b=BytesIO(); Image.new('RGB',(80,80),(value,40,50)).save(b,'PNG'); result.append(base64.b64encode(b.getvalue()).decode())\nprint(json.dumps(result))"], {cwd: root, encoding: "utf8"}));
    const files = encoded.map((value, index) => ({name: `fixture-${index}.png`, mimeType: "image/png", buffer: Buffer.from(value, "base64")}));
    await page.getByLabel("Adult photographs", {exact: true}).setInputFiles(files.slice(0, 10));
    await page.getByLabel("I confirm every subject").last().check();
    await page.getByRole("button", {name: "Upload photographs", exact: true}).click();
    await expect(page.getByText("Dataset: Training fixture · 10 photographs saved · 10 awaiting rating", {exact: true})).toBeVisible();
    await page.getByRole("button", {name: "Continue to rating", exact: true}).click();
    for (let i = 0; i < 10; i++) {
      await page.getByLabel("Your rating").fill(String(1 + i * 0.8));
      await page.getByRole("button", {name: i < 9 ? "Save and next" : "Save rating", exact: true}).click();
      if (i < 9) await expect(page.getByText(`Image ${i + 2} of 10`, {exact: true})).toBeVisible();
    }
    // Completion screen with a prominent training action, offered only because the server agrees.
    await expect(page.getByRole("heading", {name: "Every photograph has been processed."})).toBeVisible();
    await expect(page.getByText("Your ratings meet every training requirement. Train a personal model below.", {exact: true})).toBeVisible();
    await expect(page.getByText("Ready to train", {exact: true})).toBeVisible();
    await page.getByRole("combobox", {name: "Visual feature extractor", exact: true}).selectOption(extractor);
    await page.getByRole("button", {name: "Train new version", exact: true}).click();
    await expect(page.getByText(`Version 1 · READY · ${extractor}`, {exact: true})).toBeVisible({timeout: 20000});
    await expect(page.getByRole("heading", {name: "Validation for version 1"})).toBeVisible();
    // Predict from a brand-new photograph; it is auto-selected and never joins training.
    await page.getByRole("radio", {name: "Upload a new photograph", exact: true}).check();
    await page.getByLabel("Photograph of an adult to predict", {exact: true}).setInputFiles(files[10]);
    await page.getByLabel("I confirm every subject").last().check();
    await page.getByRole("button", {name: "Upload photograph for prediction", exact: true}).click();
    await expect(page.getByText("Photograph uploaded and selected for prediction. It will not be added to training.", {exact: true})).toBeVisible();
    await expect(page.getByRole("combobox", {name: "Photograph to predict", exact: true})).toHaveValue(/[0-9a-f-]{36}/);
    await expect(page.getByText("2 valid ratings", {exact: false})).toHaveCount(0);
    await expect(page.getByText("10 valid ratings · 0 skipped · 0 excluded · 0 awaiting rating", {exact: true})).toBeVisible();
    await page.getByRole("button", {name: "中文", exact: true}).click();
    await page.getByRole("button", {name: "预测个人评分", exact: true}).click();
    await expect(page.getByText("预测个人评分：", {exact: false})).toBeVisible({timeout: 20000});
    await page.getByRole("button", {name: "English", exact: true}).click();
    await expect(page.getByText("This photograph was unseen in the model's annotation snapshot.", {exact: true})).toBeVisible();
    const query = new URL(page.url()).searchParams;
    const readiness = await page.request.get(`/api/v1/research/preferences/datasets/${query.get("dataset")}/readiness`).then(r => r.json());
    expect(readiness.prediction_only).toBe(1);
    expect(readiness.rated).toBe(10);
    // Add a new annotation photograph, rate it, and retrain a persisted second version.
    await page.getByRole("button", {name: "Previous step", exact: true}).click();
    await page.getByLabel("Adult photographs", {exact: true}).setInputFiles(files[11]);
    await page.getByLabel("I confirm every subject").last().check();
    await page.getByRole("button", {name: "Upload photographs", exact: true}).click();
    await expect(page.getByText("Dataset: Training fixture · 11 photographs saved · 1 awaiting rating", {exact: true})).toBeVisible();
    await page.getByRole("button", {name: "Continue to rating", exact: true}).click();
    await expect(page.getByText("Image 11 of 11", {exact: true})).toBeVisible();
    await page.getByLabel("Your rating").fill("5.5");
    await page.getByRole("button", {name: "Save rating", exact: true}).click();
    await expect(page.getByText("11 valid ratings · 0 skipped · 0 excluded · 0 awaiting rating", {exact: true})).toBeVisible();
    await expect(page.getByText("Ready to train with 11 valid ratings from 11 independent groups.", {exact: true})).toBeVisible();
    await page.getByRole("button", {name: "Train new version", exact: true}).click();
    await expect(page.getByText(`Version 2 · READY · ${extractor}`, {exact: true})).toBeVisible({timeout: 20000});
    await page.reload();
    await expect(page.getByRole("heading", {name: "Rate photographs", level: 2})).toBeVisible();
    await expect(page.getByText(`Version 1 · READY · ${extractor}`, {exact: true})).toBeVisible();
    await expect(page.getByText(`Version 2 · READY · ${extractor}`, {exact: true})).toBeVisible();
    await page.goto("/account");
    await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
  } finally {
    await new Promise<void>(resolve => {
      if (worker.exitCode !== null) {resolve(); return;}
      const timeout = setTimeout(() => worker.kill("SIGKILL"), 10000);
      worker.once("exit", () => {clearTimeout(timeout); resolve();});
      worker.kill("SIGTERM");
    });
  }
});
}
