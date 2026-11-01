import {test, expect} from "@playwright/test";

// UI contract fixtures only; actual inference is verified by the opt-in Python test.
const base = "/api/v1/research/native-preview";
const job = {id: "80000000-0000-4000-8000-000000000001", provider: "auvylen-native", kind: "SCORE", status: "QUEUED", result: null, payload: null, progress: 0, phase: "Queued", failure_reason: null, created_at: "2026-11-01T00:00:00Z", completed_at: null};
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+afoQAAAAASUVORK5CYII=", "base64");

test("native preview disabled in both languages, no numeric result", async ({page}, info) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.route("**/api/v1/**", route => route.fulfill({json: {available: false, consumer_enabled: false, native_scale: [1, 7]}}));
  await page.goto("/research/native-preview");
  await expect(page.getByText("This research preview is disabled or its reviewed checkpoint is unavailable.")).toBeVisible();
  await expect(page.getByRole("button", {name: "Run private native preview"})).toHaveCount(0);
  await page.setViewportSize({width: 1440, height: 1000});
  await page.screenshot({path: info.outputPath("native-preview-disabled-en-desktop.png"), fullPage: true});
  await page.getByRole("button", {name: "中文", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Auvylen 原生模型研究预览"})).toBeVisible();
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: info.outputPath("native-preview-disabled-zh-mobile.png"), fullPage: true});
  expect(errors).toEqual([]);
});

test("private upload: language switching, binary body, queued state and cancellation", async ({page}) => {
  let submits = 0; let deleted = false;
  await page.route("**/api/v1/**", async route => {
    const endpoint = new URL(route.request().url()).pathname;
    if (endpoint === base + "/status") {await route.fulfill({json: {available: true, consumer_enabled: false, native_scale: [1, 7], collection: "UI contract fixture, not inference evidence", encoder: "contract-fixture", manifest_sha256: "a".repeat(64)}}); return;}
    if (endpoint.endsWith("/auth/csrf")) {await route.fulfill({json: {csrf_token: "test-only-token"}}); return;}
    if (endpoint === base + "/jobs") {
      submits++;
      expect(route.request().headers()["content-type"]).toBe("image/png");
      expect(route.request().headers()["x-csrf-token"]).toBe("test-only-token");
      expect(route.request().postDataBuffer()).toEqual(png);
      expect(JSON.parse(decodeURIComponent(route.request().headers()["x-upload-metadata"])).authorized_consent).toBe(true);
      await route.fulfill({status: 202, json: job}); return;
    }
    if (endpoint.endsWith("/delete")) {deleted = true; await route.fulfill({json: {deleted: true}}); return;}
    await route.fulfill({json: job});
  });
  await page.goto("/research/native-preview");
  await expect(page.getByRole("button", {name: "Run private native preview"})).toBeDisabled();
  await page.getByLabel("Authorized adult portrait").setInputFiles({name: "contract-fixture.png", mimeType: "image/png", buffer: png});
  await page.getByRole("checkbox").check();
  await page.getByRole("button", {name: "中文", exact: true}).click();
  await expect(page.getByRole("checkbox")).toBeChecked();
  expect(await page.getByLabel("已获授权的成人肖像").evaluate((e: HTMLInputElement) => e.files?.[0]?.name)).toBe("contract-fixture.png");
  await page.getByRole("button", {name: "运行原生模型私密预览"}).click();
  await expect(page.getByText("原生模型推理已排队或正在运行，只有工作进程完成并验证后才会显示结果。")).toBeVisible();
  await expect(page.getByRole("button", {name: "运行原生模型私密预览"})).toBeDisabled();
  expect(submits).toBe(1);
  await expect(page.getByText("研究预测 · 原生量表 1–7")).toHaveCount(0);
  await page.getByRole("button", {name: "删除预览并取消待处理任务"}).click();
  await expect(page.getByText("原生模型推理已排队或正在运行，只有工作进程完成并验证后才会显示结果。")).toHaveCount(0);
  expect(deleted).toBe(true);
});
