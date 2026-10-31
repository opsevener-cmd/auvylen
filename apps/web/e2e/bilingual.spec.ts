import {test, expect, type Page} from "@playwright/test";

const projectId = "10000000-0000-4000-8000-000000000001";
const datasetId = "20000000-0000-4000-8000-000000000001";
const imageIds = ["30000000-0000-4000-8000-000000000001", "30000000-0000-4000-8000-000000000002"];
const stamp = "2026-10-18T00:00:00Z";
const dataset = {id: datasetId, project_id: projectId, name: "Bilingual fixture", source: "Generated test fixtures", source_url: "", license: "Test-only", rating_min: 1, rating_max: 10, archived: false, created_at: stamp, expires_at: "2030-01-01T00:00:00Z", image_count: 0, rated_count: 0, compared_count: 0};
const base = `/api/v1/research/preferences/datasets/${datasetId}`;
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+afoQAAAAASUVORK5CYII=", "base64");
const syntheticImage = (index: number) => ({id: imageIds[index], dataset_id: datasetId, width: 1, height: 1, subject_group: null, excluded: false, created_at: stamp, score: null as number | null, rating_recorded: false, purpose: "annotation" as const});

async function mockResearch(page: Page) {
  const images: ReturnType<typeof syntheticImage>[] = [];
  const pairs: {id: string; left_id: string; right_id: string; choice: string; updated_at: string}[] = [];
  const calls: string[] = [];
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const endpoint = url.pathname;
    calls.push(`${route.request().method()} ${endpoint}`);
    let body: unknown = [];
    if (endpoint.endsWith("/auth/csrf")) body = {csrf_token: "synthetic-csrf"};
    else if (endpoint.endsWith("/projects")) body = [{id: projectId, name: "Demo project", created_at: stamp}];
    else if (endpoint.endsWith("/datasets")) body = [{...dataset, image_count: images.length}];
    else if (endpoint === `${base}/readiness`) {
      const rated = images.filter(i => i.score !== null).length;
      body = {eligible: false, reasons: ["too_few_ratings", "too_few_groups"], rated, required_ratings: 8, groups: rated, required_groups: 5, awaiting: images.filter(i => !i.rating_recorded).length, skipped: 0, excluded: 0, prediction_only: 0};
    } else if (endpoint === base) body = {dataset: {...dataset, image_count: images.length, rated_count: images.filter(i => i.score !== null).length, compared_count: pairs.length}, images, pairs};
    else if (endpoint.endsWith("/extractors")) body = [{id: "rgb-grid-texture-v1", available: true, reason: "Built-in handcrafted features", manifest: {}}];
    else if (endpoint.endsWith("/rating")) {
      const image = images.find(item => endpoint.includes(item.id))!;
      image.score = route.request().postDataJSON().score; image.rating_recorded = true; body = image;
    } else if (endpoint.endsWith("/pairs")) {
      const input = route.request().postDataJSON();
      const pair = {...input, id: "40000000-0000-4000-8000-000000000001", updated_at: stamp};
      pairs.splice(0, pairs.length, pair); body = pair;
    } else if (endpoint.endsWith("/content")) {await route.fulfill({contentType: "image/png", body: png, headers: {"Cache-Control": "private, no-store"}}); return;}
    await route.fulfill({json: body});
  });
  return {images, pairs, calls};
}

test("detects Chinese without hydration errors and persists switching without clearing a form", async ({browser}, info) => {
  const context = await browser.newContext({locale: "zh-CN", viewport: {width: 390, height: 844}});
  const page = await context.newPage();
  const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
  const response = await page.goto("/");
  expect(await response!.text()).toContain('lang="zh-CN"');
  await expect(page.getByRole("heading", {level: 1})).toContainText("探索属于你的审美");
  await expect(page.locator(".guide-list li")).toHaveCount(9);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: info.outputPath("home-zh-mobile.png"), fullPage: true});
  await page.getByRole("button", {name: "菜单", exact: true}).click();
  await expect(page.getByRole("navigation", {name: "主导航"})).toBeVisible();
  await page.getByRole("button", {name: "English", exact: true}).click();
  await page.setViewportSize({width: 1440, height: 1000});
  await page.screenshot({path: info.outputPath("home-en-desktop.png"), fullPage: true});
  await page.goto("/login");
  await page.getByLabel("Username or email-like identifier").fill("test-only-unsaved");
  await page.getByLabel("Password", {exact: true}).fill("test-only-unsaved-password");
  await page.getByRole("button", {name: "中文", exact: true}).click();
  await expect(page.getByLabel("用户名或邮箱格式的登录标识")).toHaveValue("test-only-unsaved");
  await expect(page.getByLabel("密码", {exact: true})).toHaveValue("test-only-unsaved-password");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.getByRole("heading", {name: "登录", exact: true})).toBeVisible();
  await page.getByRole("button", {name: "登录", exact: true}).click();
  expect(await page.getByLabel("用户名或邮箱格式的登录标识").evaluate((el: HTMLInputElement) => el.validationMessage)).toBe("请填写此必填项。");
  expect(errors).toEqual([]);
  await context.close();
});

test("slow uploads, partial recovery, live language switching, ratings and comparisons", async ({page}, info) => {
  const state = await mockResearch(page);
  let firstAttempts = 0; let secondAttempts = 0;
  let releaseFirst!: () => void;
  const held = new Promise<void>(resolve => {releaseFirst = resolve;});
  await page.route(`**${base}/images`, async route => {
    expect(route.request().headers()["x-csrf-token"]).toBe("synthetic-csrf");
    expect(route.request().headers()["content-type"]).toBe("image/png");
    expect(route.request().postDataBuffer()).toEqual(png);
    const isFirst = firstAttempts === 0;
    if (isFirst) {firstAttempts++; await held; state.images.push(syntheticImage(0)); await route.fulfill({json: state.images[0]});}
    else {secondAttempts++; if (secondAttempts === 1) {await route.fulfill({status: 503, json: {detail: "test failure"}}); return;}
      state.images.push(syntheticImage(1)); await route.fulfill({json: state.images[1]});}
  });
  await page.goto("/research/preferences");
  // Saved server data resumes the wizard at the first unfinished step: uploading.
  await expect(page.getByRole("heading", {name: "Upload photographs", level: 2})).toBeVisible();
  await page.getByLabel("Adult photographs", {exact: true}).setInputFiles(["first", "second"].map(name => ({name: `${name}.png`, mimeType: "image/png", buffer: png})));
  await page.getByLabel("I confirm every subject").last().check();
  await page.getByRole("button", {name: "Upload photographs", exact: true}).click();
  await expect(page.locator(".upload-zone")).toHaveAttribute("aria-busy", "true");
  await expect(page.getByRole("button", {name: "Uploading photographs…", exact: true})).toBeDisabled();
  await expect(page.locator(".upload-queue")).not.toContainText("Saved successfully");
  await page.getByRole("button", {name: "中文", exact: true}).click();
  await expect(page.getByRole("button", {name: "正在上传照片…", exact: true})).toBeDisabled();
  releaseFirst();
  await expect(page.locator(".upload-queue")).toContainText("保存成功");
  await expect(page.locator(".upload-queue")).toContainText("上传失败");
  await page.getByRole("button", {name: "重试未保存的照片", exact: true}).click();
  await expect(page.locator(".upload-zone")).toContainText("已确认保存 2／2");
  expect(firstAttempts).toBe(1); expect(secondAttempts).toBe(2);
  await page.getByRole("button", {name: "继续评分", exact: true}).click();
  await page.getByLabel("你的评分", {exact: false}).fill("8");
  await page.getByRole("button", {name: "English", exact: true}).click();
  await expect(page.getByLabel("Your rating")).toHaveValue("8");
  const beforeSave = state.calls.length;
  await page.getByRole("button", {name: "Save and next", exact: true}).click();
  await expect(page.getByText("Rating saved.", {exact: true})).toBeVisible();
  expect(state.calls.slice(beforeSave).filter(call => !call.endsWith("/content"))).toEqual(["GET /api/v1/auth/csrf", `POST ${base}/images/${imageIds[0]}/rating`]);
  await page.getByRole("button", {name: "Compare pairs", exact: true}).click();
  await page.getByRole("button", {name: "Left preferred", exact: true}).click();
  await expect(page.getByText("Comparison saved.", {exact: true})).toBeVisible();
  await page.getByText("Review saved comparisons (1)", {exact: true}).click();
  await page.getByRole("button", {name: "Comparison 1: left", exact: true}).click();
  await page.getByRole("button", {name: "Right preferred", exact: true}).click();
  await expect.poll(() => state.pairs[0].choice).toBe("right");
  await expect(page.getByRole("button", {name: "Train new version", exact: true})).toBeDisabled();
  await page.getByRole("button", {name: "中文", exact: true}).click();
  await expect(page.getByText("再添加 7 个有效评分（目前 1／8）。已跳过和已排除的照片不计入。", {exact: true})).toBeVisible();
  await page.screenshot({path: info.outputPath("research-zh-mobile.png"), fullPage: true});
});
