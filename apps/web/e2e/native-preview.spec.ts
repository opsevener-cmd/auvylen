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
  expect(await page.getByLabel("已获授权的成人肖像").evaluate((e: HTMLInputElement) => e.files?.length)).toBe(0);
  await page.getByLabel("已获授权的成人肖像").setInputFiles({name: "contract-fixture.png", mimeType: "image/png", buffer: png});
  await page.getByRole("checkbox").check();
  await page.getByRole("button", {name: "运行原生模型私密预览"}).click();
  await expect.poll(() => submits).toBe(2);
});

const available = {available: true, consumer_enabled: false, native_scale: [1, 7], collection: "UI contract fixture, not inference evidence", encoder: "contract-fixture", manifest_sha256: "a".repeat(64), release_failures: ["insufficient_test_subjects", "real_pose_review_missing", "unreviewed_fixture_code"]};
const fixtureResult = {predicted_rating: 4.25, native_scale: [1, 7], manifest_sha256: "a".repeat(64), encoder: "contract-fixture", collection: "UI contract fixture, not inference evidence", research_only: true, synthetic: false, consumer_enabled: false, release_failures: ["insufficient_test_subjects"], duration_ms: 1, peak_rss_kib: 1};

test("reload restores a completed request with release-gate reasons; screenshots", async ({page}, info) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.route("**/api/v1/**", async route => {
    const endpoint = new URL(route.request().url()).pathname;
    if (endpoint === base + "/status") {await route.fulfill({json: available}); return;}
    if (endpoint === `${base}/jobs/${job.id}`) {await route.fulfill({json: {...job, status: "COMPLETED", progress: 100, result: fixtureResult, completed_at: "2026-11-01T00:00:05Z"}}); return;}
    await route.fulfill({status: 404, json: {detail: "Not found"}});
  });
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto(`/research/native-preview?job=${job.id}`);
  await expect(page.getByText("4.25")).toBeVisible();
  await expect(page.getByRole("button", {name: "Delete this preview now"})).toBeVisible();
  await page.getByText("Why release is blocked (3 open checks)").click();
  await expect(page.getByText("Too few independent people in the held-out test")).toBeVisible();
  await expect(page.getByText("unreviewed_fixture_code")).toBeVisible();
  await page.screenshot({path: info.outputPath("native-preview-result-en-desktop.png"), fullPage: true});
  await page.getByRole("button", {name: "中文", exact: true}).click();
  await expect(page.getByText("留出测试中的独立人物过少")).toBeVisible();
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: info.outputPath("native-preview-result-zh-mobile.png"), fullPage: true});
  expect(errors).toEqual([]);
});

test("an expired restored request is dropped from the URL; no score shown", async ({page}) => {
  await page.route("**/api/v1/**", async route => {
    const endpoint = new URL(route.request().url()).pathname;
    if (endpoint === base + "/status") {await route.fulfill({json: available}); return;}
    await route.fulfill({status: 404, json: {detail: "Research job not found"}});
  });
  await page.goto(`/research/native-preview?job=${job.id}`);
  await expect(page.getByText("That preview request has expired or was deleted. Nothing was kept.")).toBeVisible();
  await expect.poll(() => new URL(page.url()).searchParams.has("job")).toBe(false);
  await expect(page.getByText("Research prediction · native scale 1–7")).toHaveCount(0);
});

test("a stale Owner sign-in gets a specific message and keeps the chosen photograph", async ({page}, info) => {
  await page.route("**/api/v1/**", async route => {
    const endpoint = new URL(route.request().url()).pathname;
    if (endpoint === base + "/status") {await route.fulfill({json: available}); return;}
    if (endpoint.endsWith("/auth/csrf")) {await route.fulfill({json: {csrf_token: "test-only-token"}}); return;}
    if (endpoint === base + "/jobs") {await route.fulfill({status: 403, json: {detail: "Fresh Owner sign-in required for this operation"}}); return;}
    await route.fulfill({status: 404, json: {detail: "Not found"}});
  });
  await page.goto("/research/native-preview");
  await page.getByLabel("Authorized adult portrait").setInputFiles({name: "contract-fixture.png", mimeType: "image/png", buffer: png});
  await page.getByRole("checkbox").check();
  await page.getByRole("button", {name: "Run private native preview"}).click();
  await expect(page.getByRole("alert").filter({hasText: "Owner"})).toContainText("For safety, previews need a recent Owner sign-in.");
  await expect(page.getByRole("link", {name: "Sign in again"})).toHaveAttribute("href", "/login");
  await expect(page.getByText("contract-fixture.png")).toBeVisible();
  await expect(page.getByRole("button", {name: "Run private native preview"})).toBeEnabled();
  await expect(page.getByRole("alert").filter({hasText: "Owner"})).toBeFocused();
  await expect(page.getByRole("alert").filter({hasText: "Owner"})).toBeInViewport();
  // Viewport capture: what the Owner sees immediately after the failed submit.
  await page.screenshot({path: info.outputPath("native-preview-fresh-signin-en-mobile.png")});
});
