import {expect, test} from "@playwright/test";
import {execFileSync} from "node:child_process";
import {mkdirSync, readFileSync, statSync} from "node:fs";
import path from "node:path";

test.use({trace: "off"});

test("HTTPS accounts protect sessions and support redemption with environment-gated analysis", async ({page}) => {
  const root = path.resolve(__dirname, "../../..");
  const stamp = Date.now().toString();
  const filename = `https-pilot-${stamp}.csv`;
  const uid = process.getuid?.();
  const gid = process.getgid?.();
  if (uid === undefined || gid === undefined || uid === 0 || gid === 0) {
    throw new Error("Deployment account tests require a non-root Linux runner");
  }
  mkdirSync(path.join(root, "exports"), {recursive: true, mode: 0o700});
  // Bind mounts retain host ownership. Match the runner for this one-off command
  // so it can create and the runner can read the operator's private 0600 CSV.
  execFileSync("docker", ["compose", "--env-file", ".env.production.local", "-p", "aevyra-phase2",
    "-f", "docker-compose.prod.yml", "-f", "docker-compose.prod.local.yml",
    "run", "--rm", "--no-deps", "--user", `${uid}:${gid}`, "--volume", `${path.join(root, "exports")}:/app/exports`,
    "api", "python", "-m", "aevyra_api.operator", "generate-batch", "--name", "HTTPS pilot",
    "--channel", "manual", "--sku", "pilot-10", "--credits", "10", "--quantity", "1",
    "--output", `exports/${filename}`], {cwd: root, stdio: "pipe"});
  const exported = statSync(path.join(root, "exports", filename));
  expect(exported.uid).toBe(uid);
  expect(exported.gid).toBe(gid);
  expect(exported.mode & 0o777).toBe(0o600);
  const code = readFileSync(path.join(root, "exports", filename), "utf8").trim().split(/\r?\n/)[1].split(",")[0];
  await page.goto("/register");
  await page.getByLabel("Username or email-like identifier").fill(`https-pilot-${stamp}`);
  await page.getByLabel("Password", {exact: true}).fill(`test-only-https-password-${stamp}`);
  await page.getByRole("button", {name: "Create account", exact: true}).click();
  await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
  const cookies = await page.context().cookies();
  const session = cookies.find(cookie => cookie.name === "auvylen_session");
  // Assert attributes without placing session values in assertion output.
  expect(Boolean(session?.httpOnly && session.secure && session.sameSite === "Lax")).toBe(true);
  await page.goto("/redeem");
  await page.getByLabel("Redemption Code").fill(code);
  await page.getByRole("button", {name: "Redeem", exact: true}).click();
  await expect(page.getByText("10 Credits added", {exact: true})).toBeVisible();
  await page.goto("/analyze");
  await expect(page.getByText("Balance: 10 Credits", {exact: true})).toBeVisible();
  if (process.env.AEVYRA_TEST_MODE === "production") {
    await expect(page.getByText("Synthetic analysis is unavailable in production.")).toBeVisible();
    const status = await page.evaluate(async () => {
      const csrf = await (await fetch("/api/v1/auth/csrf")).json();
      const response = await fetch("/api/v1/credit-analyses", {method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf.csrf_token},
        body: JSON.stringify({product_slug: "aevyra-test-analysis", idempotency_key: crypto.randomUUID()})});
      return response.status;
    });
    expect(status).toBe(404);
    await page.goto("/account");
    await expect(page.getByText("Balance: 10 Credits", {exact: true})).toBeVisible();
  } else {
    await page.getByRole("button", {name: "Run Analysis", exact: true}).click();
    await expect(page.getByText("Analysis status: COMPLETED", {exact: true})).toBeVisible();
    await page.goto("/account");
    await expect(page.getByText("Balance: 9 Credits", {exact: true})).toBeVisible();
  }
});
