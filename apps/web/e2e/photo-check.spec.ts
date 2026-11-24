import {expect, test} from "@playwright/test";

test.use({trace: "off"});
// 40x50 PNG. The real API is used for sign-in and the disabled state; the Gemini-backed
// routes are mocked in the browser, so this test never contacts Google.
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAACgAAAAyCAIAAACh0Q7HAAAANklEQVR4nO3NQQEAQAQAsHOphRBHQDF4bAUWXfk2/JVVLBaLxWKxWCwWi8VisVgsFovF4iPxAFMlAhwazkQSAAAAAElFTkSuQmCC", "base64");
const status = {available: true, reason: "ready", consent_version: "gemini-paid-v1", consent_required: true, used_today: 0, daily_limit: 30, max_photos: 5};
const scores = (base: number) => ({lighting: base, sharpness: base, framing: base, expression: base, eye_contact: base, background: base});

test("free photo check: sign-in prompt, disabled state, consent, upload and ranked results", async ({page}) => {
  await page.goto("/photo-check");
  await expect(page.getByText("Sign in to check your photos.")).toBeVisible();
  const stamp = Date.now().toString();
  await page.goto("/register");
  await page.getByLabel("Username or email-like identifier").fill(`photo-${stamp}`);
  await page.getByLabel("Password", {exact: true}).fill(`test-only-photo-password-${stamp}`);
  await page.getByRole("button", {name: "Create account", exact: true}).click();
  await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
  // The test API runs with FREE_HOOK_ENABLED unset: the check is honestly unavailable.
  await page.goto("/photo-check");
  await expect(page.getByText("Photo check is not available right now.")).toBeVisible();

  let consented = false;
  let uploaded: {photos: string[]; language: string} | null = null;
  await page.route("**/api/v1/photo-check/status", route => route.fulfill({json: {...status, consent_required: !consented}}));
  await page.route("**/api/v1/photo-check/consent", route => {consented = true; return route.fulfill({json: {accepted: true}});});
  await page.route("**/api/v1/photo-check/analyses", route => {
    uploaded = route.request().postDataJSON();
    return route.fulfill({json: {id: "6b0b2f1e-4b5c-4d3e-9f10-2a3b4c5d6e7f", engine: "gemini-photo-quality", model: "gemini-3.5-flash-lite",
      prompt_version: "photo-quality-v1", created_at: new Date().toISOString(), used_today: 1, daily_limit: 30, photos: [
        {index: 0, rank: 2, usable: true, refusal_reason: null, scores: scores(5), raw_score: 5, display_score: 5, tips: ["Face a window for softer light"]},
        {index: 1, rank: 1, usable: true, refusal_reason: null, scores: scores(8), raw_score: 8, display_score: 8, tips: []},
        {index: 2, rank: null, usable: false, refusal_reason: "multiple_people", scores: null, raw_score: null, display_score: null, tips: []},
      ]}});
  });
  await page.reload();
  const accept = page.getByRole("button", {name: "Accept and continue"});
  await expect(accept).toBeDisabled();
  await page.getByLabel("I am 18 or older.").check();
  await page.getByLabel("I agree that my photos are sent to Google's Gemini API for this check.").check();
  await accept.click();
  await page.getByLabel("Choose 1 to 5 photos (JPEG or PNG)").setInputFiles([0, 1, 2].map(i => ({name: `p${i}.png`, mimeType: "image/png", buffer: png})));
  await page.getByRole("button", {name: "Check my photos"}).click();
  await expect(page.getByText("Best photo")).toBeVisible();
  await expect(page.getByText("8.0")).toBeVisible();
  await expect(page.getByText("Face a window for softer light")).toBeVisible();
  await expect(page.getByText("More than one person is in this photo. Use a photo of just you.")).toBeVisible();
  expect(uploaded!.photos).toHaveLength(3);
  expect(uploaded!.language).toBe("en");
  // Ranked best first.
  await expect(page.locator("article").first()).toContainText("Best photo");

  // Chinese copy.
  await page.getByRole("button", {name: "Check other photos"}).click();
  await page.getByRole("button", {name: "中文"}).click();
  await expect(page.getByRole("heading", {name: "你的哪张照片效果最好？"})).toBeVisible();
});
