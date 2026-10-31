import {test, expect} from "@playwright/test";
import {execFileSync} from "node:child_process";
import path from "node:path";

test.use({trace: "off", screenshot: "off", video: "off"});
test("four-step wizard: dataset, ratings, completion, restore, revision and deletion", async ({page}) => {
  test.skip(process.env.E2E_RESEARCH !== "true", "Requires the explicit research test configuration");
  const root = path.resolve(__dirname, "../../..");
  const stamp = Date.now().toString();
  await page.goto("/register");
  await page.getByLabel("Username or email-like identifier").fill(`preferences-${stamp}`);
  await page.getByLabel("Password", {exact: true}).fill(`test-only-preferences-password-${stamp}`);
  await page.getByRole("button", {name: "Create account", exact: true}).click();
  await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
  const user = await page.request.get("/api/v1/auth/me").then(r => r.json());
  execFileSync("uv", ["run", "python", "-m", "aevyra_api.research.operator", "grant", user.user.public_user_id, "--reason", "Synthetic browser test"], {cwd: root, stdio: "pipe"});
  await page.goto("/research");
  await page.getByRole("link", {name: "Manage personal preference datasets"}).click();
  // Step 1 → automatic progression to step 2 after creation.
  await expect(page.getByRole("heading", {name: "Create project", level: 2})).toBeVisible();
  await expect(page.getByRole("button", {name: "Next step", exact: true})).toBeDisabled();
  await page.getByLabel("Project name", {exact: true}).fill("Browser preferences");
  await page.getByRole("button", {name: "Create project", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Create dataset", level: 2})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Create dataset", level: 2})).toBeFocused();
  await page.getByLabel("Dataset name", {exact: true}).fill("Browser synthetic set");
  await page.getByLabel("Source", {exact: true}).fill("Programmatically generated solid colors");
  await page.getByLabel("License and restrictions").fill("Synthetic test-only fixtures");
  await page.getByLabel("I confirm every subject").check();
  await page.getByRole("button", {name: "Save dataset"}).click();
  // Step 3: only the active step is rendered.
  await expect(page.getByRole("heading", {name: "Upload photographs", level: 2})).toBeVisible();
  await expect(page.getByLabel("Dataset name", {exact: true})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Next step", exact: true})).toBeDisabled();
  const buffers = JSON.parse(execFileSync("uv", ["run", "python", "-c", "import base64,json; from io import BytesIO; from PIL import Image; result=[]\nfor color in ['red','blue']:\n b=BytesIO(); Image.new('RGB',(100,80),color).save(b,'PNG'); result.append(base64.b64encode(b.getvalue()).decode())\nprint(json.dumps(result))"], {cwd: root, encoding: "utf8"}));
  await page.getByLabel("Adult photographs", {exact: true}).setInputFiles(buffers.map((buffer: string, i: number) => ({name: `synthetic-${i}.png`, mimeType: "image/png", buffer: Buffer.from(buffer, "base64")})));
  await page.getByLabel("I confirm every subject").last().check();
  await page.getByRole("button", {name: "Upload photographs", exact: true}).click();
  await expect(page.getByText("Dataset: Browser synthetic set · 2 photographs saved · 2 awaiting rating", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Continue to rating", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Rate photographs", level: 2})).toBeVisible();
  // Step moves are real history entries: Back/Forward revisit steps without losing data.
  await page.goBack();
  await expect(page.getByRole("heading", {name: "Upload photographs", level: 2})).toBeVisible();
  await page.goForward();
  await expect(page.getByRole("heading", {name: "Rate photographs", level: 2})).toBeVisible();
  const photos = page.getByRole("img", {name: "Private photograph for your subjective annotation"});
  await expect(photos.first()).toBeVisible();
  await expect.poll(() => photos.first().evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
  const privateUrl = await photos.first().getAttribute("src");
  const photo = await page.request.get(privateUrl!);
  expect(photo.status()).toBe(200);
  expect(photo.headers()["content-type"]).toContain("image/jpeg");
  expect(photo.headers()["cache-control"]).toContain("no-store");
  await page.getByLabel("Your rating").fill("8");
  await page.getByRole("button", {name: "Save and next", exact: true}).click();
  await expect(page.getByText("Image 2 of 2", {exact: true})).toBeVisible();
  // The final unrated photograph saves into a completion screen, not another "Save and next".
  await expect(page.getByRole("button", {name: "Save and next", exact: true})).toHaveCount(0);
  await page.getByLabel("Your rating").fill("6");
  await page.getByRole("button", {name: "Save rating", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Every photograph has been processed."})).toBeVisible();
  await expect(page.getByText("2 valid ratings · 0 skipped · 0 excluded · 0 awaiting rating", {exact: true})).toBeVisible();
  await expect(page.getByText("Add 6 more valid ratings (2 of 8). Skipped and excluded photographs do not count.", {exact: true})).toBeVisible();
  await expect(page.getByRole("button", {name: "Train new version"})).toBeDisabled();
  // A malformed step in the URL is ignored rather than breaking the page.
  const restored = new URL(page.url());
  restored.searchParams.set("step", "1.5");
  await page.goto(restored.toString());
  await expect(page.getByRole("heading", {name: "Rate photographs", level: 2})).toBeVisible();
  // Refresh restores the same step, dataset and saved state from the server.
  await page.reload();
  await expect(page.getByRole("heading", {name: "Rate photographs", level: 2})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Every photograph has been processed."})).toBeVisible();
  // Revisit a completed photograph and revise its rating without losing data.
  await page.getByRole("button", {name: "Select image 1", exact: true}).click();
  await expect(page.getByLabel("Your rating")).toHaveValue("8");
  await page.getByLabel("Your rating").fill("9");
  await page.getByRole("button", {name: "Save rating", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Every photograph has been processed."})).toBeVisible();
  await page.getByRole("button", {name: "Compare pairs", exact: true}).click();
  await page.getByRole("button", {name: "Left preferred", exact: true}).click();
  await expect(page.getByText("No unseen pairs remain. Upload more images or edit a saved comparison below.")).toBeVisible();
  // Previous returns to earlier steps with saved data intact.
  await page.getByRole("button", {name: "Previous step", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Upload photographs", level: 2})).toBeVisible();
  await expect(page.getByText("Dataset: Browser synthetic set · 2 photographs saved · 0 awaiting rating", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Previous step", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Create dataset", level: 2})).toBeVisible();
  await expect(page.getByRole("radio", {name: /Browser synthetic set/})).toBeChecked();
  await page.getByText("Manage “Browser synthetic set”", {exact: true}).click();
  await page.getByRole("button", {name: "Archive dataset"}).click();
  await expect(page.getByRole("button", {name: "Restore dataset"})).toBeVisible();
  await page.getByRole("button", {name: "Next step", exact: true}).click();
  await expect(page.getByText("This dataset is archived. Restore it before uploading.")).toBeVisible();
  await expect(page.getByLabel("Adult photographs", {exact: true})).toHaveCount(0);
  await page.getByRole("button", {name: "Previous step", exact: true}).click();
  await page.getByText("Manage “Browser synthetic set”", {exact: true}).click();
  await page.getByRole("button", {name: "Restore dataset"}).click();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", {name: "Delete dataset", exact: true}).click();
  await expect(page.getByRole("radio", {name: /Browser synthetic set/})).toHaveCount(0);
  expect((await page.request.get(privateUrl!)).status()).toBe(404);
  await page.goto("/account");
  await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
});
