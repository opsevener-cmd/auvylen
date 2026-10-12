import {test, expect} from "@playwright/test";
import {execFileSync, spawn} from "node:child_process";
import path from "node:path";

test.use({trace: "off", screenshot: "off", video: "off"});
test("train ratings, predict unseen upload and retrain a persisted model version", async ({page}) => {
  test.skip(process.env.E2E_RESEARCH !== "true", "Requires explicit private research test mode");
  test.setTimeout(90000);
  const root = path.resolve(__dirname, "../../..");
  const worker = spawn("uv", ["run", "python", "-m", "aevyra_api.research.worker"], {cwd: root,
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
    await page.getByText("Create a dataset", {exact: true}).click();
    await page.getByLabel("Dataset name", {exact: true}).fill("Training fixture");
    await page.getByLabel("Source", {exact: true}).fill("Synthetic colors");
    await page.getByLabel("License and restrictions").fill("Generated test fixture");
    await page.getByLabel("I confirm every subject").check();
    await page.getByRole("button", {name: "Save dataset"}).click();
    await expect(page.getByRole("heading", {name: "Training fixture", exact: true})).toBeVisible();
    const encoded: string[] = JSON.parse(execFileSync("uv", ["run", "python", "-c", "import base64,json; from PIL import Image; from io import BytesIO; result=[]\nfor value in list(range(20,220,20))+[125]:\n b=BytesIO(); Image.new('RGB',(80,80),(value,40,50)).save(b,'PNG'); result.append(base64.b64encode(b.getvalue()).decode())\nprint(json.dumps(result))"], {cwd: root, encoding: "utf8"}));
    const files = encoded.map((value, index) => ({name: `fixture-${index}.png`, mimeType: "image/png", buffer: Buffer.from(value, "base64")}));
    await page.getByLabel("Adult photographs", {exact: true}).setInputFiles(files.slice(0, 10));
    await page.getByLabel("I confirm every subject").last().check();
    await page.getByRole("button", {name: "Upload photographs"}).click();
    await expect(page.getByText("10 images · 0 rated · 0 comparisons · 10 awaiting rating", {exact: true})).toBeVisible();
    for (let i = 0; i < 10; i++) {
      await page.getByLabel("Your rating").fill(String(1 + i * 0.8));
      await page.getByRole("button", {name: "Save and next", exact: true}).click();
      if (i < 9) await expect(page.getByText(`Image ${i + 2} of 10`, {exact: true})).toBeVisible();
    }
    await expect(page.getByText("10 images · 10 rated · 0 comparisons · 0 awaiting rating", {exact: true})).toBeVisible();
    await page.getByRole("button", {name: "Train new version", exact: true}).click();
    await expect(page.getByText("Version 1 · READY · rgb-grid-texture-v1", {exact: true})).toBeVisible({timeout: 20000});
    await expect(page.getByRole("heading", {name: "Validation for version 1"})).toBeVisible();
    await page.getByLabel("Adult photographs", {exact: true}).setInputFiles(files[10]);
    await page.getByLabel("I confirm every subject").last().check();
    await page.getByRole("button", {name: "Upload photographs"}).click();
    await expect(page.getByText("11 images · 10 rated · 0 comparisons · 1 awaiting rating", {exact: true})).toBeVisible();
    await page.getByLabel("Photograph to predict").selectOption({label: "Image 11 · unrated"});
    await page.getByRole("button", {name: "Predict personal rating", exact: true}).click();
    await expect(page.getByText("Predicted personal rating:", {exact: false})).toBeVisible({timeout: 20000});
    await expect(page.getByText("This photograph was unseen in the model's annotation snapshot.", {exact: true})).toBeVisible();
    await page.getByRole("button", {name: "Select image 11", exact: true}).click();
    await page.getByLabel("Your rating").fill("5.5");
    await page.getByRole("button", {name: "Save and next", exact: true}).click();
    await expect(page.getByText("11 images · 11 rated · 0 comparisons · 0 awaiting rating", {exact: true})).toBeVisible();
    await page.getByRole("button", {name: "Train new version", exact: true}).click();
    await expect(page.getByText("Version 2 · READY · rgb-grid-texture-v1", {exact: true})).toBeVisible({timeout: 20000});
    await page.reload();
    await page.getByRole("button", {name: "Training fixture · 11 images · 11 rated", exact: true}).click();
    await expect(page.getByText("Version 1 · READY · rgb-grid-texture-v1", {exact: true})).toBeVisible();
    await expect(page.getByText("Version 2 · READY · rgb-grid-texture-v1", {exact: true})).toBeVisible();
    await page.goto("/account");
    await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
  } finally {
    worker.kill("SIGTERM");
    await new Promise<void>(resolve => {if (worker.exitCode !== null) resolve(); else worker.once("exit", () => resolve());});
  }
});
