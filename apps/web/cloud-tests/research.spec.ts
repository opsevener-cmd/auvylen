import {expect, test} from "@playwright/test";
import {execFileSync} from "node:child_process";
import {mkdirSync, readFileSync} from "node:fs";
import path from "node:path";

const root = path.resolve(__dirname, "../../..");
function compose(...args: string[]) {
  return execFileSync("docker", ["compose", "--env-file", ".env.cloud.local", "-p", "auvylen-phase4a-test",
    "-f", "docker-compose.prod.yml", "-f", "docker-compose.cloud.yml", "-f", "docker-compose.cloud.local.yml",
    "--profile", "research", ...args], {cwd: root, stdio: "pipe"}).toString();
}

test("HTTPS accounts, Credits and asynchronous free research survive restarts", async ({page}) => {
  const stamp = Date.now();
  const filename = `cloud-test-${stamp}.csv`;
  const identifier = `cloud-research-${stamp}`;
  const password = `test-only-cloud-password-${stamp}`;
  const origins = new Set<string>();
  page.on("request", request => {origins.add(new URL(request.url()).origin);});
  mkdirSync(path.join(root, "exports"), {recursive: true});
  compose("run", "--rm", "--no-deps", "--user", String(process.getuid?.() ?? 10001), "--volume", `${path.join(root, "exports")}:/app/exports`, "api", "python", "-m", "aevyra_api.operator",
    "generate-batch", "--name", "Cloud test", "--channel", "manual", "--sku", "cloud-test-10", "--credits", "10", "--quantity", "1",
    "--output", `exports/${filename}`);
  const code = readFileSync(path.join(root, "exports", filename), "utf8").trim().split(/\r?\n/)[1].split(",")[0];
  await page.goto("/register");
  await page.getByLabel("Username or email-like identifier").fill(identifier);
  await page.getByLabel("Password", {exact: true}).fill(password);
  await page.getByRole("button", {name: "Create account", exact: true}).click();
  await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
  const session = (await page.context().cookies()).find(cookie => cookie.name === "auvylen_session");
  expect(Boolean(session?.secure && session.httpOnly && session.sameSite === "Lax")).toBe(true);
  const publicUserId = await page.evaluate(async () => (await (await fetch("/api/v1/auth/me")).json()).user.public_user_id as string);
  await page.goto("/research");
  await expect(page.getByText("Research is disabled or operator authorization is required.")).toBeVisible();
  compose("exec", "-T", "api", "python", "-m", "aevyra_api.research.operator", "grant", publicUserId, "--reason", "Authorized synthetic cloud test");
  await page.goto("/redeem");
  await page.getByLabel("Redemption Code").fill(code);
  await page.getByRole("button", {name: "Redeem", exact: true}).click();
  await expect(page.getByText("10 Credits added", {exact: true})).toBeVisible();
  await page.goto("/analyze");
  await page.getByRole("button", {name: "Run Analysis", exact: true}).click();
  await expect(page.getByText("Analysis status: COMPLETED", {exact: true})).toBeVisible();
  await page.goto("/research");
  await page.getByRole("button", {name: "Run Synthetic Research Analysis", exact: true}).click();
  await expect(page.getByText("Research status: COMPLETED", {exact: true})).toBeVisible({timeout: 20000});
  await expect(page.getByText("Synthetic score:", {exact: false})).toBeVisible();
  await page.goto("/account");
  await expect(page.getByText("Balance: 9 Credits", {exact: true})).toBeVisible();
  const protectedStatuses = await page.evaluate(async () => {
    const paths = ["/.env", "/.git/config", "/exports/private.csv", "/docker-compose.cloud.yml", "/services/api/src/aevyra_api/config.py", "/models/private.ckpt", "/api/v1/operator/generate-batch"];
    return Promise.all(paths.map(async path => (await fetch(path)).status));
  });
  expect(protectedStatuses.every(status => status === 404)).toBe(true);
  const paymentStatus = await page.evaluate(async () => (await fetch("/api/v1/dev/payments/10000000-0000-4000-8000-000000000001/simulate-success", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"})).status);
  expect(paymentStatus).toBe(404);
  compose("restart", "postgres", "redis", "api", "worker");
  compose("up", "-d", "--wait");
  await page.reload();
  await expect(page.getByText("Balance: 9 Credits", {exact: true})).toBeVisible();
  await page.goto("/research");
  await expect(page.getByRole("button", {name: "mock · COMPLETED"})).toBeVisible();
  await page.goto("/account");
  await page.getByRole("button", {name: "Sign out", exact: true}).click();
  await page.getByLabel("Username or email-like identifier").fill(identifier);
  await page.getByLabel("Password", {exact: true}).fill(password);
  await page.getByRole("button", {name: "Sign in", exact: true}).click();
  await expect(page.getByText("Balance: 9 Credits", {exact: true})).toBeVisible();
  expect([...origins]).toEqual(["https://localhost:18443"]);
});
