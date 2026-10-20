import {expect, test} from "@playwright/test";

test("proxy reaches web, API, PostgreSQL and Redis", async ({page, request}) => {
  const ready = await request.get("/ready");
  expect(ready.status()).toBe(200);
  expect((await ready.json()).dependencies).toEqual({database: "ok", redis: "ok"});
  expect(ready.headers()["x-request-id"]).toBeTruthy();
  expect(ready.headers()["server"]).toBeUndefined();
  await page.goto("/status");
  await expect(page.getByRole("link", {name: "Auvylen.", exact: true})).toBeVisible();
  await expect(page.getByText("The API and its dependencies are ready.")).toBeVisible();
  const oversized = await request.post("/api/v1/orders", {data: "x".repeat(1048577)});
  expect(oversized.status()).toBe(413);
});

test("production disables mock commercial functionality", async ({page, request}) => {
  test.skip(process.env.AEVYRA_TEST_MODE !== "production");
  await page.goto("/");
  await expect(page.getByRole("link", {name: /View development demo/})).toHaveCount(0);
  await expect(page.getByText("Synthetic analysis is unavailable in production.")).toBeVisible();
  expect((await request.get("/api/v1/products")).status()).toBe(404);
  expect((await request.post("/api/v1/orders", {data: {product_slug: "aevyra-test-analysis"}})).status()).toBe(404);
  expect((await request.post("/api/v1/dev/payments/00000000-0000-0000-0000-000000000000/simulate-success", {data: {}})).status()).toBe(404);
});

test("staging mock checkout persists a synthetic result through HTTPS", async ({page, request}) => {
  test.skip(process.env.AEVYRA_TEST_MODE === "production");
  await page.goto("/");
  await page.getByRole("link", {name: /View development demo/}).click();
  await expect(page.getByRole("heading", {name: "Auvylen Analysis", exact: true})).toBeVisible();
  await expect(page.getByText("¥1.00", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Create order"}).click();
  await expect(page).toHaveURL(/\/checkout\/av_[a-f0-9]+$/);
  const reference = page.url().split("/").at(-1);
  await page.getByRole("button", {name: "Simulate successful payment"}).click();
  await expect(page).toHaveURL(/\/result\/[a-f0-9-]+$/);
  await expect(page.getByText("Development / Synthetic Result", {exact: true})).toBeVisible();
  await expect(page.getByText("Analysis status: COMPLETED", {exact: true})).toBeVisible();
  const order = await (await request.get(`/api/v1/orders/${reference}`)).json();
  expect(order.status).toBe("COMPLETED");
  expect(order.amount).toBe(100);
  const result = await (await request.get(`/api/v1/analyses/${order.analysis_id}/result`)).json();
  expect(result.metadata.synthetic).toBe(true);
});
