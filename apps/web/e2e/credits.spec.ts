import {test, expect} from "@playwright/test";
import {execFileSync} from "node:child_process";
import {readFileSync} from "node:fs";
import path from "node:path";

// Traces can capture passwords/codes. Do not record this account flow.
test.use({trace: "off"});

test("register, redeem ten Credits, spend one, view history and sign in again", async ({page}) => {
  const root = path.resolve(__dirname, "../../..");
  const stamp = Date.now().toString();
  const output = `exports/browser-${stamp}.csv`;
  execFileSync("uv", ["run", "python", "-m", "aevyra_api.operator", "generate-batch",
    "--name", "Browser pilot", "--channel", "manual", "--sku", "pilot-10",
    "--credits", "10", "--quantity", "1", "--output", output], {cwd: root, stdio: "pipe"});
  const code = readFileSync(path.join(root, output), "utf8").trim().split(/\r?\n/)[1].split(",")[0];
  const identifier = `browser-${stamp}`;
  const password = `test-only-pilot-password-${stamp}`;
  await page.goto("/register");
  await page.getByLabel("Username or email-like identifier").fill(identifier);
  await page.getByLabel("Password", {exact: true}).fill(password);
  await page.getByRole("button", {name: "Create account", exact: true}).click();
  await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
  await page.getByRole("link", {name: "Redeem Code", exact: true}).click();
  await page.getByLabel("Redemption Code").fill(code);
  await page.getByRole("button", {name: "Redeem", exact: true}).click();
  await expect(page.getByText("10 Credits added", {exact: true})).toBeVisible();
  await expect(page.getByText("Balance: 10 Credits", {exact: true})).toBeVisible();
  await page.getByRole("link", {name: "Run Analysis", exact: true}).click();
  await expect(page.getByText("Cost: 1 Credit", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Run Analysis", exact: true}).click();
  await expect(page.getByText("Development / Synthetic Result", {exact: true})).toBeVisible();
  await expect(page.getByText("Analysis status: COMPLETED", {exact: true})).toBeVisible();
  await page.goto("/account");
  await expect(page.getByText("Balance: 9 Credits", {exact: true})).toBeVisible();
  await expect(page.getByText("+10 · REDEMPTION · Balance 10", {exact: true})).toBeVisible();
  await expect(page.getByText("-1 · ANALYSIS · Balance 9", {exact: true})).toBeVisible();
  await page.goto("/history");
  await expect(page.getByRole("link", {name: "Synthetic analysis · COMPLETED"})).toBeVisible();
  await page.goto("/account");
  await page.getByRole("button", {name: "Sign out"}).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Username or email-like identifier").fill(identifier);
  await page.getByLabel("Password", {exact: true}).fill(password);
  await page.getByRole("button", {name: "Sign in", exact: true}).click();
  await expect(page.getByText("Balance: 9 Credits", {exact: true})).toBeVisible();
});
