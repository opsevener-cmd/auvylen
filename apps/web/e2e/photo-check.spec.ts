import {expect, test} from "@playwright/test";

test.use({trace: "off"});
// 40x50 PNG. The real API is used for sign-in and the disabled state; the Gemini-backed
// routes are mocked in the browser, so this test never contacts Google.
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAACgAAAAyCAIAAACh0Q7HAAAANklEQVR4nO3NQQEAQAQAsHOphRBHQDF4bAUWXfk2/JVVLBaLxWKxWCwWi8VisVgsFovF4iPxAFMlAhwazkQSAAAAAElFTkSuQmCC", "base64");
const scores = (base: number) => ({lighting: base, sharpness: base, framing: base, expression: base, eye_contact: base, background: base});
const appearance = (band: number) => ({strengths: ["Warm, open smile"], flattering: ["Soft side light suits you"], tips: ["Try a darker jacket"], band});

test("photo check: consent, own-face confirmation, quota, appearance, hidden AI impression and roast", async ({page}) => {
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
  let checks = 0;
  const uploads: {photos: string[]; language: string; self_and_adult_confirmed: boolean; roast: string}[] = [];
  const status = () => ({available: true, reason: "ready", consent_version: "gemini-paid-v2", consent_required: !consented,
    free_checks_now: Math.max(0, 4 - checks), free_signup_remaining: Math.max(0, 3 - checks), next_free_on: null,
    credit_cost: 1, credit_balance: 0, roast_available: checks > 0, max_photos: 5});
  await page.route("**/api/v1/photo-check/status", route => route.fulfill({json: status()}));
  await page.route("**/api/v1/photo-check/consent", route => {consented = true; return route.fulfill({json: {accepted: true}});});
  await page.route("**/api/v1/photo-check/analyses", route => {
    const body = route.request().postDataJSON();
    uploads.push(body);
    checks += 1;
    const roasted = body.roast !== "off";
    return route.fulfill({json: {id: "6b0b2f1e-4b5c-4d3e-9f10-2a3b4c5d6e7f", engine: "gemini-photo-check", model: "gemini-3.5-flash-lite",
      prompt_version: "photo-appearance-v1", created_at: new Date().toISOString(), funding: "free_signup", credits_charged: 0,
      free_checks_now: 4 - checks, next_free_on: null, photos: [
        // Below the 6.0 quality gate: technique feedback only, no appearance, band or roast.
        {index: 0, rank: 2, usable: true, refusal_reason: null, scores: scores(5), raw_score: 5, display_score: 5, tips: ["Face a window for softer light"], quality_passed: false, appearance: null, roast: null},
        {index: 1, rank: 1, usable: true, refusal_reason: null, scores: scores(8), raw_score: 8, display_score: 8, tips: [], quality_passed: true, appearance: appearance(4),
          roast: roasted ? {lines: ["That ceiling light is auditioning for a crime drama."], vibe: "hk_film_lead_90s"} : null},
        {index: 2, rank: null, usable: false, refusal_reason: "cannot_analyse", scores: null, raw_score: null, display_score: null, tips: [], quality_passed: false, appearance: null, roast: null},
      ]}});
  });
  await page.reload();
  const accept = page.getByRole("button", {name: "Accept and continue"});
  await expect(page.getByText("feedback on your appearance", {exact: false})).toBeVisible();
  await expect(accept).toBeDisabled();
  await page.getByLabel("I am 18 or older.").check();
  await page.getByLabel("I agree that my photos are sent to Google's Gemini API for this check.").check();
  await accept.click();
  await expect(page.getByText("You have 4 free checks left.")).toBeVisible();
  // First check: no roast on offer, and the own-face confirmation is required.
  await expect(page.getByLabel("Roast me 🔥")).toHaveCount(0);
  await page.getByLabel("Choose 1 to 5 photos of yourself (JPEG or PNG)").setInputFiles([0, 1, 2].map(i => ({name: `p${i}.png`, mimeType: "image/png", buffer: png})));
  const run = page.getByRole("button", {name: "Check my photos"});
  await expect(run).toBeDisabled();
  await page.getByLabel("This is me and I'm 18+.").check();
  await run.click();
  await expect(page.getByText("Best photo")).toBeVisible();
  await expect(page.getByText("This one was free.")).toBeVisible();
  await expect(page.getByText("8.0")).toBeVisible();
  await expect(page.getByText("We can't analyse this photo.")).toBeVisible();
  await expect(page.locator("article").first()).toContainText("Best photo");
  await expect(page.getByRole("heading", {name: "What suits you"}).first()).toBeVisible();
  // Two stages: the good photo passes the quality gate; the weak one only gets photo tips.
  const best = page.locator("article").first();
  const weak = page.locator("article").nth(1);
  await expect(best.getByText("Quality OK ✓")).toBeVisible();
  await expect(weak.getByText("Photo quality 5.0/10. Retake it with the tips above, then check your look.")).toBeVisible();
  await expect(weak.getByText("Face a window for softer light")).toBeVisible();
  await expect(weak.getByRole("heading", {name: "What suits you"})).toHaveCount(0);
  await expect(weak.getByRole("button", {name: "Show my AI impression"})).toHaveCount(0);
  await expect(weak.getByRole("button", {name: "Try another photo"})).toBeVisible();
  await expect(page.getByRole("button", {name: "Show my AI impression"})).toHaveCount(1);
  // The AI impression stays hidden until asked for, with its label always visible.
  await expect(page.getByText("Striking😘🤩")).toHaveCount(0);
  await expect(page.getByText("AI impression for fun, not an objective rating").first()).toBeVisible();
  await page.getByRole("button", {name: "Show my AI impression"}).first().click();
  await expect(page.getByText("Striking😘🤩")).toBeVisible();
  expect(uploads[0]).toMatchObject({language: "en", self_and_adult_confirmed: true, roast: "off"});
  expect(uploads[0].photos).toHaveLength(3);

  // Second check: roast on offer, off by default; spicy adds jokes about the photo and a vibe.
  await page.getByRole("button", {name: "Check other photos"}).click();
  await expect(page.getByLabel("Roast me 🔥")).not.toBeChecked();
  await page.getByLabel("Roast me 🔥").check();
  await page.getByLabel("Spicy").check();
  await page.getByLabel("Choose 1 to 5 photos of yourself (JPEG or PNG)").setInputFiles([0, 1].map(i => ({name: `q${i}.png`, mimeType: "image/png", buffer: png})));
  await expect(page.getByLabel("This is me and I'm 18+.")).not.toBeChecked(); // Asked again every upload.
  await page.getByLabel("This is me and I'm 18+.").check();
  await page.getByRole("button", {name: "Check my photos"}).click();
  await expect(page.getByText("That ceiling light is auditioning for a crime drama.")).toBeVisible();
  await expect(page.getByText("Vibe: 90s Hong Kong film lead")).toBeVisible();
  expect(uploads[1].roast).toBe("spicy");

  // Chinese copy.
  await page.getByRole("button", {name: "中文"}).click();
  await expect(page.getByRole("heading", {name: "你的哪张照片效果最好？"})).toBeVisible();
  await expect(page.getByText("氛围感：90 年代港片主角")).toBeVisible();
  await expect(page.getByText("照片质量 5.0/10，按上面的建议重拍一张，再来看颜值评价。")).toBeVisible();
  // "Try another photo" goes straight back to choosing photos.
  await page.getByRole("button", {name: "换一张试试"}).click();
  await expect(page.getByText("选择照片", {exact: true})).toBeVisible();
});
